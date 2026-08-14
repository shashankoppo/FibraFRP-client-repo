# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import copy
import requests
import json
import logging
import base64
import io
import mimetypes
import random
import secrets
from urllib.parse import quote, unquote, urlparse
from datetime import timedelta

_logger = logging.getLogger(__name__)


LEGACY_WEBHOOK_BASE_URLS = {
    'http://fibera.elsxglobal.com',
    'https://fibera.elsxglobal.com',
}
FIBERAFRP_WEBHOOK_BASE_URL = 'https://fiberafrp.com'


MEDIA_SIZE_LIMITS = {
    'image': 5 * 1024 * 1024,
    'video': 16 * 1024 * 1024,
    'audio': 16 * 1024 * 1024,
    'document': 100 * 1024 * 1024,
}

TEXT_MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024
META_PRIVATE_MEDIA_HOSTS = (
    'scontent.whatsapp.net',
    'lookaside.fbsbx.com',
    'lookaside.facebook.com',
)



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
    webhook_verify_token = fields.Char('Webhook Verify Token', default=lambda self: secrets.token_urlsafe(24))
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
    ai_brand_name = fields.Char(
        'AI Brand Name',
        help='Customer-facing name the AI should use in draft replies. Example: FiberaFRP.',
    )
    ai_reply_tone = fields.Selection([
        ('professional', 'Professional'),
        ('friendly', 'Friendly'),
        ('warm', 'Warm'),
        ('concise', 'Concise'),
        ('technical', 'Technical'),
    ], string='AI Reply Tone', default='professional')
    ai_context = fields.Text('AI Business Context', help='Tell the AI about your business, products, service rules, and escalation process.')
    ai_reply_instructions = fields.Text(
        'AI Reply Instructions',
        help='Specific rules for WhatsApp drafts: what to ask, what to avoid, when to hand off, preferred wording, and language style.',
    )
    ai_reply_signature = fields.Char(
        'AI Reply Signature',
        help='Optional short closing line/signature appended by the AI when appropriate.',
    )
    
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
    commerce_catalog_id = fields.Char(
        'Meta Catalog ID',
        help='Commerce Manager catalog connected to this WhatsApp Business account.',
    )
    commerce_default_product_retailer_id = fields.Char(
        'Default Product Retailer ID',
        help='Optional product/content ID used as the default thumbnail or single product in catalog messages.',
    )
    commerce_shop_url = fields.Char(
        'Shop / Catalogue URL',
        help='Public shop, catalogue, or website URL used by URL button steps.',
    )
    commerce_manager_url = fields.Char(
        'Commerce Manager URL',
        help='Internal Meta Commerce Manager link for admins to maintain products.',
    )
    payment_link_mode = fields.Selection([
        ('disabled', 'Disabled'),
        ('manual_url', 'Manual Payment URL'),
        ('odoo_invoice_link', 'ERP Invoice / Quote Link'),
    ], string='Payment Link Mode', default='disabled',
        help='Controls whether Inbox, Campaign, and Flow shortcuts may send payment links.')
    payment_manual_url = fields.Char(
        'Manual Payment URL',
        help='Static payment URL used when Payment Link Mode is Manual Payment URL.',
    )
    payment_link_message = fields.Text(
        'Payment Link Message',
        default='Hi {{name}}, please use this secure payment link: {{payment_url}}',
        help='Text used by Send Payment Link actions. Supported placeholders: {{name}}, {{phone}}, {{payment_url}}, {{document_name}}, {{amount}}.',
    )
    default_form_id = fields.Many2one(
        'whatsapp.form',
        string='Default WhatsApp Form',
        domain="[('active', '=', True)]",
        help='Default form used by Inbox, Campaign, and Flow Send Form Link shortcuts.',
    )
    profile_picture_url = fields.Char('Profile Picture URL')
    profile_image = fields.Image('Profile Image')
    quality_rating = fields.Char('Quality Rating', readonly=True)
    messaging_limit = fields.Char('Messaging Limit', readonly=True)
    phone_number_status = fields.Char('Phone Number Status', readonly=True)
    display_name_status = fields.Char('Display Name Status', readonly=True)
    throughput_level = fields.Char('Throughput Level', readonly=True)
    last_health_sync = fields.Datetime('Last Meta Health Sync', readonly=True)
    last_webhook_at = fields.Datetime('Last Webhook Received', readonly=True)
    last_status_webhook_at = fields.Datetime('Last Delivery Status Webhook', readonly=True)
    last_status_wamid = fields.Char('Last Status Message ID', readonly=True)
    last_inbound_webhook_at = fields.Datetime('Last Inbound Message Webhook', readonly=True)
    
    # Industrial Tier & Compliance
    opt_out_keywords = fields.Char('Opt-out Keywords', default='STOP,UNSUBSCRIBE,OFF', 
                                  help="Comma-separated keywords that trigger automatic blacklisting.")
    daily_message_count = fields.Integer('Daily Message Count', default=0, readonly=True)
    max_daily_limit = fields.Integer('Max Daily Limit', default=1000, 
                                    help="Meta messaging tier limit (e.g., 1000, 10000).")
    is_limit_reached = fields.Boolean('Limit Reached', compute='_compute_limit_reached')
    daily_limit_remaining = fields.Integer('Daily Limit Remaining', compute='_compute_limit_reached')
    daily_limit_usage_percent = fields.Float('Daily Limit Usage %', compute='_compute_limit_reached')
    
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
            max_limit = max(rec.max_daily_limit or 0, 0)
            daily_count = max(rec.daily_message_count or 0, 0)
            rec.is_limit_reached = max_limit > 0 and daily_count >= max_limit
            rec.daily_limit_remaining = max(max_limit - daily_count, 0) if max_limit else 0
            rec.daily_limit_usage_percent = round((daily_count / max_limit * 100.0), 1) if max_limit else 0.0

    def _has_daily_capacity(self):
        self.ensure_one()
        return bool(self.max_daily_limit > 0 and self.daily_message_count < self.max_daily_limit)

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
    
    @api.model
    def _normalize_webhook_base_url(self, base_url):
        base_url = (base_url or '').strip().rstrip('/')
        if base_url in LEGACY_WEBHOOK_BASE_URLS:
            return FIBERAFRP_WEBHOOK_BASE_URL
        return base_url

    @api.model
    def _get_webhook_base_url(self):
        params = self.env['ir.config_parameter'].sudo()
        base_url = (
            params.get_param('whatsapp.public.webhook.base.url')
            or params.get_param('web.base.url')
            or ''
        )
        return self._normalize_webhook_base_url(base_url)

    def _compute_webhook_url(self):
        base_url = self._get_webhook_base_url()
        db_query = quote(self.env.cr.dbname or '')
        for record in self:
            record.webhook_url = f"{base_url}/whatsapp/webhook?db={db_query}"

    def action_refresh_webhook_url(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Webhook URL Ready'),
                'message': _('Current webhook URL: %s') % self.webhook_url,
                'type': 'success',
                'sticky': True,
            },
        }

    @api.model
    def _get_default_account(self):
        """Return the configured default WhatsApp account, falling back to the first active one."""
        account = self.browse()
        context_account_id = self.env.context.get('whatsapp_seed_account_id')
        if context_account_id:
            try:
                account = self.sudo().browse(int(context_account_id)).exists()
            except (TypeError, ValueError):
                account = self.browse()
            if account and account.active:
                return account

        account_id = self.env['ir.config_parameter'].sudo().get_param('whatsapp.default.account.id')
        if account_id:
            try:
                account = self.sudo().browse(int(account_id)).exists()
            except (TypeError, ValueError):
                account = self.browse()
        if account and account.active:
            return account
        return self.sudo().search([('active', '=', True)], limit=1)

    def action_open_full_account_setup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Account Setup'),
            'res_model': 'whatsapp.account',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('elsx_whatsapp_marketing.view_whatsapp_account_form').id, 'form')],
            'target': 'current',
        }

    def _get_latest_payable_document(self, partner=False, document_type='invoice'):
        self.ensure_one()
        if not partner:
            return self.env['sale.order'] if document_type == 'quote' else self.env['account.move']
        commercial_partner = partner.commercial_partner_id or partner
        if document_type == 'quote':
            return self.env['sale.order'].sudo().search([
                ('partner_id', 'child_of', commercial_partner.id),
                ('state', 'in', ['draft', 'sent', 'sale']),
            ], order='date_order desc, id desc', limit=1)
        return self.env['account.move'].sudo().search([
            ('partner_id', 'child_of', commercial_partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment', 'reversed']),
        ], order='invoice_date_due desc, invoice_date desc, id desc', limit=1)

    def _get_payment_link(self, partner=False, invoice=False, sale_order=False, mode='account_default'):
        """Return a payment URL for safe optional WhatsApp payment-link actions."""
        self.ensure_one()
        if self.payment_link_mode == 'disabled':
            raise UserError(_("Payment links are disabled on WhatsApp account %s.") % self.display_name)

        effective_mode = mode or 'account_default'
        if effective_mode == 'account_default':
            effective_mode = 'manual_url' if self.payment_link_mode == 'manual_url' else 'latest_invoice'

        if effective_mode == 'manual_url':
            if not self.payment_manual_url:
                raise UserError(_("Set a Manual Payment URL on WhatsApp account %s before sending payment links.") % self.display_name)
            return self.payment_manual_url

        document = invoice or sale_order
        if not document and partner:
            if effective_mode == 'latest_quote':
                document = self._get_latest_payable_document(partner, document_type='quote')
            else:
                document = self._get_latest_payable_document(partner, document_type='invoice')
        if not document:
            raise UserError(_("No unpaid invoice or quotation is available for this customer. Add one first or switch the account to Manual Payment URL mode."))

        if hasattr(document, 'get_portal_url'):
            return document.get_portal_url()
        if getattr(document, 'access_url', False):
            return document.access_url
        raise UserError(_("The selected document does not expose a customer portal/payment URL."))

    def _build_payment_link_message(self, partner=False, invoice=False, sale_order=False, mode='account_default'):
        self.ensure_one()
        payment_url = self._get_payment_link(partner=partner, invoice=invoice, sale_order=sale_order, mode=mode)
        effective_mode = mode or 'account_default'
        if effective_mode == 'account_default':
            effective_mode = 'manual_url' if self.payment_link_mode == 'manual_url' else 'latest_invoice'
        if effective_mode == 'manual_url':
            document = invoice or sale_order or self.env['account.move']
        elif effective_mode == 'latest_quote':
            document = invoice or sale_order or (partner and self._get_latest_payable_document(partner, document_type='quote')) or self.env['sale.order']
        else:
            document = invoice or sale_order or (partner and self._get_latest_payable_document(partner, document_type='invoice')) or self.env['account.move']
        amount = ''
        if document:
            amount = getattr(document, 'amount_total', '') or ''
            currency = getattr(document, 'currency_id', False)
            if amount and currency:
                amount = "%s %s" % (currency.symbol or currency.name or '', amount)
        values = {
            '{{name}}': partner.display_name if partner else 'Customer',
            '{{phone}}': (partner.mobile or partner.phone) if partner else '',
            '{{payment_url}}': payment_url,
            '{{document_name}}': document.display_name if document else '',
            '{{amount}}': str(amount or ''),
        }
        body = self.payment_link_message or 'Hi {{name}}, please use this secure payment link: {{payment_url}}'
        for placeholder, value in values.items():
            body = body.replace(placeholder, value or '')
        if payment_url not in body:
            body = "%s\n%s" % (body.rstrip(), payment_url)
        return body

    @api.model
    def _normalize_meta_limit_label(self, value):
        """Return a readable limit label from Meta's old/new limit fields."""
        if value in (None, False, ''):
            return False
        if isinstance(value, dict):
            for key in (
                'messaging_limit',
                'whatsapp_business_manager_messaging_limit',
                'max_daily_conversations_per_phone',
                'limit',
                'value',
                'tier',
            ):
                if value.get(key) not in (None, False, ''):
                    return self._normalize_meta_limit_label(value.get(key))
            return json.dumps(value)

        text = str(value).strip()
        upper = text.upper()
        labels = {
            'TIER_250': '250 customers / 24h',
            'TIER_1K': '1,000 customers / 24h',
            'TIER_2K': '2,000 customers / 24h',
            'TIER_10K': '10,000 customers / 24h',
            'TIER_100K': '100,000 customers / 24h',
            'TIER_UNLIMITED': 'Unlimited',
            'UNLIMITED': 'Unlimited',
        }
        if upper in labels:
            return labels[upper]
        if text.isdigit():
            return f"{int(text):,} customers / 24h"
        return text

    @api.model
    def _extract_meta_limit_number(self, value):
        """Extract an integer sending limit when Meta exposes one."""
        if value in (None, False, ''):
            return False
        if isinstance(value, dict):
            for key in (
                'messaging_limit',
                'whatsapp_business_manager_messaging_limit',
                'max_daily_conversations_per_phone',
                'limit',
                'value',
                'tier',
            ):
                limit = self._extract_meta_limit_number(value.get(key))
                if limit:
                    return limit
            return False

        upper = str(value).strip().upper()
        tier_limits = {
            'TIER_250': 250,
            'TIER_1K': 1000,
            'TIER_2K': 2000,
            'TIER_10K': 10000,
            'TIER_100K': 100000,
            'TIER_UNLIMITED': 100000000,
            'UNLIMITED': 100000000,
        }
        if upper in tier_limits:
            return tier_limits[upper]

        digits = ''.join(ch for ch in upper.replace(',', '') if ch.isdigit())
        return int(digits) if digits else False

    def _request_phone_number_health(self):
        """Fetch phone-number health while tolerating Graph field changes."""
        self.ensure_one()
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        field_sets = [
            'display_phone_number,verified_name,quality_rating,whatsapp_business_manager_messaging_limit,status,name_status,throughput',
            'display_phone_number,verified_name,quality_rating,messaging_limit_tier,status,name_status,throughput',
            'display_phone_number,verified_name,quality_rating,status,name_status',
        ]
        last_error = False
        for fields_spec in field_sets:
            response = requests.get(url, headers=headers, params={'fields': fields_spec}, timeout=15)
            if response.status_code == 200:
                return response.json()
            last_error = response.text

        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        raise UserError(_("Meta phone-number health sync failed: %s") % (last_error or response.text or response.status_code))

    def action_sync_meta_health(self):
        """Sync quality rating, phone status, and messaging limits from Meta."""
        for account in self:
            data = account._request_phone_number_health()
            raw_limit = (
                data.get('whatsapp_business_manager_messaging_limit')
                or data.get('messaging_limit_tier')
                or data.get('messaging_limit')
            )
            limit_label = account._normalize_meta_limit_label(raw_limit)
            limit_number = account._extract_meta_limit_number(raw_limit)
            vals = {
                'quality_rating': data.get('quality_rating') or account.quality_rating,
                'phone_number_status': data.get('status') or account.phone_number_status,
                'display_name_status': data.get('name_status') or data.get('verified_name') or account.display_name_status,
                'throughput_level': account._normalize_meta_limit_label(data.get('throughput')) or account.throughput_level,
                'last_health_sync': fields.Datetime.now(),
                'status': 'connected',
            }
            if limit_label:
                vals['messaging_limit'] = limit_label
            if limit_number:
                vals['max_daily_limit'] = limit_number
            account.sudo().write(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Meta Health Synced'),
                'message': _('Quality rating, phone status, and messaging limits were refreshed.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_test_connection(self):
        """Test WhatsApp Cloud API connection"""
        self.ensure_one()
        try:
            self.action_sync_meta_health()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success!',
                    'message': 'WhatsApp account connected and Meta health synced successfully',
                    'type': 'success',
                    'sticky': False,
                }
            }
                
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
                        'meta_state': t_data.get('status'),
                        'meta_quality_rating': t_data.get('quality_score') or t_data.get('quality_rating'),
                        'meta_disabled_reason': t_data.get('disabled_reason') or t_data.get('rejected_reason'),
                        'rejection_reason': t_data.get('rejected_reason') or t_data.get('reason') or False,
                    }
                    
                    # Extract content
                    for component in t_data.get('components', []):
                        if component.get('type') == 'BODY':
                            vals['body'] = component.get('text')
                        elif component.get('type') == 'HEADER':
                            vals['header_type'] = (component.get('format') or 'none').lower()
                            if vals['header_type'] == 'text':
                                vals['header_text'] = component.get('text')
                            elif vals['header_type'] in ('image', 'video', 'document'):
                                example = component.get('example') or {}
                                header_handles = example.get('header_handle') or []
                                if isinstance(header_handles, str):
                                    header_handles = [header_handles]
                                header_example = header_handles[0] if header_handles else False
                                if header_example and str(header_example).startswith(('http://', 'https://')):
                                    vals['header_media_url'] = header_example
                                    if vals['header_type'] == 'document':
                                        current_filename = template.header_media_filename if template else False
                                        vals['header_media_filename'] = (
                                            current_filename
                                            or f"{template_name}_header.pdf"
                                        )
                        elif component.get('type') == 'FOOTER':
                            vals['footer'] = component.get('text')
                        elif component.get('type') == 'BUTTONS':
                            buttons = component.get('buttons') or []
                            vals['has_buttons'] = bool(buttons)
                            quick_replies = [btn for btn in buttons if btn.get('type') == 'QUICK_REPLY']
                            urls = [btn for btn in buttons if btn.get('type') == 'URL']
                            phones = [btn for btn in buttons if btn.get('type') == 'PHONE_NUMBER']
                            copy_codes = [btn for btn in buttons if btn.get('type') in ('OTP', 'COPY_CODE')]
                            if quick_replies:
                                vals['button_type'] = 'quick_reply'
                                for idx, button in enumerate(quick_replies[:3], start=1):
                                    vals[f'button_text_{idx}'] = button.get('text')
                            elif urls or phones:
                                vals['button_type'] = 'call_to_action'
                                if urls:
                                    vals['cta_url_text'] = urls[0].get('text')
                                    vals['cta_url_link'] = urls[0].get('url')
                                if phones:
                                    vals['cta_phone_text'] = phones[0].get('text')
                                    vals['cta_phone_number'] = phones[0].get('phone_number')
                            elif copy_codes:
                                vals['button_type'] = 'copy_code'
                    
                    if template:
                        template.write(vals)
                    else:
                        template = self.env['whatsapp.template'].create(vals)
                    template.action_refresh_variables()
                    template._log_meta_audit(
                        'sync_from_meta',
                        status=vals.get('status'),
                        reason=vals.get('rejection_reason') or vals.get('meta_disabled_reason'),
                        raw_data=t_data,
                    )
                
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
            'disabled': 'disabled',
            'paused': 'paused',
            'pending_deletion': 'rejected',
        }
        return status_map.get(status, 'draft')

    @api.model
    def _cron_reset_daily_counters(self):
        """Reset daily message counters for all accounts at midnight UTC."""
        self.search([]).write({'daily_message_count': 0})
        _logger.info("WhatsApp daily message counters reset successfully.")

    def _consume_rate_limit_token_legacy(self):
        """Consume 1 token from the bucket using atomic SQL to prevent SerializationFailure.
        
        This avoids the 'could not serialize access due to concurrent update' error
        that occurs when multiple cron jobs (broadcast queue + retry) try to ORM-write
        the same whatsapp.account row simultaneously.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        if not self.token_bucket_last_fill:
            # First-time initialization - safe to use ORM since it's a one-time write
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

    def _consume_rate_limit_token(self):
        """Consume one token without racing concurrent campaign/retry workers."""
        self.ensure_one()
        if not self._has_daily_capacity():
            return False

        now = fields.Datetime.now()
        try:
            self.env.cr.execute("""
                WITH locked_account AS (
                    SELECT
                        id,
                        COALESCE(token_bucket_level, rate_limit_capacity, 1)::float AS token_bucket_level,
                        token_bucket_last_fill,
                        GREATEST(COALESCE(NULLIF(rate_limit_capacity, 0), 1), 1)::float AS capacity,
                        GREATEST(COALESCE(rate_limit_fill_rate, 0), 0)::float AS fill_rate,
                        COALESCE(daily_message_count, 0) AS daily_message_count,
                        COALESCE(max_daily_limit, 0) AS max_daily_limit
                    FROM whatsapp_account
                    WHERE id = %s
                    FOR UPDATE SKIP LOCKED
                ),
                computed AS (
                    SELECT
                        id,
                        LEAST(
                            capacity,
                            CASE
                                WHEN token_bucket_last_fill IS NULL THEN capacity
                                ELSE token_bucket_level + (
                                    EXTRACT(EPOCH FROM (%s::timestamp - token_bucket_last_fill)) * fill_rate
                                )
                            END
                        ) AS available_level,
                        daily_message_count,
                        max_daily_limit
                    FROM locked_account
                ),
                eligible AS (
                    SELECT *
                    FROM computed
                    WHERE available_level >= 1.0
                      AND max_daily_limit > 0
                      AND daily_message_count < max_daily_limit
                )
                UPDATE whatsapp_account account
                   SET token_bucket_level = eligible.available_level - 1.0,
                       token_bucket_last_fill = %s,
                       daily_message_count = account.daily_message_count + 1,
                       write_uid = %s,
                       write_date = NOW() AT TIME ZONE 'UTC'
                  FROM eligible
                 WHERE account.id = eligible.id
             RETURNING account.id
            """, (self.id, now, now, self.env.uid))
            consumed = bool(self.env.cr.fetchone())
            self.invalidate_recordset(['token_bucket_level', 'token_bucket_last_fill', 'daily_message_count'])
            return consumed
        except Exception as exc:
            _logger.warning("Token bucket contention on account %s, will retry next cycle: %s", self.id, exc)
            return False

    @api.model
    def _is_private_meta_media_url(self, media_url):
        try:
            hostname = (urlparse(str(media_url or '').strip()).hostname or '').lower()
        except ValueError:
            return False
        return bool(
            hostname
            and (
                hostname in META_PRIVATE_MEDIA_HOSTS
                or hostname.endswith('.fbcdn.net')
                or hostname.endswith('.whatsapp.net')
            )
        )

    def _download_and_upload_private_media(self, media_url, media_type, filename=False):
        """Convert an authenticated Meta CDN URL into a reusable media ID."""
        self.ensure_one()
        media_url = str(media_url or '').strip()
        hostname = (urlparse(media_url).hostname or '').lower()
        try:
            response = requests.get(
                media_url,
                headers={'Authorization': f'Bearer {self.access_token}'},
                timeout=60,
            )
        except requests.RequestException as exc:
            raise UserError(_(
                "Could not download the temporary WhatsApp media from %(host)s. "
                "Upload the file again if the link has expired."
            ) % {'host': hostname or _('Meta')}) from exc

        if response.status_code != 200 or not response.content:
            raise UserError(_(
                "Could not download the temporary WhatsApp media from %(host)s "
                "(HTTP %(status)s). The link may have expired; upload the file again."
            ) % {
                'host': hostname or _('Meta'),
                'status': response.status_code,
            })

        content_type = (response.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
        if content_type.startswith(('application/json', 'text/html')):
            raise UserError(_(
                "Meta returned %(content_type)s instead of the media file. "
                "Upload the file again and retry."
            ) % {'content_type': content_type})

        if not filename:
            filename = unquote(urlparse(media_url).path.rsplit('/', 1)[-1]).strip()
        if not filename or len(filename) > 180 or '.' not in filename:
            extension = mimetypes.guess_extension(content_type) or {
                'image': '.jpg',
                'video': '.mp4',
                'document': '.pdf',
                'audio': '.mp3',
            }.get(media_type, '.bin')
            filename = f"whatsapp_media{extension}"

        media_id = self._upload_media_to_meta(
            base64.b64encode(response.content),
            filename,
            media_type,
        )
        if not media_id:
            raise UserError(_("Meta accepted the media upload but did not return a media ID."))
        return media_id

    def _replace_private_media_links(self, value, filename=False, uploaded=None):
        """Replace authenticated Meta links anywhere in a message payload."""
        uploaded = uploaded if uploaded is not None else {}
        if isinstance(value, list):
            for item in value:
                self._replace_private_media_links(item, filename=filename, uploaded=uploaded)
            return value
        if not isinstance(value, dict):
            return value

        for media_type in ('image', 'video', 'document', 'audio'):
            media_object = value.get(media_type)
            if not isinstance(media_object, dict):
                continue
            media_link = str(media_object.get('link') or '').strip()
            if not self._is_private_meta_media_url(media_link):
                continue
            cache_key = (media_link, media_type)
            if cache_key not in uploaded:
                uploaded[cache_key] = self._download_and_upload_private_media(
                    media_link,
                    media_type,
                    media_object.get('filename') or filename,
                )
            media_object.pop('link', None)
            media_object['id'] = uploaded[cache_key]

        for nested in value.values():
            self._replace_private_media_links(nested, filename=filename, uploaded=uploaded)
        return value

    def send_message(self, to_number, message_type='text', **kwargs):
        """
        Send WhatsApp message via Cloud API.
        Handles: text, template, image, video, document, audio, interactive.
        """
        self.ensure_one()
        to_number = self.env['whatsapp.message']._normalize_phone(to_number, account=self, strict=True)
        existing_msg = kwargs.get('existing_message')
        partner_id = kwargs.get('partner_id') or (existing_msg.partner_id.id if existing_msg and existing_msg.partner_id else False)
        campaign_id = kwargs.get('campaign_id') or (existing_msg.campaign_id.id if existing_msg and existing_msg.campaign_id else False)
        flow_id = kwargs.get('flow_id') or (existing_msg.flow_id.id if existing_msg and existing_msg.flow_id else False)
        if not existing_msg and not kwargs.get('skip_compliance'):
            self.env['whatsapp.message'].new({
                'account_id': self.id,
                'phone_number': to_number,
                'partner_id': partner_id,
                'campaign_id': campaign_id,
                'message_type': message_type,
                'direction': 'outbound',
                'is_automated': bool(kwargs.get('is_automated') or campaign_id),
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
        template_header_media_vals = {}
        
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
                template_payload = kwargs['template_record']._prepare_send_payload(
                    partner=partner,
                    record=kwargs.get('record'),
                    header_media_file=kwargs.get('header_media_file'),
                    header_media_filename=kwargs.get('header_media_filename'),
                    header_media_url=kwargs.get('header_media_url'),
                    account=self,
                    allow_missing_header_media=bool(kwargs.get('allow_missing_header_media')),
                )
            if not template_payload and kwargs.get('template_name'):
                template_payload = {
                    'name': kwargs.get('template_name'),
                    'language': {'code': kwargs.get('language_code') or kwargs.get('template_language') or 'en_US'},
                    'components': kwargs.get('components') or [],
                }
            
            if template_payload:
                template_payload = self._replace_private_media_links(
                    copy.deepcopy(template_payload),
                    filename=(
                        kwargs.get('header_media_filename')
                        or (existing_msg.media_filename if existing_msg else False)
                    ),
                )
                # Ensure components key is omitted entirely if empty for Meta API stability (Prevents 131009 error)
                if 'components' in template_payload and not template_payload['components']:
                    del template_payload['components']
                payload['template'] = template_payload
                template_record = kwargs.get('template_record')
                if template_record and hasattr(template_record, '_header_media_kwargs_from_payload'):
                    template_header_media_vals = template_record._header_media_kwargs_from_payload(template_payload)
            else:
                raise UserError(_("Template messages require a template payload, template record, or template name."))

        elif message_type == 'image':
            payload['type'] = 'image'
            if kwargs.get('media_file'):
                media_id = self._upload_media_to_meta(kwargs['media_file'], kwargs.get('media_filename', 'image'), 'image')
                payload['image'] = {'id': media_id}
            else:
                payload['image'] = kwargs.get('image') or self._prepare_media_reference(kwargs.get('media_url'), 'image', kwargs.get('media_filename'))
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
                payload['video'] = kwargs.get('video') or self._prepare_media_reference(kwargs.get('media_url'), 'video', kwargs.get('media_filename'))
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
                payload['document'] = kwargs.get('document') or self._prepare_media_reference(kwargs.get('media_url'), 'document', kwargs.get('media_filename'))
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
                payload['audio'] = kwargs.get('audio') or self._prepare_media_reference(kwargs.get('media_url'), 'audio', kwargs.get('media_filename'))

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

        biz_opaque = kwargs.get('biz_opaque_callback_data') or (f"campaign_{campaign_id}" if campaign_id else False)
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
                    'partner_id': partner_id,
                    'campaign_id': campaign_id,
                    'flow_id': flow_id,
                    'message_type': message_type,
                    'body': kwargs.get('body') or payload.get('text', {}).get('body') or f"Media: {message_type}",
                    'direction': 'outbound',
                    'status': 'queued',
                    'next_retry_at': next_retry_at,
                    'error_message': 'Rate limit exceeded; queued for retry.',
                    'raw_data': json.dumps(payload),
                }
                if message_type in ('image', 'video', 'document', 'audio'):
                    media_payload = payload.get(message_type, {})
                    queued_vals.update({
                        'media_url': media_payload.get('id') or kwargs.get('media_url') or media_payload.get('link'),
                        'media_filename': kwargs.get('media_filename'),
                        'media_mime_type': kwargs.get('media_mime_type'),
                        'caption': kwargs.get('caption'),
                    })
                    if kwargs.get('media_file'):
                        queued_vals['media_file'] = kwargs['media_file']
                elif message_type == 'template':
                    header_media_url = template_header_media_vals.get('header_media_url') or kwargs.get('header_media_url')
                    header_media_filename = (
                        kwargs.get('header_media_filename')
                        or template_header_media_vals.get('header_media_filename')
                    )
                    if header_media_url:
                        queued_vals['media_url'] = header_media_url
                    if header_media_filename:
                        queued_vals['media_filename'] = header_media_filename
                    if kwargs.get('header_media_file'):
                        queued_vals['media_file'] = kwargs['header_media_file']
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
            if partner_id:
                # We'll link the message later if successful
                pass
                
            self.env['whatsapp.api.log'].sudo().create(log_vals)

            try:
                response_data = response.json()
            except ValueError:
                response_data = {'error': {'message': response.text or 'Invalid JSON response from Meta'}}
            
            # Create local log
            body = kwargs.get('body') or (payload.get('text', {}).get('body'))
            if not body and message_type == 'template':
                template_record = kwargs.get('template_record')
                if not template_record:
                    template_name = payload.get('template', {}).get('name') or kwargs.get('template_name')
                    if template_name:
                        template_record = self.env['whatsapp.template'].sudo().search([
                            ('account_id', 'in', [False, self.id]),
                            '|',
                            ('meta_template_name', '=', template_name),
                            ('name', '=', template_name),
                        ], limit=1)
                if template_record:
                    body = template_record.body
                else:
                    body = "Template Sent"
            elif not body:
                body = f"Media: {message_type}"

            vals = {
                'account_id': self.id,
                'phone_number': to_number,
                'partner_id': partner_id,
                'campaign_id': campaign_id,
                'flow_id': flow_id,
                'message_type': message_type,
                'body': body,
                'template_name': payload.get('template', {}).get('name') if message_type == 'template' else False,
                'direction': 'outbound',
                'raw_data': json.dumps(payload),
            }
            if message_type == 'interactive':
                interactive_payload = payload.get('interactive', {})
                action_payload = interactive_payload.get('action', {}) if isinstance(interactive_payload, dict) else {}
                action_parameters = action_payload.get('parameters', {}) if isinstance(action_payload, dict) else {}
                vals.update({
                    'interactive_type': interactive_payload.get('type'),
                    'button_text': action_parameters.get('display_text'),
                    'button_url': action_parameters.get('url'),
                    'catalog_id': action_payload.get('catalog_id'),
                    'product_retailer_id': (
                        action_payload.get('product_retailer_id')
                        or action_parameters.get('thumbnail_product_retailer_id')
                    ),
                })
                if interactive_payload.get('type') == 'product_list':
                    product_ids = []
                    sections = action_payload.get('sections', [])
                    if not isinstance(sections, list):
                        sections = []
                    for section in sections:
                        product_items = section.get('product_items', []) if isinstance(section, dict) else []
                        if not isinstance(product_items, list):
                            product_items = []
                        for item in product_items:
                            if isinstance(item, dict) and item.get('product_retailer_id'):
                                product_ids.append(item['product_retailer_id'])
                    vals['product_retailer_id'] = ','.join(product_ids)
            template_record = kwargs.get('template_record')
            if template_record:
                vals['template_id'] = template_record.id
            if message_type in ('image', 'video', 'document', 'audio'):
                media_payload = payload.get(message_type, {})
                vals.update({
                    'media_url': media_payload.get('id') or kwargs.get('media_url') or media_payload.get('link') or (existing_msg.media_url if existing_msg else False),
                    'media_filename': kwargs.get('media_filename') or (existing_msg.media_filename if existing_msg else False),
                    'media_mime_type': kwargs.get('media_mime_type') or (existing_msg.media_mime_type if existing_msg else False),
                    'caption': kwargs.get('caption') or (existing_msg.caption if existing_msg else False),
                })
                if kwargs.get('media_file'):
                    vals['media_file'] = kwargs['media_file']
            elif message_type == 'template':
                header_media_url = template_header_media_vals.get('header_media_url') or kwargs.get('header_media_url')
                header_media_filename = (
                    kwargs.get('header_media_filename')
                    or template_header_media_vals.get('header_media_filename')
                )
                if header_media_url:
                    vals['media_url'] = header_media_url
                if header_media_filename:
                    vals['media_filename'] = header_media_filename
                if kwargs.get('header_media_file'):
                    vals['media_file'] = kwargs['header_media_file']

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
                error = response_data.get('error', {})
                error_code = error.get('code')
                message_model = self.env['whatsapp.message']
                error_msg = message_model._format_meta_error(error)
                
                _logger.error(f"WhatsApp send failed (Code {error_code}): {error_msg}")
                
                vals.update({
                    'status': 'failed',
                    'error_message': error_msg,
                })
                retryable_codes = {4, 17, 32, 613, 130429, 131048, 131056}
                retryable = (
                    not message_model._is_non_retryable_meta_error_code(error_code)
                    and (
                        response.status_code in (408, 425, 429, 500, 502, 503, 504)
                        or error_code in retryable_codes
                    )
                )
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
                        'partner_id': partner_id,
                        'campaign_id': campaign_id,
                        'flow_id': flow_id,
                        'message_type': message_type,
                        'body': kwargs.get('body') or payload.get('text', {}).get('body') or f"Media: {message_type}",
                        'template_name': payload.get('template', {}).get('name') if message_type == 'template' else False,
                        'direction': 'outbound',
                        'status': 'failed',
                        'error_message': str(e),
                        'raw_data': json.dumps(payload),
                    })
                except Exception:
                    _logger.exception("Failed to create failed-send message log for account %s", self.id)
            raise

    def _prepare_media_reference(self, media_reference, media_type, filename=False):
        if not media_reference:
            raise UserError(_("Please provide a media file, Meta media ID, or public HTTPS media URL for %s messages.") % media_type)
        media_reference = str(media_reference).strip()
        if media_reference.startswith('http://'):
            raise UserError(_("WhatsApp media links must use HTTPS."))
        if media_reference.startswith('https://'):
            if self._is_private_meta_media_url(media_reference):
                return {
                    'id': self._download_and_upload_private_media(
                        media_reference,
                        media_type,
                        filename,
                    )
                }
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
            'type': mime_type
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

    def _upload_template_sample_media_handle(self, binary_data, filename, media_type):
        """Upload media for Meta template approval and return a header_handle.

        WhatsApp message sending uses /PHONE_NUMBER_ID/media and returns a media ID.
        Template approval examples use Meta's resumable upload API and return a
        header handle. Using the normal media ID as header_handle causes Meta
        error [131009] "Parameter value is not valid".
        """
        self.ensure_one()
        if not self.app_id:
            raise UserError(_(
                "Meta App ID is required to submit image/video/document header templates. "
                "Open the WhatsApp Account and fill App ID under API Configuration."
            ))

        file_content = self._check_media_upload_size(binary_data, media_type, filename)
        if not filename:
            extension = {
                'image': 'jpg',
                'video': 'mp4',
                'document': 'pdf',
            }.get(media_type, 'bin')
            filename = f"template_sample_{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"

        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = {
                'image': 'image/jpeg',
                'video': 'video/mp4',
                'document': 'application/pdf',
            }.get(media_type, 'application/octet-stream')

        upload_url = f"https://graph.facebook.com/{self.api_version}/{self.app_id}/uploads"
        params = {
            'file_name': filename,
            'file_length': len(file_content),
            'file_type': mime_type,
            'access_token': self.access_token,
        }
        start_response = requests.post(upload_url, params=params, timeout=30)
        start_data = start_response.json() if start_response.content else {}
        if start_response.status_code not in (200, 201) or not start_data.get('id'):
            error_msg = start_data.get('error', {}).get('message') or 'Could not start template media upload.'
            _logger.error("Meta template media upload start failed: %s", start_data)
            raise UserError(_("Template media upload failed: %s") % error_msg)

        upload_id = start_data['id']
        finish_url = f"https://graph.facebook.com/{self.api_version}/{upload_id}"
        finish_headers = {
            'Authorization': f'OAuth {self.access_token}',
            'file_offset': '0',
            'Content-Type': 'application/octet-stream',
        }
        finish_response = requests.post(finish_url, headers=finish_headers, data=file_content, timeout=60)
        finish_data = finish_response.json() if finish_response.content else {}
        media_handle = finish_data.get('h') or finish_data.get('handle')
        if finish_response.status_code not in (200, 201) or not media_handle:
            error_msg = finish_data.get('error', {}).get('message') or 'Could not finish template media upload.'
            _logger.error("Meta template media upload finish failed: %s", finish_data)
            raise UserError(_("Template media upload failed: %s") % error_msg)
        return media_handle

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
                limit_value = d.get('messaging_limit_tier')
                self.messaging_limit = self._normalize_meta_limit_label(limit_value)
                limit_number = self._extract_meta_limit_number(limit_value)
                if limit_number:
                    self.max_daily_limit = limit_number
            try:
                self.action_sync_meta_health()
            except Exception as health_error:
                _logger.info("Meta health sync skipped after profile fetch: %s", health_error)
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
        """Check whether the Node.js sidecar is reachable from ERP."""
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
                    'views': [(False, 'kanban'), (False, 'list'), (False, 'form')],
                    'target': 'current',
                },
            },
        }

    def action_initialize_whatsapp_defaults(self):
        """Rerunnable fresh-database starter setup for the selected WhatsApp account."""
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        if not params.get_param('whatsapp.default.account.id'):
            params.set_param('whatsapp.default.account.id', str(self.id))

        setup_context = dict(self.env.context, whatsapp_seed_account_id=self.id)
        sample_templates = self.env['whatsapp.sample.template'].with_context(setup_context).sudo()._seed_sample_templates()
        production_forms = self.env['whatsapp.form'].with_context(setup_context).sudo()._seed_fiberafrp_production_forms()
        assistant_flow = self.env['whatsapp.bot.flow'].with_context(setup_context).sudo()._seed_fiberafrp_assistant_flow()
        advanced_flows = self.env['whatsapp.bot.flow'].with_context(setup_context).sudo()._seed_fiberafrp_advanced_business_flows()

        flow_count = len(advanced_flows)
        if assistant_flow:
            flow_count += 1
        template_count = sample_templates if isinstance(sample_templates, int) else len(sample_templates)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WhatsApp Setup Ready'),
                'message': _(
                    'Initialized defaults for %(account)s: %(templates)s template(s), %(forms)s form(s), and %(flows)s flow(s).',
                ) % {
                    'account': self.display_name,
                    'templates': template_count,
                    'forms': len(production_forms),
                    'flows': flow_count,
                },
                'type': 'success',
                'sticky': False,
            },
        }
