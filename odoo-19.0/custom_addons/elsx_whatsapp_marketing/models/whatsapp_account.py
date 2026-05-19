# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
import base64
import io
import mimetypes
import random
from datetime import timedelta

_logger = logging.getLogger(__name__)


MEDIA_SIZE_LIMITS = {
    'image': 5 * 1024 * 1024,
    'video': 16 * 1024 * 1024,
    'audio': 16 * 1024 * 1024,
    'document': 100 * 1024 * 1024,
}

TEXT_MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024


class WhatsAppAccount(models.Model):
    _name = 'whatsapp.account'
    _description = 'WhatsApp Business Account'
    _rec_name = 'name'

    name = fields.Char('Account Name', required=True)
    phone_number = fields.Char('Phone Number', required=True, help='WhatsApp Business phone number with country code')
    phone_number_id = fields.Char('Phone Number ID', required=True, help='WhatsApp Cloud API Phone Number ID')
    business_account_id = fields.Char('Business Account ID', required=True)
    access_token = fields.Char('Access Token', required=True, help='WhatsApp Cloud API Access Token')
    api_version = fields.Char('API Version', default='v18.0')
    app_id = fields.Char('App ID', help='Meta App ID')
    app_secret = fields.Char('App Secret', help='Meta App Secret (for HMAC verification)')
    default_country_code = fields.Char('Default Country Code', default='91', help='Default country code for numbers without one (e.g. 91 for India)')
    
    # Status
    active = fields.Boolean('Active', default=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
        ('error', 'Error'),
    ], string='Status', default='draft')
    
    # Statistics
    message_count = fields.Integer('Total Messages', compute='_compute_statistics')
    campaign_count = fields.Integer('Total Campaigns', compute='_compute_statistics')
    
    # Relations
    message_ids = fields.One2many('whatsapp.message', 'account_id', string='Messages')
    campaign_ids = fields.One2many('whatsapp.campaign', 'account_id', string='Campaigns')
    template_ids = fields.One2many('whatsapp.template', 'account_id', string='Templates')
    compliance_policy_ids = fields.One2many('whatsapp.compliance.policy', 'account_id', string='Compliance Policies')
    team_member_ids = fields.One2many('whatsapp.team.member', 'account_id', string='Team Members')
    media_ids = fields.One2many('whatsapp.media.library', 'account_id', string='Media Library')
    
    # Settings
    auto_reply_enabled = fields.Boolean('Auto Reply Enabled', default=False)
    auto_reply_message = fields.Text('Auto Reply Message')
    notification_sound_receive = fields.Selection([
        ('bell', 'Bell'),
        ('chime', 'Chime'),
        ('pop', 'Pop'),
        ('none', 'None'),
    ], string='Receive Notification Sound', default='bell')
    notification_sound_send = fields.Selection([
        ('ting', 'Ting'),
        ('swish', 'Swish'),
        ('click', 'Click'),
        ('none', 'None'),
    ], string='Send Notification Sound', default='ting')
    notification_enabled = fields.Boolean('Notification Sounds Enabled', default=True)
    webhook_url = fields.Char('Webhook URL', compute='_compute_webhook_url')
    webhook_verify_token = fields.Char('Webhook Verify Token', default='elsx_verify_2024')
    webhook_status = fields.Selection([
        ('none', 'Not Tested'),
        ('verified', 'Verified'),
        ('failed', 'Failed')
    ], string='Webhook Verification Status', default='none', readonly=True)
    webhook_last_error = fields.Text('Webhook Last Error', readonly=True)
    skip_webhook_hmac = fields.Boolean('Skip Signature Check (Debug)', default=False, 
                                      help="Disable HMAC verification for testing. WARNING: Highly insecure for production.")
    is_primary_webhook_db = fields.Boolean('Is Primary Webhook DB', default=True,
                                          help="Mark this database as the receiver for webhooks.")
    two_factor_pin = fields.Char('2FA PIN (for Registration)', help='6-digit PIN for two-step verification registration')

    # AI & Automation
    ai_enabled = fields.Boolean('AI Automation Enabled', default=True)
    ai_model = fields.Selection([
        ('gpt-4o', 'GPT-4o (Premium)'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('claude-3-5-sonnet', 'Claude 3.5 Sonnet'),
    ], string='AI Model', default='gpt-4o')
    ai_context = fields.Text('AI Business Context', help='Tell the AI about your business to generate better replies.')
    
    # Industrial Rate Limiting (Token Bucket)
    rate_limit_capacity = fields.Integer('Bucket Capacity', default=80, help="Max burst capacity")
    rate_limit_fill_rate = fields.Float('Fill Rate (msgs/sec)', default=40.0, help="Average messages per second")
    token_bucket_level = fields.Float('Current Bucket Level', default=80.0, readonly=True)
    token_bucket_last_fill = fields.Datetime('Last Bucket Fill Time', readonly=True)
    
    # Template Sync
    last_sync_date = fields.Datetime('Last Template Sync')

    # Meta Business Profile Fields
    business_description = fields.Text('Description / About')
    business_vertical = fields.Selection([
        ('UNDEFINED', 'Undefined'),
        ('AUTOMOTIVE', 'Automotive'),
        ('BEAUTY_SPA', 'Beauty / Spa'),
        ('EDUCATION', 'Education'),
        ('ENTERTAINMENT', 'Entertainment'),
        ('ENERGY', 'Energy'),
        ('FINANCE_BANKING', 'Finance / Banking'),
        ('FOOD_BEVERAGE', 'Food / Beverage'),
        ('GOVERNMENT', 'Government'),
        ('HEALTH_MEDICAL', 'Health / Medical'),
        ('HOSPITALITY', 'Hospitality'),
        ('NON_PROFIT', 'Non-Profit'),
        ('PROF_SERVICES', 'Professional Services'),
        ('RETAIL', 'Retail'),
        ('TRAVEL_TRANSPORT', 'Travel / Transport'),
        ('RESTAURANTS', 'Restaurants'),
        ('OTHER', 'Other'),
    ], string='Vertical', default='UNDEFINED')
    business_address = fields.Char('Address')
    business_email = fields.Char('Public Email')
    business_websites = fields.Char('Websites (comma separated)')
    profile_picture_url = fields.Char('Profile Picture URL')
    profile_image = fields.Image('Profile Image')
    quality_rating = fields.Char('Quality Rating', readonly=True)
    messaging_limit = fields.Char('Messaging Limit', readonly=True)
    
    # Industrial Tier & Compliance
    opt_out_keywords = fields.Char('Opt-out Keywords', default='STOP,UNSUBSCRIBE,OFF', 
                                  help="Comma-separated keywords that trigger automatic blacklisting.")
    daily_message_count = fields.Integer('Daily Message Count', default=0, readonly=True)
    max_daily_limit = fields.Integer('Max Daily Limit', default=1000, 
                                    help="Meta messaging tier limit (e.g., 1000, 10000).")
    is_limit_reached = fields.Boolean('Limit Reached', compute='_compute_limit_reached', store=True)
    
    # API Test Fields
    test_phone_number = fields.Char('Test Recipient')
    test_message_body = fields.Text('Test Body')
    test_api_status = fields.Selection([('none', 'Not Run'), ('success', 'Success'), ('failed', 'Failed')], default='none')
    test_api_response = fields.Text('Last API Response')
    is_sandbox = fields.Boolean('Sandbox Mode', default=False)
    sandbox_warning = fields.Text('Sandbox Notice', compute='_compute_sandbox_warning')

    @api.depends('is_sandbox', 'daily_message_count', 'max_daily_limit')
    def _compute_limit_reached(self):
        for rec in self:
            rec.is_limit_reached = rec.daily_message_count >= rec.max_daily_limit

    @api.depends('is_sandbox')
    def _compute_sandbox_warning(self):
        for rec in self:
            if rec.is_sandbox:
                rec.sandbox_warning = "In Sandbox Mode, messages can only be sent to Meta-registered test numbers."
            else:
                rec.sandbox_warning = False

    @api.constrains('phone_number', 'default_country_code')
    def _check_phone_configuration(self):
        normalizer = self.env['whatsapp.message']
        for rec in self:
            if rec.phone_number:
                normalizer._normalize_phone(rec.phone_number, account=rec, strict=True)
            if rec.default_country_code and (not rec.default_country_code.isdigit() or len(rec.default_country_code) > 3):
                raise ValidationError(_("Default country code must contain 1 to 3 digits."))

    @api.depends('message_ids', 'campaign_ids')
    def _compute_statistics(self):
        for record in self:
            record.message_count = len(record.message_ids)
            record.campaign_count = len(record.campaign_ids)
    
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.webhook_url = f"{base_url}/whatsapp/webhook/{record.id}"
    
    def action_test_connection(self):
        """Test WhatsApp Cloud API connection"""
        self.ensure_one()
        try:
            url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.status = 'connected'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success!',
                        'message': 'WhatsApp account connected successfully',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.status = 'error'
                raise Exception(f"API Error: {response.text}")
                
        except Exception as e:
            self.status = 'error'
            _logger.error(f"WhatsApp connection test failed: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Failed',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_register_phone(self):
        """Register phone number for Cloud API"""
        self.ensure_one()
        if not self.two_factor_pin:
            from odoo.exceptions import UserError
            raise UserError("2FA PIN is required for registration.")

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/register"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'messaging_product': 'whatsapp',
            'pin': self.two_factor_pin,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                self.status = 'connected'
                return True
            else:
                raise Exception(response.text)
        except Exception as e:
            _logger.error(f"Registration failed: {e}")
            raise

    def action_sync_templates(self):
        """Sync templates from Meta WhatsApp Business Account"""
        self.ensure_one()
        url = f"https://graph.facebook.com/{self.api_version}/{self.business_account_id}/message_templates"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                templates_data = response.json().get('data', [])
                for t_data in templates_data:
                    template_name = t_data.get('name')
                    language_code = t_data.get('language') or 'en_US'
                    template = self.env['whatsapp.template'].search([
                        ('account_id', '=', self.id),
                        ('language_code', '=', language_code),
                        '|',
                            ('meta_template_name', '=', template_name),
                            ('name', '=', template_name),
                    ], limit=1)
                    
                    vals = {
                        'name': template_name,
                        'meta_template_name': template_name,
                        'template_id': t_data.get('id'),
                        'language_code': language_code,
                        'language': self.env['whatsapp.template']._normalize_language_selection(language_code),
                        'category': self._map_template_category(t_data.get('category')),
                        'status': self._map_template_status(t_data.get('status')),
                        'account_id': self.id,
                    }
                    
                    # Extract content
                    for component in t_data.get('components', []):
                        if component.get('type') == 'BODY':
                            vals['body'] = component.get('text')
                        elif component.get('type') == 'HEADER':
                            vals['header_type'] = (component.get('format') or 'none').lower()
                            if vals['header_type'] == 'text':
                                vals['header_text'] = component.get('text')
                        elif component.get('type') == 'FOOTER':
                            vals['footer'] = component.get('text')
                    
                    if template:
                        template.write(vals)
                    else:
                        template = self.env['whatsapp.template'].create(vals)
                    template.action_refresh_variables()
                
                self.last_sync_date = fields.Datetime.now()
                return True
            raise UserError(_("Meta template sync failed: %s") % (response.text or response.status_code))
        except Exception as e:
            _logger.error(f"Sync failed: {e}")
            raise

    def _map_template_category(self, meta_category):
        category = (meta_category or 'MARKETING').lower()
        return category if category in ('marketing', 'utility', 'authentication') else 'marketing'

    def _map_template_status(self, meta_status):
        status = (meta_status or 'draft').lower()
        status_map = {
            'approved': 'approved',
            'pending': 'pending',
            'in_appeal': 'pending',
            'rejected': 'rejected',
            'disabled': 'rejected',
            'paused': 'rejected',
            'pending_deletion': 'rejected',
        }
        return status_map.get(status, 'draft')

    @api.model
    def _cron_reset_daily_counters(self):
        """Reset daily message counters for all accounts at midnight UTC."""
        self.search([]).write({'daily_message_count': 0})
        _logger.info("WhatsApp daily message counters reset successfully.")

    def _consume_rate_limit_token(self):
        """Consume 1 token from the bucket using atomic SQL to prevent SerializationFailure.
        
        This avoids the 'could not serialize access due to concurrent update' error
        that occurs when multiple cron jobs (broadcast queue + retry) try to ORM-write
        the same whatsapp.account row simultaneously.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        if not self.token_bucket_last_fill:
            # First-time initialization — safe to use ORM since it's a one-time write
            self.sudo().write({
                'token_bucket_last_fill': now,
                'token_bucket_level': max((self.rate_limit_capacity or 1.0) - 1.0, 0.0),
                'daily_message_count': self.daily_message_count + 1,
            })
            return True

        diff_seconds = (now - self.token_bucket_last_fill).total_seconds()
        new_level = min(self.rate_limit_capacity, self.token_bucket_level + (diff_seconds * self.rate_limit_fill_rate))

        if new_level < 1.0:
            return False

        # Atomic SQL update: only succeeds if no concurrent write changed the row
        try:
            self.env.cr.execute("""
                UPDATE whatsapp_account
                SET token_bucket_level = %s,
                    token_bucket_last_fill = %s,
                    daily_message_count = daily_message_count + 1,
                    write_date = NOW() AT TIME ZONE 'UTC'
                WHERE id = %s
            """, (new_level - 1.0, now, self.id))
            # Invalidate the ORM cache so subsequent reads see the new values
            self.invalidate_recordset(['token_bucket_level', 'token_bucket_last_fill', 'daily_message_count'])
            return True
        except Exception:
            _logger.warning(f"Token bucket contention on account {self.id}, will retry next cycle")
            return False

    def send_message(self, to_number, message_type='text', **kwargs):
        """
        Send WhatsApp message via Cloud API.
        Handles: text, template, image, video, document, audio, interactive.
        """
        self.ensure_one()
        to_number = self.env['whatsapp.message']._normalize_phone(to_number, account=self, strict=True)
        existing_msg = kwargs.get('existing_message')
        if not existing_msg and not kwargs.get('skip_compliance'):
            self.env['whatsapp.message'].new({
                'account_id': self.id,
                'phone_number': to_number,
                'partner_id': kwargs.get('partner_id'),
                'campaign_id': kwargs.get('campaign_id'),
                'message_type': message_type,
                'direction': 'outbound',
                'is_automated': bool(kwargs.get('is_automated') or kwargs.get('campaign_id')),
            })._check_compliance()
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to_number,
        }
        
        if message_type == 'text':
            body = kwargs.get('body', '') or ''
            if len(body) > TEXT_MESSAGE_LIMIT:
                raise UserError(_("WhatsApp text messages cannot exceed %s characters.") % TEXT_MESSAGE_LIMIT)
            payload['type'] = 'text'
            payload['text'] = {'body': body, 'preview_url': True}
        
        elif message_type == 'template':
            payload['type'] = 'template'
            template_payload = kwargs.get('template')
            if not template_payload and kwargs.get('template_record'):
                partner = kwargs.get('partner')
                if not partner and kwargs.get('partner_id'):
                    partner = self.env['res.partner'].browse(kwargs['partner_id'])
                template_payload = kwargs['template_record']._prepare_send_payload(partner=partner)
            if not template_payload and kwargs.get('template_name'):
                template_payload = {
                    'name': kwargs.get('template_name'),
                    'language': {'code': kwargs.get('language_code') or kwargs.get('template_language') or 'en_US'},
                    'components': kwargs.get('components') or [],
                }
            
            if template_payload:
                # Ensure components key is omitted entirely if empty for Meta API stability (Prevents 131009 error)
                if 'components' in template_payload and not template_payload['components']:
                    del template_payload['components']
                payload['template'] = template_payload
            else:
                raise UserError(_("Template messages require a template payload, template record, or template name."))

        elif message_type == 'image':
            payload['type'] = 'image'
            if kwargs.get('media_file'):
                media_id = self._upload_media_to_meta(kwargs['media_file'], kwargs.get('media_filename', 'image'), 'image')
                payload['image'] = {'id': media_id}
            else:
                payload['image'] = kwargs.get('image') or self._prepare_media_reference(kwargs.get('media_url'), 'image')
            if kwargs.get('caption'):
                if len(kwargs['caption']) > CAPTION_LIMIT:
                    raise UserError(_("WhatsApp media captions cannot exceed %s characters.") % CAPTION_LIMIT)
                payload['image']['caption'] = kwargs['caption']

        elif message_type == 'video':
            payload['type'] = 'video'
            if kwargs.get('media_file'):
                media_id = self._upload_media_to_meta(kwargs['media_file'], kwargs.get('media_filename', 'video'), 'video')
                payload['video'] = {'id': media_id}
            else:
                payload['video'] = kwargs.get('video') or self._prepare_media_reference(kwargs.get('media_url'), 'video')
            if kwargs.get('caption'):
                if len(kwargs['caption']) > CAPTION_LIMIT:
                    raise UserError(_("WhatsApp media captions cannot exceed %s characters.") % CAPTION_LIMIT)
                payload['video']['caption'] = kwargs['caption']

        elif message_type == 'document':
            payload['type'] = 'document'
            if kwargs.get('media_file'):
                media_id = self._upload_media_to_meta(kwargs['media_file'], kwargs.get('media_filename', 'document'), 'document')
                payload['document'] = {'id': media_id}
            else:
                payload['document'] = kwargs.get('document') or self._prepare_media_reference(kwargs.get('media_url'), 'document')
            if kwargs.get('media_filename'):
                payload['document']['filename'] = kwargs['media_filename']
            if kwargs.get('caption'):
                if len(kwargs['caption']) > CAPTION_LIMIT:
                    raise UserError(_("WhatsApp media captions cannot exceed %s characters.") % CAPTION_LIMIT)
                payload['document']['caption'] = kwargs['caption']

        elif message_type == 'audio':
            payload['type'] = 'audio'
            if kwargs.get('media_file'):
                media_id = self._upload_media_to_meta(kwargs['media_file'], kwargs.get('media_filename', 'audio'), 'audio')
                payload['audio'] = {'id': media_id}
            else:
                payload['audio'] = kwargs.get('audio') or self._prepare_media_reference(kwargs.get('media_url'), 'audio')

        elif message_type == 'interactive':
            payload['type'] = 'interactive'
            interactive_payload = kwargs.get('interactive')
            if not isinstance(interactive_payload, dict) or not interactive_payload:
                raise UserError(_("Interactive messages require a valid interactive payload."))
            if not interactive_payload.get('type'):
                raise UserError(_("Interactive payload is missing its type."))
            payload['interactive'] = interactive_payload
        else:
            raise UserError(_("Unsupported WhatsApp message type: %s") % message_type)

        context_message_id = kwargs.get('context_message_id')
        if context_message_id:
            payload['context'] = {'message_id': context_message_id}

        biz_opaque = kwargs.get('biz_opaque_callback_data') or (f"campaign_{kwargs.get('campaign_id')}" if kwargs.get('campaign_id') else False)
        if biz_opaque:
            payload['biz_opaque_callback_data'] = str(biz_opaque)

        # Rate Limiting Check
        if not self._consume_rate_limit_token():
            import time
            time.sleep(0.5) # Quick retry wait
            if not self._consume_rate_limit_token():
                _logger.warning(f"WhatsApp Rate Limit Exceeded for {self.name}")
                retry_delay = 60 + random.uniform(0, 15)
                next_retry_at = fields.Datetime.now() + timedelta(seconds=retry_delay)
                if existing_msg:
                    existing_msg.write({
                        'status': 'queued',
                        'error_message': 'Rate limit exceeded; queued for retry.',
                        'next_retry_at': next_retry_at,
                    })
                    return existing_msg
                queued_vals = {
                    'account_id': self.id,
                    'phone_number': to_number,
                    'partner_id': kwargs.get('partner_id'),
                    'campaign_id': kwargs.get('campaign_id'),
                    'flow_id': kwargs.get('flow_id'),
                    'message_type': message_type,
                    'body': kwargs.get('body') or payload.get('text', {}).get('body') or f"Media: {message_type}",
                    'direction': 'outbound',
                    'status': 'queued',
                    'next_retry_at': next_retry_at,
                    'error_message': 'Rate limit exceeded; queued for retry.',
                    'raw_data': json.dumps(payload),
                }
                return self.env['whatsapp.message'].create(queued_vals)

        import time
        start_time = time.time()
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            latency = (time.time() - start_time) * 1000
            
            # Create Industrial API Log
            log_vals = {
                'account_id': self.id,
                'endpoint': url,
                'method': 'POST',
                'request_body': json.dumps(payload),
                'response_body': response.text,
                'status_code': response.status_code,
                'latency': latency,
                'template_name': payload.get('template', {}).get('name') if message_type == 'template' else False,
            }
            if kwargs.get('partner_id'):
                # We'll link the message later if successful
                pass
                
            self.env['whatsapp.api.log'].sudo().create(log_vals)

            try:
                response_data = response.json()
            except ValueError:
                response_data = {'error': {'message': response.text or 'Invalid JSON response from Meta'}}
            
            # Create local log
            vals = {
                'account_id': self.id,
                'phone_number': to_number,
                'partner_id': kwargs.get('partner_id'),
                'campaign_id': kwargs.get('campaign_id'),
                'flow_id': kwargs.get('flow_id'),
                'message_type': message_type,
                'body': kwargs.get('body') or (payload.get('text', {}).get('body')) or f"Media: {message_type}",
                'direction': 'outbound',
                'raw_data': json.dumps(payload),
            }

            if response.status_code in (200, 201):
                vals.update({
                    'status': 'sent',
                    'message_id': response_data.get('messages', [{}])[0].get('id'),
                    'sent_date': fields.Datetime.now(),
                    'error_message': False,
                    'latency_ms': latency,
                    'retry_count': 0,
                    'next_retry_at': False,
                })
            else:
                error_msg = str(response_data.get('error', {}).get('message', 'Unknown error'))
                error_code = response_data.get('error', {}).get('code')
                
                _logger.error(f"WhatsApp send failed (Code {error_code}): {error_msg}")
                
                vals.update({
                    'status': 'failed',
                    'error_message': error_msg,
                })
                retryable_codes = {4, 17, 32, 613, 130429, 131048, 131056}
                retryable = response.status_code in (408, 425, 429, 500, 502, 503, 504) or error_code in retryable_codes
                if retryable:
                    current_retry = existing_msg.retry_count if existing_msg else 0
                    retry_delay = min(3600, 60 * (2 ** min(current_retry, 5))) + random.uniform(0, 10)
                    vals.update({
                        'retry_count': current_retry + 1,
                        'next_retry_at': fields.Datetime.now() + timedelta(seconds=retry_delay),
                    })
                else:
                    vals['next_retry_at'] = False

                # Handle Authentication Errors (190) specifically for Enterprise Stability
                if error_code == 190:
                    self.sudo().write({
                        'status': 'disconnected',
                        'webhook_status': 'failed',
                        'webhook_last_error': f"Authentication Failed (190): {error_msg}"
                    })

            if existing_msg:
                existing_msg.write(vals)
                return existing_msg
            else:
                msg = self.env['whatsapp.message'].create(vals)
                return msg
                
        except Exception as e:
            _logger.error(f"WhatsApp message send error: {str(e)}")
            if existing_msg:
                try:
                    existing_msg.write({
                        'status': 'failed',
                        'error_message': str(e),
                    })
                except Exception:
                    _logger.exception("Failed to persist send error on existing message %s", existing_msg.id)
            else:
                try:
                    self.env['whatsapp.message'].create({
                        'account_id': self.id,
                        'phone_number': to_number,
                        'partner_id': kwargs.get('partner_id'),
                        'campaign_id': kwargs.get('campaign_id'),
                        'flow_id': kwargs.get('flow_id'),
                        'message_type': message_type,
                        'body': kwargs.get('body') or payload.get('text', {}).get('body') or f"Media: {message_type}",
                        'direction': 'outbound',
                        'status': 'failed',
                        'error_message': str(e),
                        'raw_data': json.dumps(payload),
                    })
                except Exception:
                    _logger.exception("Failed to create failed-send message log for account %s", self.id)
            raise

    def _prepare_media_reference(self, media_reference, media_type):
        if not media_reference:
            raise UserError(_("Please provide a media file, Meta media ID, or public HTTPS media URL for %s messages.") % media_type)
        media_reference = str(media_reference).strip()
        if media_reference.startswith('http://'):
            raise UserError(_("WhatsApp media links must use HTTPS."))
        if media_reference.startswith('https://'):
            return {'link': media_reference}
        return {'id': media_reference}

    def _check_media_upload_size(self, binary_data, media_type, filename=None):
        """Return decoded content after validating Meta Cloud API media limits."""
        if media_type not in MEDIA_SIZE_LIMITS:
            raise UserError(_("Unsupported WhatsApp media type: %s") % media_type)
        try:
            file_content = base64.b64decode(binary_data or b'')
        except Exception as exc:
            raise UserError(_("The uploaded media file could not be decoded.")) from exc

        size = len(file_content)
        limit = MEDIA_SIZE_LIMITS[media_type]
        if size > limit:
            raise UserError(_(
                "%(name)s is too large for WhatsApp %(type)s messages (%(size).2f MB). "
                "Maximum allowed size is %(limit).0f MB."
            ) % {
                'name': filename or _('Media file'),
                'type': media_type,
                'size': size / (1024 * 1024),
                'limit': limit / (1024 * 1024),
            })
        return file_content

    def _upload_media_to_meta(self, binary_data, filename, media_type):
        """Upload binary data to Meta and return media_id"""
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        file_content = self._check_media_upload_size(binary_data, media_type, filename)
        # Ensure we have a valid filename for the MIME guessing and Meta payload
        if not filename:
            extension = {
                'image': 'jpg', 'video': 'mp4', 
                'document': 'pdf', 'audio': 'mp3'
            }.get(media_type, 'bin')
            filename = f"upload_{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"
            
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = {
                'image': 'image/jpeg', 'video': 'video/mp4', 
                'document': 'application/pdf', 'audio': 'audio/mpeg'
            }.get(media_type, 'application/octet-stream')

        files = {'file': (filename, io.BytesIO(file_content), mime_type)}
        # Meta Cloud API is extremely sensitive to parameter types and order in multipart requests.
        # Ensure data values are explicit strings.
        data = {
            'messaging_product': 'whatsapp', 
            'type': str(media_type)
        }
        
        try:
            _logger.info(f"Uploading media to Meta: type={media_type}, filename={filename}, mime={mime_type}")
            response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            resp_json = response.json() if response.content else {}
            
            if response.status_code in (200, 201):
                return resp_json.get('id')
            else:
                error_msg = resp_json.get('error', {}).get('message', 'Upload failed')
                _logger.error(f"Meta Media Upload Error: {resp_json}")
                raise Exception(f"Media upload failed: {error_msg}")
        except Exception as e:
            _logger.error(f"Media upload exception: {e}")
            raise

    def action_get_business_profile(self):
        """Fetch profile from Meta"""
        self.ensure_one()
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        try:
            # Profile
            res = requests.get(f"{url}/whatsapp_business_profile?fields=about,description,address,email,websites,vertical,profile_picture_url", headers=headers, timeout=20)
            if res.status_code == 200:
                data = res.json().get('data', [{}])[0]
                vertical = data.get('vertical') or 'UNDEFINED'
                if vertical not in dict(self._fields['business_vertical'].selection):
                    vertical = 'OTHER'
                self.write({
                    'business_description': data.get('description') or data.get('about'),
                    'business_address': data.get('address'),
                    'business_email': data.get('email'),
                    'business_vertical': vertical,
                    'business_websites': ", ".join(data.get('websites', [])),
                    'profile_picture_url': data.get('profile_picture_url'),
                })
            # Quality
            res2 = requests.get(f"{url}?fields=quality_rating,messaging_limit_tier", headers=headers, timeout=20)
            if res2.status_code == 200:
                d = res2.json()
                self.quality_rating = d.get('quality_rating')
                self.messaging_limit = d.get('messaging_limit_tier')
            return True
        except Exception as e:
            _logger.error(f"Profile sync error: {e}")
            return False

    def action_update_business_profile(self):
        """Push profile to Meta"""
        self.ensure_one()
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/whatsapp_business_profile"
        headers = {'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'}
        payload = {
            "messaging_product": "whatsapp",
            "description": self.business_description or "",
            "address": self.business_address or "",
            "email": self.business_email or "",
            "vertical": self.business_vertical or "UNDEFINED",
            "websites": [w.strip() for w in (self.business_websites or "").split(",") if w.strip()],
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code not in (200, 201):
                raise UserError(_("Meta profile update failed: %s") % response.text)
            return True
        except Exception as e:
            _logger.error(f"Profile update error: {e}")
            raise

    def action_sync_profile_picture(self):
        """Fetch and store the WhatsApp Business profile picture from Meta."""
        self.ensure_one()
        if not self.profile_picture_url:
            self.action_get_business_profile()
        if not self.profile_picture_url:
            raise UserError(_("Meta did not return a profile picture URL for this account."))

        try:
            response = requests.get(self.profile_picture_url, timeout=30)
            if response.status_code != 200:
                raise UserError(_("Profile picture download failed: %s") % response.text)
            self.write({'profile_image': base64.b64encode(response.content)})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Profile Picture Updated'),
                    'message': _('The WhatsApp business profile picture was refreshed from Meta.'),
                    'type': 'success',
                },
            }
        except Exception as e:
            _logger.error("Profile picture sync failed: %s", e)
            raise

    def action_send_test_message(self):
        self.ensure_one()
        if not self.test_phone_number or not self.test_message_body:
            return False
        try:
            msg = self.send_message(
                self.test_phone_number,
                message_type='text',
                body=self.test_message_body,
            )
            if msg.status == 'sent':
                self.test_api_status = 'success'
            else:
                self.test_api_status = 'failed'
            self.test_api_response = msg.raw_data or msg.error_message
        except Exception as e:
            self.test_api_status = 'failed'
            self.test_api_response = str(e)

    def action_perform_api_test_calls(self):
        return self.action_test_connection()

    def action_test_sidecar(self):
        """Check whether the Node.js sidecar is reachable from Odoo."""
        self.ensure_one()
        sidecar_url = self.env['ir.config_parameter'].sudo().get_param('whatsapp.sidecar.url')
        if not sidecar_url:
            raise UserError(_("Set system parameter whatsapp.sidecar.url before testing the sidecar."))
        try:
            response = requests.get(f"{sidecar_url.rstrip('/')}/health", timeout=5)
            response.raise_for_status()
            self.write({
                'test_api_status': 'success',
                'test_api_response': response.text,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sidecar Online'),
                    'message': _('The WhatsApp sidecar responded successfully.'),
                    'type': 'success',
                },
            }
        except Exception as e:
            self.write({
                'test_api_status': 'failed',
                'test_api_response': str(e),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sidecar Unreachable'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                },
            }

    def action_create_sample_templates(self):
        """Seed the reusable template library and open it."""
        created = self.env['whatsapp.sample.template'].sudo()._seed_sample_templates()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Template Library Ready'),
                'message': _('%s sample template(s) were added.') % created if created else _('All sample templates already exist.'),
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'whatsapp.sample.template',
                    'view_mode': 'kanban,list,form',
                    'target': 'current',
                },
            },
        }
