# -*- coding: utf-8 -*-
import odoo
import odoo.modules.registry
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
import re
import base64
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import random
import pytz
import time
from markupsafe import Markup, escape
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

NON_RETRYABLE_META_ERROR_CODES = {131049}
SIDECAR_NOTIFY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wa-sidecar')
MEDIA_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wa-media')


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return False

def _submit_best_effort(executor, func, label, fallback=None):
    """Run non-critical work without letting thread exhaustion break Odoo actions."""
    try:
        executor.submit(func)
        return True
    except RuntimeError as exc:
        _logger.warning("%s background worker unavailable: %s", label, exc)
        if fallback:
            try:
                fallback()
                return True
            except Exception as fallback_exc:
                _logger.warning("%s synchronous fallback failed: %s", label, fallback_exc)
        return False
    except Exception as exc:
        _logger.warning("%s background submit failed: %s", label, exc)
        return False


def _should_notify_realtime(message):
    """Queued campaign records are queue state, not live chat events yet."""
    if message.status in ('draft', 'queued'):
        return False
    if message.campaign_id and message.direction == 'outbound' and not message.chat_id_ref:
        return False
    return True


def notify_sidecar_background(env, message_id, event_type='new_message'):
    """Fire-and-forget notification to the sidecar â€” non-blocking thread."""
    # Capture db_name from the current cursor before spawning a thread
    try:
        db_name = env.cr.dbname
    except Exception:
        return  # env is already closed or unavailable

    def _do_request():
        try:
            # Use the correct registry access pattern
            registry = odoo.modules.registry.Registry(db_name)
            with registry.cursor() as cr:
                new_env = api.Environment(cr, odoo.SUPERUSER_ID, {})

                params = new_env['ir.config_parameter'].sudo()
                if params.get_param('whatsapp.realtime.mode', default='bus') != 'socket':
                    return
                base_url = params.get_param('whatsapp.sidecar.url')
                secret = params.get_param('whatsapp.sidecar.secret')
                if not base_url or not secret:
                    return

                msg = new_env['whatsapp.message'].sudo().browse(message_id)
                if not msg.exists():
                    return

                payload = {
                    'chat_id': msg.chat_id_ref.id if msg.chat_id_ref else msg.phone_number,
                    'message_id': msg.id,
                    'message_wamid': msg.message_id,
                    'status': msg.status,
                    'message': {
                        'id': msg.id,
                        'wamid': msg.message_id,
                        'body': msg.body,
                        'direction': msg.direction,
                        'type': msg.message_type,
                        'status': msg.status,
                    },
                    'type': event_type,
                }
                headers = {'x-sidecar-key': secret}
                requests.post(
                    f"{base_url.rstrip('/')}/relay/new-message",
                    json=payload, headers=headers, timeout=5
                )
        except Exception as e:
            _logger.warning('[SIDECAR-ASYNC] notification failed: %s', e)

    _submit_best_effort(SIDECAR_NOTIFY_EXECUTOR, _do_request, '[SIDECAR-ASYNC]')


class WhatsAppMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'create_date desc'
    _rec_name = 'phone_number'

    _message_id_unique = models.Constraint(
        'unique(message_id)',
        'Duplicate WhatsApp Message ID (wamid) detected. Data integrity enforced.',
    )

    _message_id_idx = models.Index(
        "(message_id) WHERE message_id IS NOT NULL",
    )
    _campaign_queue_idx = models.Index("(campaign_id, status, next_retry_at, create_date)")
    _message_status_idx = models.Index("(status, retry_count, next_retry_at, create_date)")
    _chat_direction_idx = models.Index("(chat_id_ref, direction, status, create_date)")

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Contact')
    phone_number = fields.Char('Phone Number', required=True)

    # Message details
    message_id = fields.Char('Message ID', help='WhatsApp Cloud API Message ID')
    message_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('template', 'Template'),
        ('interactive', 'Interactive'),
        ('internal_note', 'Internal Note'),
    ], string='Type', default='text', required=True)

    direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Direction', required=True, default='outbound')

    body = fields.Text('Message Body')
    media_url = fields.Char('Media URL')
    media_file = fields.Binary('Attachment')
    media_filename = fields.Char('Filename')
    media_mime_type = fields.Char('Media MIME Type')
    caption = fields.Text('Caption')

    # Interactive Data
    button_text = fields.Char('Button Text', help='Text of the button clicked')
    button_payload = fields.Char('Button Payload', help='Developer payload of the button')
    list_item_id = fields.Char('List Item ID', help='ID of the list item selected')
    list_item_title = fields.Char('List Item Title')
    interactive_type = fields.Char(
        'Interactive Type',
        help='Meta interactive type such as button, list, cta_url, product, product_list, or catalog_message.',
    )
    button_url = fields.Char('Button URL', help='URL used by CTA URL interactive messages.')
    catalog_id = fields.Char('Catalog ID', help='Meta Commerce Manager catalog ID used by product messages.')
    product_retailer_id = fields.Char(
        'Product Retailer ID',
        help='Commerce Manager content/product ID used by product and catalog messages.',
    )

    # Conversation Grouping
    chat_id = fields.Char('Chat ID', compute='_compute_chat_id', store=True)
    chat_id_ref = fields.Many2one('whatsapp.chat', string='Conversation', ondelete='cascade')
    raw_data = fields.Text('Raw Meta Data', help='Complete JSON payload from Meta')

    # Template fields â€” stored explicitly so action_send can build the correct Meta payload
    template_id = fields.Many2one('whatsapp.template', string='Template', ondelete='set null')
    template_name = fields.Char('Template Name', help='Approved Meta template name (e.g. hello_world)')
    template_language = fields.Char('Template Language', default='en_US', help='BCP-47 language code (e.g. en_US, hi)')

    # Status tracking
    status = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('deleted', 'Deleted'),
    ], string='Status', default='draft', required=True)

    error_message = fields.Text('Error Message')

    # Retry & Exponential Backoff (Phase 2)
    retry_count = fields.Integer('Retry Count', default=0, readonly=True)
    next_retry_at = fields.Datetime('Next Retry', help='Next attempt time for exponential backoff retry')

    # Threading (Replies)
    parent_id = fields.Many2one('whatsapp.message', string='Replying To', ondelete='set null')
    parent_message_id = fields.Char('Meta Parent ID', help='Original wamid being replied to')

    # Campaign relation
    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign', ondelete='set null')
    flow_id = fields.Many2one('whatsapp.bot.flow', string='Auto-Start Flow', ondelete='set null')
    ab_test_version = fields.Selection([
        ('a', 'Version A'),
        ('b', 'Version B'),
    ], string='A/B Version')

    # Timestamps & Analytics
    sent_date = fields.Datetime('Sent Date')
    delivered_date = fields.Datetime('Delivered Date')
    read_date = fields.Datetime('Read Date')
    latency_ms = fields.Float('API Latency (ms)', readonly=True)
    message_cost = fields.Float('Message Cost', digits=(16, 4), help="Estimated cost based on conversation type.")
    conversation_id = fields.Char('Meta Conversation ID')
    conversation_type = fields.Char('Conversation Type')
    pricing_category = fields.Char('Pricing Category')
    pricing_model = fields.Char('Pricing Model')

    # Compliance & Safety
    is_opt_out = fields.Boolean('Opt-out Message', default=False, help="True if this message triggered a STOP request.")

    # Automation
    is_automated = fields.Boolean('Automated Message', default=False)
    trigger_event = fields.Char('Trigger Event')

    # Media handling
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    preview_html = fields.Html('WhatsApp Preview', compute='_compute_preview')
    preview_text = fields.Text('Preview Text', compute='_compute_preview')

    # E-Commerce Integration
    sale_order_id = fields.Many2one('sale.order', string='Created Order', ondelete='set null')

    def _preview_media_url(self, media_type=None):
        self.ensure_one()
        message_type = media_type or self.message_type
        if self.media_file and self.id:
            route = 'image' if message_type == 'image' else 'content'
            return f"/web/{route}/whatsapp.message/{self.id}/media_file"
        if self.media_url and str(self.media_url).startswith(('http://', 'https://')):
            return self.media_url
        return False

    def _preview_document_icon_class(self):
        self.ensure_one()
        name = (self.media_filename or '').lower()
        if name.endswith(('.doc', '.docx')):
            return 'fa-file-word-o text-primary'
        if name.endswith(('.xls', '.xlsx')):
            return 'fa-file-excel-o text-success'
        if name.endswith(('.ppt', '.pptx')):
            return 'fa-file-powerpoint-o text-warning'
        if name.endswith('.pdf'):
            return 'fa-file-pdf-o text-danger'
        return 'fa-file-text-o text-muted'

    def _preview_plain_body(self):
        self.ensure_one()
        if self.caption:
            return self.caption
        if self.body:
            return self.body
        if self.button_text or self.list_item_title:
            return self.button_text or self.list_item_title
        if self.media_filename:
            return self.media_filename
        return ''

    def _render_media_preview_html(self):
        self.ensure_one()
        media_type = self.message_type
        media_url = self._preview_media_url(media_type)
        filename = self.media_filename or self.media_url or 'Attachment'
        caption = self.caption or self.body or ''
        caption_html = (
            "<div class='wa-preview-caption'>%s</div>" % escape(caption)
            if caption else ''
        )
        if media_type == 'image':
            if media_url:
                return Markup(
                    "<div class='wa-preview-media wa-preview-image'>"
                    "<img src='%s' alt='Image preview' loading='lazy'/></div>%s"
                ) % (escape(media_url), Markup(caption_html))
            return Markup(
                "<div class='wa-preview-media-placeholder'><i class='fa fa-image'></i>"
                "<span>%s</span></div>%s"
            ) % (escape(filename), Markup(caption_html))
        if media_type == 'video':
            if media_url:
                return Markup(
                    "<div class='wa-preview-media wa-preview-video'>"
                    "<video src='%s' controls preload='metadata'></video></div>%s"
                ) % (escape(media_url), Markup(caption_html))
            return Markup(
                "<div class='wa-preview-media-placeholder wa-preview-dark'><i class='fa fa-play-circle'></i>"
                "<span>%s</span></div>%s"
            ) % (escape(filename), Markup(caption_html))
        if media_type == 'audio':
            if media_url:
                return Markup(
                    "<div class='wa-preview-audio'><i class='fa fa-microphone'></i>"
                    "<audio src='%s' controls preload='metadata'></audio></div>%s"
                ) % (escape(media_url), Markup(caption_html))
            return Markup(
                "<div class='wa-preview-audio'><i class='fa fa-microphone'></i>"
                "<span>%s</span></div>%s"
            ) % (escape(filename), Markup(caption_html))
        icon = self._preview_document_icon_class()
        label = escape(filename)
        if media_url:
            title = Markup("<a href='%s' target='_blank'>%s</a>") % (escape(media_url), label)
        else:
            title = label
        return Markup(
            "<div class='wa-preview-document'><i class='fa %s'></i>"
            "<div class='wa-preview-document-text'><strong>%s</strong>"
            "<span>%s</span></div></div>%s"
        ) % (icon, title, escape(self.media_mime_type or 'Document'), Markup(caption_html))

    def _render_interactive_preview_html(self):
        self.ensure_one()
        try:
            raw = json.loads(self.raw_data or '{}')
        except Exception:
            raw = {}
        payload = raw.get('interactive') if isinstance(raw, dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        itype = self.interactive_type or payload.get('type') or 'interactive'
        body = ((payload.get('body') or {}).get('text') if isinstance(payload.get('body'), dict) else False) or self.body or ''
        header = payload.get('header') or {}
        footer = payload.get('footer') or {}
        pieces = [
            "<div class='wa-preview-type'><i class='fa fa-hand-pointer-o'></i>%s</div>"
            % escape(itype.replace('_', ' ').title())
        ]
        if isinstance(header, dict) and header.get('text'):
            pieces.append("<strong class='wa-preview-header'>%s</strong>" % escape(header['text']))
        if body:
            pieces.append("<div class='wa-preview-text'>%s</div>" % escape(body))
        if isinstance(footer, dict) and footer.get('text'):
            pieces.append("<div class='wa-preview-footer'>%s</div>" % escape(footer['text']))
        if self.button_text or self.list_item_title:
            pieces.append(
                "<div class='wa-preview-buttons'><div><i class='fa fa-reply'></i>%s</div></div>"
                % escape(self.button_text or self.list_item_title)
            )
        elif self.button_url:
            pieces.append(
                "<div class='wa-preview-buttons'><div><i class='fa fa-external-link'></i>%s</div></div>"
                % escape(self.button_text or 'Open link')
            )
        return Markup(''.join(pieces))

    def _render_preview_html(self):
        self.ensure_one()
        direction_class = 'wa-preview-outbound' if self.direction == 'outbound' else 'wa-preview-inbound'
        type_label = dict(self._fields['message_type'].selection).get(self.message_type, self.message_type or 'Message')
        if self.message_type == 'template' and self.template_id:
            body = self.template_id._render_customer_preview_html(
                partner=self.partner_id,
                message=self,
                body_override=self.body or False,
                shell=False,
                compact=True,
                include_template_name=True,
            )
        elif self.message_type in ('image', 'video', 'document', 'audio'):
            body = self._render_media_preview_html()
        elif self.message_type == 'interactive' or self.button_text or self.button_payload or self.list_item_title:
            body = self._render_interactive_preview_html()
        else:
            body = Markup("<div class='wa-preview-text'>%s</div>") % escape(self.body or 'Type a message...')
        status = escape(self.status or 'draft')
        time_label = 'Now'
        if self.create_date:
            local_dt = fields.Datetime.context_timestamp(self, self.create_date)
            time_label = local_dt.strftime('%I:%M %p').lstrip('0').lower()
        return Markup(
            "<div class='wa-message-preview-shell %s'>"
            "<div class='wa-message-preview-phone'>"
            "<div class='wa-message-preview-topbar'><span></span><strong>WhatsApp Preview</strong><span></span></div>"
            "<div class='wa-message-preview-chat'>"
            "<div class='wa-message-preview-bubble'>"
            "<div class='wa-preview-type-label'>%s</div>%s"
            "<div class='wa-preview-meta'><span>%s</span><span>%s</span></div>"
            "</div></div></div></div>"
        ) % (direction_class, escape(type_label), body, escape(time_label), status)

    @api.depends(
        'body', 'caption', 'message_type', 'direction', 'status', 'create_date',
        'media_file', 'media_url', 'media_filename', 'media_mime_type',
        'template_id', 'template_id.preview_html', 'template_name', 'template_language',
        'raw_data', 'button_text', 'button_payload', 'list_item_title', 'list_item_id',
        'interactive_type', 'button_url',
    )
    def _compute_preview(self):
        for record in self:
            try:
                preview = record._render_preview_html()
                record.preview_html = preview
                record.preview_text = html2plaintext(str(preview or '')).strip() or record._preview_plain_body()
            except Exception as exc:
                _logger.warning("WhatsApp message preview failed for %s: %s", record.id, exc)
                safe_error = escape(str(exc) or 'Preview not ready.')
                record.preview_html = Markup(
                    "<div class='alert alert-warning mb-0'>Preview not ready.<br/>%s</div>"
                ) % safe_error
                record.preview_text = "Preview not ready. %s" % safe_error

    @api.model
    def _is_non_retryable_meta_error_code(self, code):
        return _safe_int(code) in NON_RETRYABLE_META_ERROR_CODES

    @api.model
    def _meta_error_code_from_text(self, message):
        if not message:
            return False
        match = re.search(r'\[(\d+)\]', str(message))
        if match:
            return _safe_int(match.group(1))
        match = re.search(r'\b(?:code|error)\D{0,12}(\d{4,6})\b', str(message), re.IGNORECASE)
        return _safe_int(match.group(1)) if match else False

    @api.model
    def _format_meta_error(self, error):
        error = error or {}
        code = error.get('code')
        code_int = _safe_int(code)
        if code_int == 131049:
            return _(
                "[131049] Meta blocked delivery for this recipient to maintain WhatsApp ecosystem health. "
                "This commonly affects marketing templates when the recipient has reached Meta's per-user "
                "marketing limit or has low recent engagement. Do not retry immediately; wait for the "
                "customer to reply, improve opt-in/segmentation, or use an approved utility template for "
                "transactional content."
            )

        if code_int == 131053:
            return _(
                "[131053] Meta could not download the media link. Retry can securely re-upload "
                "temporary WhatsApp CDN media while it is still available. For an expired or "
                "other protected URL, upload the original file again."
            )

        title = error.get('title') or ''
        message = error.get('message') or ''
        details = ''
        if isinstance(error.get('error_data'), dict):
            details = error['error_data'].get('details') or ''

        parts = [part for part in (title, message, details) if part]
        text = " - ".join(parts) or _("Message delivery failed")
        return f"[{code}] {text}" if code else text

    def _is_non_retryable_failure(self):
        self.ensure_one()
        return self._is_non_retryable_meta_error_code(
            self._meta_error_code_from_text(self.error_message)
        )


    @api.depends('phone_number', 'account_id')
    def _compute_chat_id(self):
        for record in self:
            if record.phone_number and record.account_id:
                record.chat_id = f"{record.account_id.id}_{record.phone_number}"
            else:
                record.chat_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('phone_number'):
                account = self.env['whatsapp.account'].sudo().browse(vals.get('account_id')) if vals.get('account_id') else False
                vals['phone_number'] = self._normalize_phone(vals['phone_number'], account=account, strict=False)

            # Skip chat creation for campaign/bulk messages â€” they are marketing blasts,
            # not conversations. A chat will be created when the customer replies.
            is_campaign = bool(vals.get('campaign_id'))
            if not is_campaign and not vals.get('chat_id_ref') and vals.get('phone_number') and vals.get('account_id'):
                # Link to existing chat or create new one
                chat = self.env['whatsapp.chat'].sudo()._get_or_create_chat(vals['account_id'], vals['phone_number'])
                vals['chat_id_ref'] = chat.id

            # Auto-assign partner if missing
            if not vals.get('partner_id') and vals.get('phone_number'):
                normalized = self._normalize_phone(vals['phone_number'])
                partner_domain = [('phone', '=', normalized)]
                if 'mobile' in self.env['res.partner']._fields:
                    partner_domain = ['|', ('phone', '=', normalized), ('mobile', '=', normalized)]
                partner = self.env['res.partner'].sudo().search(partner_domain, limit=1)
                if partner:
                    vals['partner_id'] = partner.id

            # Populate body for templates to show in chat list
            if vals.get('message_type') == 'template' and (not vals.get('body') or vals.get('body') == 'Template Sent'):
                template = False
                if vals.get('template_id'):
                    template = self.env['whatsapp.template'].sudo().browse(vals['template_id'])
                if not template and vals.get('template_name'):
                    template_domain = [
                        '|',
                        ('meta_template_name', '=', vals.get('template_name')),
                        ('name', '=', vals.get('template_name')),
                    ]
                    if vals.get('account_id'):
                        template_domain = ['&', ('account_id', 'in', [False, vals.get('account_id')])] + template_domain
                    template = self.env['whatsapp.template'].sudo().search(template_domain, limit=1)
                if template:
                    vals['template_id'] = template.id
                    vals['body'] = template.body

        messages = super().create(vals_list)

        # Ensure outbound media gets an attachment so the UI can render it immediately
        for msg in messages:
            if msg.media_file and not msg.attachment_ids:
                attachment = self.env['ir.attachment'].sudo().create({
                    'name': msg.media_filename or f"media_{msg.id}",
                    'type': 'binary',
                    'datas': msg.media_file,
                    'res_model': 'whatsapp.message',
                    'res_id': msg.id,
                })
                msg.sudo().write({'attachment_ids': [(4, attachment.id)]})

            if msg.chat_id_ref and msg.partner_id and not msg.chat_id_ref.partner_id:
                msg.chat_id_ref.sudo().write({'partner_id': msg.partner_id.id})

            # Skip lead chatter sync for campaign messages to avoid CRM spam
            if msg.direction == 'inbound' and msg.chat_id_ref and not msg.campaign_id:
                msg.chat_id_ref.sudo()._sync_message_to_lead_chatter(msg)
            elif msg.direction == 'outbound' and msg.chat_id_ref and not msg.campaign_id:
                msg.chat_id_ref.sudo()._sync_message_to_lead_chatter(msg)

        # Notify real-time sidecar
        for record in messages:
            if _should_notify_realtime(record):
                notify_sidecar_background(self.env, record.id)

        return messages

    def write(self, vals):
        res = super(WhatsAppMessage, self).write(vals)
        notify_fields = {
            'status',
            'body',
            'media_file',
            'media_filename',
            'media_mime_type',
            'attachment_ids',
        }
        if notify_fields.intersection(vals):
            for record in self:
                event_type = 'status_update' if 'status' in vals else 'message_update'
                if _should_notify_realtime(record):
                    notify_sidecar_background(self.env, record.id, event_type=event_type)
                if 'status' in vals and record.chat_id_ref:
                    try:
                        self.env['bus.bus']._sendone(
                            'elsx_whatsapp_channel',
                            'whatsapp_status_update',
                            {
                                'chat_id': record.chat_id_ref.id,
                                'message_id': record.id,
                                'message_wamid': record.message_id,
                                'status': record.status,
                                'sent_date': str(record.sent_date or ''),
                                'delivered_date': str(record.delivered_date or ''),
                                'read_date': str(record.read_date or ''),
                            }
                        )
                    except Exception as exc:
                        _logger.debug("WhatsApp status bus notification failed: %s", exc)
                elif record.chat_id_ref:
                    try:
                        self.env['bus.bus']._sendone(
                            'elsx_whatsapp_channel',
                            'elsx_whatsapp_channel',
                            {
                                'chat_id': record.chat_id_ref.id,
                                'message_id': record.id,
                                'type': 'message_update',
                            }
                        )
                    except Exception as exc:
                        _logger.debug("WhatsApp message update bus notification failed: %s", exc)
        if vals.get('chat_id_ref'):
            for record in self.filtered(lambda msg: msg.chat_id_ref):
                record.chat_id_ref.sudo()._sync_message_to_lead_chatter(record)
        return res

    @api.model
    def _normalize_phone(self, phone, account=None, strict=False):
        """Normalize to the WhatsApp API format: E.164 digits without a leading plus."""
        if not phone:
            if strict:
                raise ValidationError(_("Phone number is required."))
            return False
        clean = re.sub(r'\D', '', phone)
        if clean.startswith('00'):
            clean = clean[2:]
        # Use account's default country code if no CC provided
        if len(clean) == 10 and not clean.startswith('0'):
            cc = '91'
            if account and getattr(account, 'default_country_code', False):
                cc = account.default_country_code
            else:
                active_account = self.env['whatsapp.account']._get_default_account()
                if active_account and active_account.default_country_code:
                    cc = active_account.default_country_code
                elif hasattr(self, 'account_id') and self.account_id and self.account_id.default_country_code:
                    cc = self.account_id.default_country_code
            clean = cc + clean
        if strict and not re.fullmatch(r'[1-9]\d{7,14}', clean or ''):
            raise ValidationError(_(
                "Invalid WhatsApp phone number '%s'. Use E.164 format with country code, "
                "for example 919876543210 or +14155552671."
            ) % phone)
        return clean

    @api.model
    def _find_partner_by_phone(self, phone):
        """Finds a partner by normalized phone number, accounting for spaces/symbols/prefixes"""
        if not phone:
            return False
        normalized = self._normalize_phone(phone)
        if not normalized:
            return False

        # 1. Try exact normalized match first
        domain = [('phone', '=', normalized)]
        if 'mobile' in self.env['res.partner']._fields:
            domain = ['|', ('phone', '=', normalized), ('mobile', '=', normalized)]
        partner = self.env['res.partner'].sudo().search(domain, limit=1)
        if partner:
            return partner

        # 2. Try normalized match with prepended '+'
        plus_normalized = '+' + normalized
        domain = [('phone', '=', plus_normalized)]
        if 'mobile' in self.env['res.partner']._fields:
            domain = ['|', ('phone', '=', plus_normalized), ('mobile', '=', plus_normalized)]
        partner = self.env['res.partner'].sudo().search(domain, limit=1)
        if partner:
            return partner

        # 3. Use suffix only to narrow candidates, then compare complete normalized
        # numbers so equal national numbers in different countries are never merged.
        if len(normalized) >= 10:
            suffix = normalized[-10:]
            domain = [('phone', 'like', suffix)]
            if 'mobile' in self.env['res.partner']._fields:
                domain = ['|', ('phone', 'like', suffix), ('mobile', 'like', suffix)]
            partners = self.env['res.partner'].sudo().search(domain)
            for p in partners:
                for candidate in (p.phone, getattr(p, 'mobile', False)):
                    if candidate and self._normalize_phone(candidate) == normalized:
                        return p
        return False

    def _coerce_interactive_button(self, button, index):
        title = False
        button_id = False

        if isinstance(button, dict):
            title = button.get('title') or button.get('name') or button.get('text') or button.get('label')
            button_id = button.get('id') or button.get('button_id') or button.get('payload') or button.get('value')
        elif isinstance(button, (list, tuple)):
            if len(button) >= 2:
                title, button_id = button[0], button[1]
            elif button:
                title = button[0]
        else:
            title = button

        title = str(title or button_id or f"Option {index + 1}").strip()
        button_id = str(button_id or title or f"button_{index + 1}").strip()
        if not title:
            return False

        if len(title) > 20:
            _logger.warning("[INTERACTIVE] Button title truncated to 20 chars: %s", title)
            title = title[:20]
        return {
            'type': 'reply',
            'reply': {
                'id': button_id[:256],
                'title': title,
            },
        }

    def _prepare_interactive_payload(self, body_text, buttons, header_text=False, footer_text=False):
        """Build and store a Meta Cloud API interactive button payload."""
        self.ensure_one()
        prepared_buttons = []
        for index, button in enumerate((buttons or [])[:3]):
            prepared = self._coerce_interactive_button(button, index)
            if prepared:
                prepared_buttons.append(prepared)

        if not prepared_buttons:
            raise ValidationError(_("Interactive messages require at least one button."))

        interactive = {
            'type': 'button',
            'body': {'text': body_text or ''},
            'action': {'buttons': prepared_buttons},
        }
        if header_text:
            interactive['header'] = {'type': 'text', 'text': str(header_text)[:60]}
        if footer_text:
            interactive['footer'] = {'text': str(footer_text)[:60]}
        write_vals = {
            'raw_data': json.dumps(interactive),
            'interactive_type': 'button',
        }
        if self.message_type != 'interactive':
            write_vals['message_type'] = 'interactive'
        if body_text and not self.body:
            write_vals['body'] = body_text
        self.sudo().write(write_vals)
        return interactive

    def _prepare_interactive_list_payload(self, body_text, rows, button_text=False, section_title=False, header_text=False, footer_text=False):
        """Build and store a Meta Cloud API interactive list payload."""
        self.ensure_one()
        prepared_rows = []
        for index, row in enumerate((rows or [])[:10]):
            if isinstance(row, dict):
                title = row.get('title') or row.get('name') or row.get('text') or row.get('label')
                row_id = row.get('id') or row.get('button_id') or row.get('payload') or row.get('value')
                description = row.get('description') or ''
            else:
                title = row
                row_id = row
                description = ''
            title = str(title or row_id or f"Option {index + 1}").strip()
            row_id = str(row_id or title or f"list_{index + 1}").strip()
            if not title:
                continue
            prepared = {
                'id': row_id[:200],
                'title': title[:24],
            }
            if description:
                prepared['description'] = str(description)[:72]
            prepared_rows.append(prepared)

        if not prepared_rows:
            raise ValidationError(_("Interactive list messages require at least one row."))

        interactive = {
            'type': 'list',
            'body': {'text': body_text or ''},
            'action': {
                'button': (button_text or _('Choose'))[:20],
                'sections': [{
                    'title': (section_title or _('Options'))[:24],
                    'rows': prepared_rows,
                }],
            },
        }
        if header_text:
            interactive['header'] = {'type': 'text', 'text': str(header_text)[:60]}
        if footer_text:
            interactive['footer'] = {'text': str(footer_text)[:60]}
        write_vals = {
            'raw_data': json.dumps(interactive),
            'interactive_type': 'list',
        }
        if self.message_type != 'interactive':
            write_vals['message_type'] = 'interactive'
        if body_text and not self.body:
            write_vals['body'] = body_text
        self.sudo().write(write_vals)
        return interactive

    def _prepare_interactive_cta_url_payload(self, body_text, display_text, url, header_text=False, footer_text=False):
        """Build and store a Meta Cloud API interactive CTA URL payload."""
        self.ensure_one()
        display_text = str(display_text or _('Open Link')).strip()[:20]
        url = str(url or '').strip()
        if not url:
            raise ValidationError(_("CTA URL messages require a URL."))
        if not url.startswith(('http://', 'https://')):
            raise ValidationError(_("CTA URL must start with http:// or https://."))
        interactive = {
            'type': 'cta_url',
            'body': {'text': body_text or ''},
            'action': {
                'name': 'cta_url',
                'parameters': {
                    'display_text': display_text,
                    'url': url,
                },
            },
        }
        if header_text:
            interactive['header'] = {'type': 'text', 'text': str(header_text)[:60]}
        if footer_text:
            interactive['footer'] = {'text': str(footer_text)[:60]}
        self.sudo().write({
            'message_type': 'interactive',
            'raw_data': json.dumps(interactive),
            'body': body_text or self.body,
            'interactive_type': 'cta_url',
            'button_text': display_text,
            'button_url': url,
        })
        return interactive

    def _prepare_interactive_product_payload(self, body_text, catalog_id, product_retailer_id, footer_text=False):
        """Build and store a single product interactive payload."""
        self.ensure_one()
        catalog_id = str(catalog_id or '').strip()
        product_retailer_id = str(product_retailer_id or '').strip()
        if not catalog_id or not product_retailer_id:
            raise ValidationError(_("Single product messages require Catalog ID and Product Retailer ID."))
        interactive = {
            'type': 'product',
            'body': {'text': body_text or _('Please review this product.')},
            'action': {
                'catalog_id': catalog_id,
                'product_retailer_id': product_retailer_id,
            },
        }
        if footer_text:
            interactive['footer'] = {'text': str(footer_text)[:60]}
        self.sudo().write({
            'message_type': 'interactive',
            'raw_data': json.dumps(interactive),
            'body': body_text or self.body or _('Product message'),
            'interactive_type': 'product',
            'catalog_id': catalog_id,
            'product_retailer_id': product_retailer_id,
        })
        return interactive

    def _prepare_interactive_product_list_payload(
        self, body_text, catalog_id, product_retailer_ids,
        header_text=False, footer_text=False, section_title=False,
    ):
        """Build and store a multi-product list payload."""
        self.ensure_one()
        catalog_id = str(catalog_id or '').strip()
        if isinstance(product_retailer_ids, str):
            product_retailer_ids = [
                part.strip() for part in re.split(r'[\n,;]+', product_retailer_ids)
                if part.strip()
            ]
        product_retailer_ids = [str(item).strip() for item in (product_retailer_ids or []) if str(item).strip()]
        if not catalog_id:
            raise ValidationError(_("Product list messages require Catalog ID."))
        if not product_retailer_ids:
            raise ValidationError(_("Product list messages require at least one Product Retailer ID."))
        product_retailer_ids = product_retailer_ids[:30]
        interactive = {
            'type': 'product_list',
            'header': {
                'type': 'text',
                'text': str(header_text or _('Products'))[:60],
            },
            'body': {'text': body_text or _('Please review these products.')},
            'action': {
                'catalog_id': catalog_id,
                'sections': [{
                    'title': str(section_title or _('Products'))[:24],
                    'product_items': [
                        {'product_retailer_id': item}
                        for item in product_retailer_ids
                    ],
                }],
            },
        }
        if footer_text:
            interactive['footer'] = {'text': str(footer_text)[:60]}
        self.sudo().write({
            'message_type': 'interactive',
            'raw_data': json.dumps(interactive),
            'body': body_text or self.body or _('Product list message'),
            'interactive_type': 'product_list',
            'catalog_id': catalog_id,
            'product_retailer_id': ','.join(product_retailer_ids),
        })
        return interactive

    def _prepare_interactive_catalog_message_payload(self, body_text, thumbnail_product_retailer_id=False, footer_text=False):
        """Build and store a catalog message payload that opens the WhatsApp shop/catalog."""
        self.ensure_one()
        parameters = {}
        thumbnail_product_retailer_id = str(thumbnail_product_retailer_id or '').strip()
        if thumbnail_product_retailer_id:
            parameters['thumbnail_product_retailer_id'] = thumbnail_product_retailer_id
        interactive = {
            'type': 'catalog_message',
            'body': {'text': body_text or _('Browse our catalogue.')},
            'action': {'name': 'catalog_message'},
        }
        if parameters:
            interactive['action']['parameters'] = parameters
        if footer_text:
            interactive['footer'] = {'text': str(footer_text)[:60]}
        self.sudo().write({
            'message_type': 'interactive',
            'raw_data': json.dumps(interactive),
            'body': body_text or self.body or _('Catalog message'),
            'interactive_type': 'catalog_message',
            'product_retailer_id': thumbnail_product_retailer_id,
        })
        return interactive

    def _store_downloaded_media(self, content, mimetype=False, filename=False):
        self.ensure_one()
        if not content:
            return False

        filename = filename or self.media_filename or f"media_{self.id}"
        encoded = base64.b64encode(content)
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'datas': encoded,
            'mimetype': mimetype,
            'res_model': 'whatsapp.message',
            'res_id': self.id,
        })
        self.sudo().write({
            'media_file': encoded,
            'media_filename': filename,
            'media_mime_type': mimetype or self.media_mime_type,
            'attachment_ids': [(4, attachment.id)],
        })
        return True

    def _restore_media_from_local_cache(self):
        self.ensure_one()
        attachment = self.attachment_ids[:1]
        if not attachment:
            attachment = self.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'whatsapp.message'),
                ('res_id', '=', self.id),
                ('type', '=', 'binary'),
            ], order='id desc', limit=1)
        if not attachment or not attachment.datas:
            return False

        self.sudo().write({
            'media_file': attachment.datas,
            'media_filename': self.media_filename or attachment.name,
            'media_mime_type': self.media_mime_type or attachment.mimetype,
            'attachment_ids': [(4, attachment.id)],
        })
        _logger.info("[MEDIA-DL] Restored media for message %s from local cache", self.id)
        return True

    def _download_media_from_sidecar(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('whatsapp.sidecar.url')
        if not base_url or not self.media_url:
            return False

        secret = self.env['ir.config_parameter'].sudo().get_param('whatsapp.sidecar.secret')
        if not secret:
            return False
        headers = {'x-sidecar-key': secret}
        media_ref = str(self.media_url).strip()
        endpoints = [
            f"{base_url.rstrip('/')}/media/{media_ref}",
            f"{base_url.rstrip('/')}/proxy/media/{media_ref}",
        ]

        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, headers=headers, timeout=10)
                if response.status_code != 200:
                    continue

                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    data = response.json()
                    content_b64 = data.get('content_base64') or data.get('data')
                    if content_b64:
                        return self._store_downloaded_media(
                            base64.b64decode(content_b64),
                            data.get('mime_type') or data.get('mimetype'),
                            data.get('filename'),
                        )
                    direct_url = data.get('url')
                    if direct_url:
                        media_response = requests.get(direct_url, timeout=20)
                        if media_response.status_code == 200:
                            return self._store_downloaded_media(
                                media_response.content,
                                media_response.headers.get('Content-Type'),
                                data.get('filename'),
                            )
                else:
                    return self._store_downloaded_media(
                        response.content,
                        content_type,
                        self.media_filename or f"media_{self.id}",
                    )
            except Exception as e:
                _logger.warning("[MEDIA-DL] Sidecar fallback failed for message %s via %s: %s", self.id, endpoint, e)
        return False

    def download_media_from_meta(self):
        """
        Three-tier media recovery:
        1. Meta direct URL/API
        2. Local attachment cache
        3. Sidecar proxy
        """
        self.ensure_one()
        if self.media_file:
            return True
        if not self.media_url:  # media_url stores the media_id for inbound
            return self._restore_media_from_local_cache()

        account = self.account_id
        if not account or not account.access_token:
            return self._restore_media_from_local_cache() or self._download_media_from_sidecar()

        _logger.info(f"[MEDIA-DL] Starting download for media_id {self.media_url}")

        try:
            headers = {'Authorization': f'Bearer {account.access_token}'}
            media_ref = str(self.media_url).strip()
            download_url = media_ref if media_ref.startswith(('http://', 'https://')) else False
            mime_type = self.media_mime_type

            if not download_url:
                url = f"https://graph.facebook.com/{account.api_version}/{media_ref}"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    download_url = data.get('url')
                    mime_type = data.get('mime_type') or mime_type
                else:
                    _logger.warning("[MEDIA-DL] Failed to get URL for %s: %s", media_ref, resp.text[:300])

            if download_url:
                binary_resp = requests.get(download_url, headers=headers, timeout=30)
                if binary_resp.status_code == 200:
                    saved = self._store_downloaded_media(
                        binary_resp.content,
                        mime_type or binary_resp.headers.get('Content-Type'),
                        self.media_filename or f"media_{self.id}",
                    )
                    if saved:
                        _logger.info(f"[MEDIA-DL] Successfully saved media for message {self.id}")
                        return True
                else:
                    _logger.warning("[MEDIA-DL] Binary download failed for message %s: %s", self.id, binary_resp.status_code)
            else:
                _logger.warning("[MEDIA-DL] No direct download URL returned for message %s", self.id)
        except Exception as e:
            _logger.warning("[MEDIA-DL] Direct Meta download failed for message %s: %s", self.id, e)

        return self._restore_media_from_local_cache() or self._download_media_from_sidecar()

    def queue_media_download(self):
        """Download inbound media after the webhook transaction commits."""
        for message in self:
            db_name = message.env.registry.db_name
            message_id = message.id

            def _after_commit(db_name=db_name, message_id=message_id):
                def _download():
                    try:
                        registry = odoo.modules.registry.Registry(db_name)
                        with registry.cursor() as cr:
                            env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                            msg = env['whatsapp.message'].sudo().browse(message_id)
                            if msg.exists():
                                msg.download_media_from_meta()
                                cr.commit()
                    except Exception as e:
                        _logger.error("[MEDIA-DL] Async download failed for message %s: %s", message_id, e)

                _submit_best_effort(
                    MEDIA_DOWNLOAD_EXECUTOR,
                    _download,
                    '[MEDIA-DL]',
                    fallback=_download,
                )

            self.env.cr.postcommit.add(_after_commit)

    def action_retry_media_download(self):
        """Manual, safe retry for inbound media cards shown in Team Inbox."""
        success_count = 0
        failed = []
        for message in self:
            try:
                if message.download_media_from_meta():
                    success_count += 1
                    if message.chat_id_ref:
                        self.env['bus.bus']._sendone(
                            'elsx_whatsapp_channel',
                            'elsx_whatsapp_channel',
                            {
                                'chat_id': message.chat_id_ref.id,
                                'message_id': message.id,
                                'type': 'message_update',
                            }
                        )
                else:
                    failed.append(message.id)
            except Exception as exc:
                _logger.warning("[MEDIA-DL] Manual retry failed for message %s: %s", message.id, exc)
                failed.append(message.id)

        if success_count:
            message = _("Media downloaded. Refreshing the chat preview.")
            notif_type = 'success'
        elif failed:
            message = _("Media is still unavailable from Meta. Please retry after a moment or check the account token.")
            notif_type = 'warning'
        else:
            message = _("No media message was selected.")
            notif_type = 'info'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WhatsApp Media'),
                'message': message,
                'type': notif_type,
                'sticky': False,
            },
        }

    def _get_active_compliance_policy(self):
        self.ensure_one()
        if not self.account_id:
            return self.env['whatsapp.compliance.policy']
        return self.env['whatsapp.compliance.policy'].sudo().search([
            ('account_id', '=', self.account_id.id),
            ('active', '=', True),
        ], limit=1)

    def _current_quiet_hour(self, policy):
        self.ensure_one()
        if not policy:
            return False

        quiet_hours = self.env['whatsapp.quiet.hours'].sudo().search([
            ('policy_id', '=', policy.id),
            ('active', '=', True),
        ])
        now_utc = fields.Datetime.to_datetime(fields.Datetime.now())
        if now_utc.tzinfo is None:
            now_utc = pytz.utc.localize(now_utc)

        for quiet in quiet_hours:
            try:
                tz = pytz.timezone(quiet.timezone or 'UTC')
            except pytz.UnknownTimeZoneError:
                tz = pytz.utc
            local_now = now_utc.astimezone(tz)
            weekday = local_now.weekday()
            if quiet.days_of_week == 'weekdays' and weekday >= 5:
                continue
            if quiet.days_of_week == 'weekends' and weekday < 5:
                continue

            current_hour = local_now.hour + (local_now.minute / 60.0) + (local_now.second / 3600.0)
            start = quiet.start_time or 0.0
            end = quiet.end_time or 0.0
            if start <= end:
                in_window = start <= current_hour < end
            else:
                in_window = current_hour >= start or current_hour < end
            if in_window:
                return quiet
        return False

    def _check_compliance(self):
        """Verify if the recipient can receive this outbound WhatsApp message."""
        self.ensure_one()
        # 1. Tier Limit Check
        if not self.account_id._has_daily_capacity():
            raise ValidationError(_("Daily messaging limit reached for account %s.") % self.account_id.name)

        policy = self._get_active_compliance_policy()

        # 2. Opt-in / Opt-out / DND Checks
        if self.partner_id:
            if 'whatsapp_opt_in' in self.partner_id._fields and not self.partner_id.whatsapp_opt_in:
                raise ValidationError(_("Partner %s has not opted in to WhatsApp messages.") % self.partner_id.name)

            consent = self.env['whatsapp.consent.log'].sudo().search([
                ('partner_id', '=', self.partner_id.id),
                ('account_id', '=', self.account_id.id),
                ('status', 'in', ['opted_out', 'revoked'])
            ], limit=1)
            if consent:
                raise ValidationError(_("Partner %s has opted out of WhatsApp messages.") % self.partner_id.name)

            if policy and policy.respect_dnd_list and self.partner_id.id in policy.dnd_contact_ids.ids:
                raise ValidationError(_("Partner %s is on the WhatsApp do-not-contact list.") % self.partner_id.name)

        if policy and (self.is_automated or self.campaign_id):
            quiet = self._current_quiet_hour(policy)
            if quiet:
                raise ValidationError(_("Quiet hours are active for policy %s.") % policy.name)
        return True

    def action_send(self):
        """
        Sends the message via Meta Cloud API using account_id.send_message.
        Unified entry point for Draft, Queued, and One-Click messages.
        """
        for record in self:
            if record.direction == 'inbound' or record.status in ['sent', 'delivered', 'read']:
                continue

            # Compliance Check before attempting send
            record._check_compliance()

            payload = {}
            # 1. Start with raw_data if available (contains pre-calculated components)
            if record.raw_data:
                try:
                    payload = json.loads(record.raw_data)
                except Exception:
                    pass

            # 2. Extract specific payload segment if nested under 'template' or 'interactive'
            if record.message_type == 'template' and 'template' in payload:
                payload = payload['template']
            elif record.message_type == 'interactive' and 'interactive' in payload:
                payload = payload['interactive']

            # 3. Fallback for simple messages
            if not payload:
                if record.message_type == 'text':
                    payload['body'] = record.body
                elif record.message_type in ['image', 'video', 'document', 'audio']:
                    payload[record.message_type] = {'id': record.media_url}

            # Build explicit kwargs per message type (NO **payload splat â€” causes TypeError)
            send_kwargs = {
                'existing_message': record,
                'partner_id': record.partner_id.id if record.partner_id else False,
                'body': record.body,
            }
            context_message_id = record.parent_message_id or (record.parent_id.message_id if record.parent_id else False)
            if context_message_id:
                send_kwargs['context_message_id'] = context_message_id
            if record.campaign_id:
                send_kwargs['campaign_id'] = record.campaign_id.id
            if record.flow_id:
                send_kwargs['flow_id'] = record.flow_id.id

            if record.message_type == 'template':
                needs_media_header = (
                    record.template_id
                    and record.template_id.header_type in ('image', 'video', 'document')
                )
                has_header_component = bool(
                    payload
                    and any(
                        isinstance(component, dict)
                        and str(component.get('type') or '').lower() == 'header'
                        for component in (payload.get('components') or [])
                    )
                )
                if needs_media_header and not has_header_component:
                    send_kwargs['template_record'] = record.template_id
                    if record.media_file:
                        send_kwargs['header_media_file'] = record.media_file
                        send_kwargs['header_media_filename'] = record.media_filename
                    elif record.media_url:
                        send_kwargs['header_media_url'] = record.media_url
                        if record.media_filename:
                            send_kwargs['header_media_filename'] = record.media_filename
                elif payload and payload.get('name') and payload.get('language'):
                    send_kwargs['template'] = payload
                    if record.template_id:
                        send_kwargs['template_record'] = record.template_id
                elif record.template_id:
                    send_kwargs['template_record'] = record.template_id
                    if record.media_file:
                        send_kwargs['header_media_file'] = record.media_file
                        send_kwargs['header_media_filename'] = record.media_filename
                    elif record.media_url:
                        send_kwargs['header_media_url'] = record.media_url
                        if record.media_filename:
                            send_kwargs['header_media_filename'] = record.media_filename
                elif record.template_name:
                    send_kwargs['template_name'] = record.template_name
                    send_kwargs['language_code'] = record.template_language or 'en_US'
                    if payload and payload.get('components'):
                        send_kwargs['components'] = payload.get('components')
            elif record.message_type == 'interactive':
                if not isinstance(payload, dict) or not payload:
                    raise ValidationError(
                        _("Interactive message %s is missing interactive payload data.") % record.id
                    )
                send_kwargs['interactive'] = payload
            elif record.message_type == 'text':
                send_kwargs['body'] = payload.get('body', record.body) if payload else record.body
            elif record.message_type in ('image', 'video', 'document', 'audio'):
                send_kwargs['body'] = record.caption or record.body
                if record.media_file:
                    send_kwargs['media_file'] = record.media_file
                    send_kwargs['media_filename'] = record.media_filename
                    send_kwargs['caption'] = record.caption or record.body
                elif record.media_url:
                    send_kwargs['media_url'] = record.media_url
                    send_kwargs['caption'] = record.caption or record.body

            record.account_id.send_message(
                record.phone_number,
                message_type=record.message_type,
                **send_kwargs
            )
        return True

    def action_retry(self):
        cancelled_campaign_messages = self.filtered(
            lambda msg: msg.campaign_id and msg.campaign_id.state in ('cancelled', 'archived')
        )
        if cancelled_campaign_messages:
            raise UserError(_(
                'Messages from a Cancelled or Archived campaign cannot be retried. '
                'Duplicate the campaign to start a new delivery run.'
            ))
        non_retryable = self.filtered(lambda msg: msg._is_non_retryable_failure())
        if non_retryable:
            raise UserError(_(
                "This message failed with Meta error 131049, so retrying the same marketing template "
                "immediately is blocked. Wait for the customer to reply, retry later with better "
                "segmentation, or use an approved utility template for transactional content."
            ))
        self.write({'status': 'queued', 'error_message': False})
        self.action_send()

    def action_mark_read(self):
        self.write({'status': 'read', 'read_date': fields.Datetime.now()})

    @api.model
    def _cleanup_old_messages(self, days=None):
        if days is None:
            try:
                days = int(self.env['ir.config_parameter'].sudo().get_param('whatsapp.retention.days', default=0) or 0)
            except (TypeError, ValueError):
                days = 0
        if not days or days <= 0:
            _logger.info("WhatsApp message retention cleanup skipped; retention is disabled.")
            return 0

        limit_date = fields.Datetime.now() - timedelta(days=days)
        messages = self.search([('create_date', '<', limit_date)])
        count = len(messages)
        if messages:
            messages.unlink()
        return count

    @api.model
    def _cron_process_broadcast_queue(self, limit=100):
        """
        High-priority processor for the broadcast campaign queue.
        Processes newly 'queued' messages that haven't failed yet.
        """
        started = time.monotonic()
        now = fields.Datetime.now()
        queued_msgs = self.search([
            ('status', '=', 'queued'),
            ('retry_count', '=', 0),
            ('campaign_id', '=', False),
            '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now)
        ], limit=limit, order='create_date asc')

        sent_count = 0
        for msg in queued_msgs:
            try:
                with self.env.cr.savepoint():
                    msg.action_send()
                if msg.status in ('sent', 'delivered', 'read'):
                    sent_count += 1
            except Exception as e:
                _logger.error(f"[CRON-BROADCAST] Message {msg.id} failed: {e}")
                vals = {
                    'status': 'failed',
                    'error_message': str(e),
                    'next_retry_at': False,
                }
                if not isinstance(e, ValidationError):
                    backoff_seconds = min(3600, 60 * (2 ** min(msg.retry_count, 5)))
                    vals.update({
                        'retry_count': msg.retry_count + 1,
                        'next_retry_at': fields.Datetime.now() + timedelta(seconds=backoff_seconds + random.uniform(0, 10)),
                    })
                msg.write(vals)

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        _logger.info(
            "[CRON-BROADCAST] processed=%s sent=%s duration_ms=%s",
            len(queued_msgs), sent_count, duration_ms,
        )
        return sent_count

    @api.model
    def _cron_retry_failed(self):
        """
        Cron job to retry failed messages with exponential backoff.
        """
        started = time.monotonic()
        now = fields.Datetime.now()

        # Failed-only retry path. Queued messages are handled by their queue processors.
        retry_msgs = self.search([
            ('status', '=', 'failed'),
            ('retry_count', '<', 5),
            ('next_retry_at', '!=', False),
            ('next_retry_at', '<=', now),
            '|',
                ('campaign_id', '=', False),
                ('campaign_id.state', 'in', ['running', 'scheduled']),
        ], limit=50, order='next_retry_at asc, create_date asc')

        retried_count = 0
        for msg in retry_msgs:
            if msg._is_non_retryable_failure():
                msg.write({'next_retry_at': False})
                continue
            try:
                with self.env.cr.savepoint():
                    msg.action_send()
                if msg.status in ('sent', 'delivered', 'read'):
                    retried_count += 1
                    flow = msg.flow_id or (msg.campaign_id.flow_id if msg.campaign_id else False)
                    if flow:
                        try:
                            flow.sudo().start_flow_for_participant(False, msg)
                        except Exception as flow_err:
                            _logger.error("[CRON-RETRY] Failed to auto-start flow %s: %s", flow.name, flow_err)
                    if msg.campaign_id and not self.search_count([
                        ('campaign_id', '=', msg.campaign_id.id),
                        '|',
                            ('status', 'in', ['draft', 'queued']),
                            '&', '&', ('status', '=', 'failed'), ('retry_count', '<', 5), ('next_retry_at', '!=', False),
                    ]):
                        msg.campaign_id.state = 'completed'
            except Exception as e:
                try:
                    vals = {
                        'error_message': str(e)[:500],
                        'status': 'failed',
                        'next_retry_at': False,
                    }
                    if not isinstance(e, ValidationError):
                        backoff_seconds = min(3600, 60 * (2 ** min(msg.retry_count, 5)))
                        jitter = random.uniform(0, 10)
                        vals.update({
                            'retry_count': msg.retry_count + 1,
                            'next_retry_at': now + timedelta(seconds=backoff_seconds + jitter),
                        })
                    msg.write(vals)
                except Exception:
                    _logger.error(f"[CRON-RETRY] Could not update message {msg.id} after failure")

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        _logger.info(
            "[CRON-RETRY] processed=%s resent=%s duration_ms=%s",
            len(retry_msgs), retried_count, duration_ms,
        )
        return retried_count
