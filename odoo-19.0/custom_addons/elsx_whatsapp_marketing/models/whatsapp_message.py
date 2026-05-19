# -*- coding: utf-8 -*-
import odoo
import odoo.modules.registry
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json
import logging
import re
import base64
from datetime import timedelta
import threading
import random
import pytz

_logger = logging.getLogger(__name__)

def notify_sidecar_background(env, message_id, event_type='new_message'):
    """Fire-and-forget notification to the sidecar — non-blocking thread."""
    # Capture db_name from the current cursor before spawning a thread
    try:
        db_name = env.cr.dbname
    except Exception:
        return  # env is already closed or unavailable

    def _do_request():
        try:
            # Use the correct Odoo 19 registry access pattern
            registry = odoo.modules.registry.Registry(db_name)
            with registry.cursor() as cr:
                new_env = api.Environment(cr, odoo.SUPERUSER_ID, {})

                base_url = new_env['ir.config_parameter'].sudo().get_param('whatsapp.sidecar.url')
                secret = new_env['ir.config_parameter'].sudo().get_param(
                    'whatsapp.sidecar.secret', 'elsx_sidecar_secure_2024'
                )
                if not base_url:
                    return

                msg = new_env['whatsapp.message'].sudo().browse(message_id)
                if not msg.exists():
                    return

                payload = {
                    'chat_id': msg.chat_id_ref.id if msg.chat_id_ref else msg.phone_number,
                    'message': {
                        'id': msg.id,
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

    thread = threading.Thread(target=_do_request, daemon=True)
    thread.start()


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

    # Conversation Grouping
    chat_id = fields.Char('Chat ID', compute='_compute_chat_id', store=True)
    chat_id_ref = fields.Many2one('whatsapp.chat', string='Conversation', ondelete='cascade')
    raw_data = fields.Text('Raw Meta Data', help='Complete JSON payload from Meta')

    # Template fields — stored explicitly so action_send can build the correct Meta payload
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

            if not vals.get('chat_id_ref') and vals.get('phone_number') and vals.get('account_id'):
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
            if vals.get('message_type') == 'template' and not vals.get('body'):
                template = self.env['whatsapp.template'].sudo().search([('name', '=', vals.get('template_name'))], limit=1)
                if template:
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

            if msg.direction == 'inbound' and msg.chat_id_ref:
                msg.chat_id_ref.sudo()._sync_message_to_lead_chatter(msg)

        # Notify real-time sidecar
        for record in messages:
            if record.status != 'draft':
                notify_sidecar_background(self.env, record.id)
                
        return messages

    def write(self, vals):
        res = super(WhatsAppMessage, self).write(vals)
        if 'status' in vals or 'body' in vals:
            for record in self:
                notify_sidecar_background(self.env, record.id, event_type='message_update')
        if vals.get('chat_id_ref'):
            for record in self.filtered(lambda msg: msg.direction == 'inbound' and msg.chat_id_ref):
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
                active_account = self.env['whatsapp.account'].search([], limit=1)
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

        # 3. Clean and search using suffix (last 10 digits for common mobile numbers like India/US)
        if len(normalized) >= 10:
            suffix = normalized[-10:]
            domain = [('phone', 'like', suffix)]
            if 'mobile' in self.env['res.partner']._fields:
                domain = ['|', ('phone', 'like', suffix), ('mobile', 'like', suffix)]
            partners = self.env['res.partner'].sudo().search(domain)
            for p in partners:
                # Strip all non-digits from partner's phone/mobile to see if it matches normalized suffix
                p_phone = re.sub(r'\D', '', p.phone or '')
                p_mobile = re.sub(r'\D', '', p.mobile or '')
                if p_phone.endswith(suffix) or p_mobile.endswith(suffix):
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

    def _prepare_interactive_payload(self, body_text, buttons):
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
        write_vals = {'raw_data': json.dumps(interactive)}
        if self.message_type != 'interactive':
            write_vals['message_type'] = 'interactive'
        if body_text and not self.body:
            write_vals['body'] = body_text
        self.sudo().write(write_vals)
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

        secret = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.sidecar.secret', 'elsx_sidecar_secure_2024'
        )
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
                        registry = odoo.registry(db_name)
                        with registry.cursor() as cr:
                            env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                            msg = env['whatsapp.message'].sudo().browse(message_id)
                            if msg.exists():
                                msg.download_media_from_meta()
                                cr.commit()
                    except Exception as e:
                        _logger.error("[MEDIA-DL] Async download failed for message %s: %s", message_id, e)

                thread = threading.Thread(target=_download)
                thread.daemon = True
                thread.start()

            self.env.cr.postcommit.add(_after_commit)

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
        if self.account_id.is_limit_reached:
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

            # Build explicit kwargs per message type (NO **payload splat — causes TypeError)
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
                if payload and payload.get('name') and payload.get('language'):
                    send_kwargs['template'] = payload
                elif record.template_id:
                    send_kwargs['template_record'] = record.template_id
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
        self.write({'status': 'queued', 'error_message': False})
        self.action_send()

    def action_mark_read(self):
        self.write({'status': 'read', 'read_date': fields.Datetime.now()})

    @api.model
    def _cleanup_old_messages(self, days=90):
        limit_date = fields.Datetime.now() - timedelta(days=days)
        self.search([('create_date', '<', limit_date)]).unlink()

    @api.model
    def _cron_process_broadcast_queue(self, limit=100):
        """
        High-priority processor for the broadcast campaign queue.
        Processes newly 'queued' messages that haven't failed yet.
        """
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
        
        if sent_count > 0:
            _logger.info(f"[CRON-BROADCAST] Successfully processed {sent_count} messages from queue.")
        return sent_count

    @api.model
    def _cron_retry_failed(self):
        """
        Cron job to retry failed messages with exponential backoff.
        """
        now = fields.Datetime.now()
        
        # Failed-only retry path. Queued messages are handled by their queue processors.
        retry_msgs = self.search([
            ('status', '=', 'failed'),
            ('retry_count', '<', 5),
            ('next_retry_at', '!=', False),
            ('next_retry_at', '<=', now),
        ], limit=50, order='next_retry_at asc, create_date asc')
        
        retried_count = 0
        for msg in retry_msgs:
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
        
        if retried_count > 0:
            _logger.info(f"[CRON-RETRY] Successfully resent {retried_count} failed messages")
        return retried_count
