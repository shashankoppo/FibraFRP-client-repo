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
    
    _sql_constraints = [
        ('message_id_unique', 'unique(message_id)', 'Duplicate WhatsApp Message ID (wamid) detected. Data integrity enforced.'),
    ]
    
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
    ab_test_version = fields.Selection([
        ('a', 'Version A'),
        ('b', 'Version B'),
    ], string='A/B Version')

    # Timestamps
    sent_date = fields.Datetime('Sent Date')
    delivered_date = fields.Datetime('Delivered Date')
    read_date = fields.Datetime('Read Date')

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
        """Finds a partner by normalized phone number"""
        if not phone:
            return False
        normalized = self._normalize_phone(phone)
        domain = [('phone', '=', normalized)]
        if 'mobile' in self.env['res.partner']._fields:
            domain = ['|', ('phone', '=', normalized), ('mobile', '=', normalized)]
        return self.env['res.partner'].sudo().search(domain, limit=1)

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

    def action_send(self):
        """
        Sends the message via Meta Cloud API using account_id.send_message.
        Unified entry point for Draft, Queued, and One-Click messages.
        """
        for record in self:
            if record.direction == 'inbound' or record.status in ['sent', 'delivered', 'read']:
                continue
            
            payload = {}
            # 1. Start with raw_data if available (contains pre-calculated components)
            if record.raw_data:
                try:
                    payload = json.loads(record.raw_data)
                except: pass

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
            if record.campaign_id:
                send_kwargs['campaign_id'] = record.campaign_id.id

            if record.message_type == 'template':
                if payload and payload.get('name') and payload.get('language'):
                    send_kwargs['template'] = payload
                elif record.template_name:
                    send_kwargs['template_name'] = record.template_name
                    send_kwargs['language_code'] = record.template_language or 'en_US'
                    if payload and payload.get('components'):
                        send_kwargs['components'] = payload.get('components')
            elif record.message_type == 'interactive':
                send_kwargs['interactive'] = payload if payload else None
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
    def _cron_retry_failed(self):
        """
        Cron job to retry failed messages with exponential backoff.
        Uses savepoints per message to prevent one failure from rolling back
        the entire batch (fixes SerializationFailure crashes).
        
        Retry schedule:
        - Attempt 1: immediate
        - Attempt 2: after 1s
        - Attempt 3: after 4s
        - Attempt 4: after 16s
        - Attempt 5: after 64s → then permanent failure
        """
        from datetime import timedelta
        import random
        
        now = fields.Datetime.now()
        
        # Find messages ready for retry (next_retry_at <= now)
        retry_msgs = self.search([
            ('status', 'in', ['failed', 'queued']),
            ('retry_count', '<', 5),
            '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now)
        ], limit=50, order='next_retry_at asc, create_date asc')
        
        retried_count = 0
        for msg in retry_msgs:
            # Use a savepoint so one message failure doesn't kill the whole batch
            try:
                cr = self.env.cr
                cr.execute("SAVEPOINT retry_msg_%s", (msg.id,))
                msg.action_send()
                cr.execute("RELEASE SAVEPOINT retry_msg_%s", (msg.id,))
                retried_count += 1
            except Exception as e:
                cr.execute("ROLLBACK TO SAVEPOINT retry_msg_%s", (msg.id,))
                
                # Calculate next retry time with exponential backoff + jitter
                backoff_seconds = (2 ** msg.retry_count) if msg.retry_count > 0 else 0
                jitter = random.uniform(0, 0.5)
                next_retry_seconds = backoff_seconds + jitter
                
                try:
                    msg.write({
                        'retry_count': msg.retry_count + 1,
                        'next_retry_at': now + timedelta(seconds=next_retry_seconds),
                        'error_message': str(e)[:500],
                        'status': 'failed',
                    })
                except Exception:
                    _logger.error(f"[CRON-RETRY] Could not update message {msg.id} after failure")
                
                _logger.warning(
                    f"[CRON-RETRY] Message {msg.id} retry {msg.retry_count+1}/5 "
                    f"scheduled for +{next_retry_seconds:.1f}s: {e}"
                )
        
        if retried_count > 0:
            _logger.info(f"[CRON-RETRY] Successfully resent {retried_count} failed messages")
        
        return retried_count
