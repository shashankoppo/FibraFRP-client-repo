# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Sidecar Real-Time Settings
    whatsapp_sidecar_url = fields.Char(
        string='Real-time Sidecar URL',
        config_parameter='whatsapp.sidecar.url',
        help="URL of the Node.js zero-latency WebSocket server (e.g. http://node_sidecar:3000)"
    )
    whatsapp_sidecar_secret = fields.Char(
        string='Sidecar Secret Key',
        config_parameter='whatsapp.sidecar.secret',
        help="Secret key used to authenticate requests between Odoo and the Node sidecar"
    )
    whatsapp_runtime_enabled = fields.Boolean(
        string='Enable WhatsApp Runtime',
        default=True,
        config_parameter='whatsapp.runtime.enabled',
        help="Compatibility switch for older settings views. Keep enabled for normal WhatsApp operation."
    )
    whatsapp_ui_version = fields.Selection([
        ('legacy', 'Legacy'),
        ('v2', 'V2'),
    ],
        string='WhatsApp UI Version',
        default='legacy',
        config_parameter='whatsapp.ui.version',
        help="Compatibility setting for databases that still have older WhatsApp V2 settings metadata. Keep Legacy for this rolled-back UI.",
    )
    whatsapp_realtime_mode = fields.Selection([
        ('bus', 'Odoo Bus'),
        ('socket', 'Sidecar Socket'),
        ('polling_fallback', 'Polling Fallback Only'),
    ], string='Realtime Mode', default='bus', config_parameter='whatsapp.realtime.mode',
        help="Use Odoo Bus by default. Sidecar Socket is optional and only used when explicitly enabled.")
    whatsapp_history_initial_limit = fields.Integer(
        string='Initial Chat History Limit',
        default=50,
        config_parameter='whatsapp.history.initial.limit',
        help="Number of latest messages rendered when opening a chat. Older messages remain available through Load Older."
    )
    whatsapp_dashboard_refresh_seconds = fields.Integer(
        string='Dashboard Refresh Seconds',
        default=30,
        config_parameter='whatsapp.dashboard.refresh.seconds',
        help="Automatic WhatsApp dashboard refresh interval. Set 0 to disable auto-refresh."
    )
    whatsapp_dashboard_cache_minutes = fields.Integer(
        string='Dashboard Cache Minutes',
        default=5,
        config_parameter='whatsapp.dashboard.cache.minutes',
        help="How long heavy dashboard charts and leaderboard sections can use cached data in hybrid mode."
    )
    whatsapp_form_rate_limit_seconds = fields.Integer(
        string='Public Form Rate Limit Seconds',
        default=5,
        config_parameter='whatsapp.form.rate_limit.seconds',
        help="Minimum seconds between public form submissions from the same browser session."
    )
    whatsapp_form_max_upload_mb = fields.Integer(
        string='Public Form Max Upload MB',
        default=10,
        config_parameter='whatsapp.form.max_upload.mb',
        help="Maximum size per file uploaded through public WhatsApp forms."
    )
    whatsapp_ui_motion_enabled = fields.Boolean(
        string='Enable WhatsApp UI Motion',
        default=True,
        config_parameter='whatsapp.ui.motion.enabled',
        help="Enable subtle local UI animations on custom WhatsApp screens. Disabled automatically for reduced-motion users."
    )
    whatsapp_ui_motion_level = fields.Selection([
        ('off', 'Off'),
        ('subtle', 'Subtle'),
        ('standard', 'Standard'),
    ], string='WhatsApp UI Motion Level', default='subtle',
        config_parameter='whatsapp.ui.motion.level',
        help="Controls animation intensity for custom WhatsApp screens only."
    )

    # General Preferences
    whatsapp_default_account_id = fields.Many2one(
        'whatsapp.account',
        string='Default WhatsApp Account',
        config_parameter='whatsapp.default.account.id',
        help="The default account used for outbound messages if none is specified"
    )
    whatsapp_default_quality_rating = fields.Char(
        string='Default Account Quality',
        related='whatsapp_default_account_id.quality_rating',
        readonly=True,
    )
    whatsapp_default_messaging_limit = fields.Char(
        string='Default Account Meta Limit',
        related='whatsapp_default_account_id.messaging_limit',
        readonly=True,
    )
    whatsapp_default_daily_usage = fields.Float(
        string='Default Account Daily Usage %',
        related='whatsapp_default_account_id.daily_limit_usage_percent',
        readonly=True,
    )
    whatsapp_default_remaining_limit = fields.Integer(
        string='Default Account Remaining Today',
        related='whatsapp_default_account_id.daily_limit_remaining',
        readonly=True,
    )

    whatsapp_crm_won_template_id = fields.Many2one(
        'whatsapp.template',
        string='CRM Won Template',
        config_parameter='whatsapp.crm.won.template.id',
        help="Template to send automatically when a CRM Opportunity is marked as Won."
    )

    # Automation & Bots
    whatsapp_enable_bot = fields.Boolean(
        string='Enable Bot Engine',
        config_parameter='whatsapp.enable.bot',
        default=True,
        help="If enabled, incoming messages will be processed by the Bot Engine before being assigned to agents."
    )

    # Invoicing Integration
    whatsapp_invoice_auto_send = fields.Boolean(
        string='Auto-send Invoice on Post',
        config_parameter='whatsapp.invoice.auto.send',
        default=False,
        help="Automatically send a WhatsApp message when a customer invoice is posted."
    )
    whatsapp_invoice_auto_remind = fields.Boolean(
        string='Auto-send Overdue Reminders',
        config_parameter='whatsapp.invoice.auto.remind',
        default=False,
        help="Automatically send reminder messages for overdue invoices via cron."
    )
    whatsapp_invoice_reminder_days = fields.Integer(
        string='Reminder Frequency (Days)',
        config_parameter='whatsapp.invoice.reminder.days',
        default=3,
        help="Number of days between automated overdue invoice reminders."
    )
    whatsapp_invoice_default_template_id = fields.Many2one(
        'whatsapp.template',
        string='Default Invoice Template',
        config_parameter='whatsapp.invoice.default.template.id',
        domain=[('status', '=', 'approved'), ('category', 'in', ['utility', 'marketing'])],
        help="Default template to use when sending invoices via WhatsApp."
    )

    # Compliance & Retention
    whatsapp_retention_days = fields.Integer(
        string='Message Retention (Days)',
        config_parameter='whatsapp.retention.days',
        default=365,
        help="Number of days to keep message history before automatic archival/deletion. 0 means keep forever."
    )
    elsx_ai_enabled = fields.Boolean(
        string='Enable ELSX AI',
        config_parameter='elsx_ai.enabled',
        default=False,
        help="Keep disabled until provider tests pass. AI creates auditable drafts and jobs only."
    )
    elsx_ai_auto_write = fields.Boolean(
        string='Allow AI Auto-write',
        config_parameter='elsx_ai.auto_write',
        default=False,
        help="When disabled, AI output must be reviewed and manually applied."
    )
    elsx_ai_default_provider_id = fields.Many2one(
        'elsx.ai.provider',
        string='Default AI Provider',
        config_parameter='elsx_ai.default_provider_id',
        help="Provider used by CRM, WhatsApp, OCR, and campaign draft jobs."
    )
    elsx_ai_default_model = fields.Char(
        string='Default AI Model',
        config_parameter='elsx_ai.default_model',
        help="Fallback model name used when the selected provider does not define a default model."
    )
    whatsapp_ai_draft_enabled = fields.Boolean(
        string='Enable WhatsApp AI Drafts',
        config_parameter='whatsapp.ai.draft.enabled',
        default=True,
        help="Allow AI to prepare reply, campaign, template, and flow suggestions. Output stays draft-only."
    )
    whatsapp_ai_auto_send = fields.Boolean(
        string='Allow WhatsApp AI Auto-send',
        config_parameter='whatsapp.ai.auto_send',
        default=False,
        help="Safety guard. Keep disabled: AI should not send customer WhatsApp messages automatically."
    )

    def action_sync_all_whatsapp_contacts(self):
        """One-time synchronization from res.partner to whatsapp.contact"""
        Partner = self.env['res.partner'].sudo()
        domain = [('active', '=', True)]
        if 'mobile' in Partner._fields:
            domain.extend(['|', ('phone', '!=', False), ('mobile', '!=', False)])
        else:
            domain.append(('phone', '!=', False))
        partners = Partner.search(domain)

        synced_count = 0
        for partner in partners:
            phone = getattr(partner, 'mobile', False) or partner.phone
            if not phone:
                continue

            normalized_phone = phone
            try:
                account = self.env['whatsapp.account'].sudo()._get_default_account()
                normalized_phone = self.env['whatsapp.message']._normalize_phone(phone, account=account)
            except Exception:
                normalized_phone = ''.join(c for c in phone if c.isdigit())

            if not normalized_phone:
                continue

            WhatsAppContact = self.env['whatsapp.contact'].sudo()
            contact = WhatsAppContact.search([
                '|', ('partner_id', '=', partner.id), ('phone_number', '=', normalized_phone)
            ], limit=1)

            contact_vals = {
                'name': partner.name,
                'phone_number': normalized_phone,
                'partner_id': partner.id,
                'opt_in': partner.whatsapp_opt_in,
            }

            if contact:
                update_vals = {}
                if contact.name != partner.name:
                    update_vals['name'] = partner.name
                if contact.phone_number != normalized_phone:
                    update_vals['phone_number'] = normalized_phone
                if contact.partner_id != partner:
                    update_vals['partner_id'] = partner.id
                if contact.opt_in != partner.whatsapp_opt_in:
                    update_vals['opt_in'] = partner.whatsapp_opt_in
                if update_vals:
                    contact.with_context(skip_partner_sync=True).write(update_vals)
            else:
                WhatsAppContact.with_context(skip_partner_sync=True).create(contact_vals)
            synced_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Completed',
                'message': f'Successfully synchronized {synced_count} contacts to WhatsApp Contacts.',
                'type': 'success',
            }
        }

    def action_sync_default_whatsapp_account_health(self):
        self.ensure_one()
        if not self.whatsapp_default_account_id:
            return False
        return self.whatsapp_default_account_id.action_sync_meta_health()

    def action_capture_whatsapp_health_snapshot(self):
        return self.env['whatsapp.diagnostic.snapshot'].action_capture_now()
