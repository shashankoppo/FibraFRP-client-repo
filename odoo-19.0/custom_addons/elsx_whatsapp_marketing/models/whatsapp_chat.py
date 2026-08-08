# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
import logging
import json
from markupsafe import Markup, escape

_logger = logging.getLogger(__name__)

class WhatsAppChat(models.Model):
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc nulls last, id desc'
    _rec_name = 'display_name'

    _account_phone_idx = models.Index("(account_id, phone_number)")
    _inbox_state_idx = models.Index("(state, is_archived, assigned_user_id, last_message_date)")

    @api.model
    def _get_or_create_chat(self, account_id, phone_number, reopen=True):
        """Find or create a conversation for a specific phone number and account.

        Args:
            account_id: WhatsApp account ID
            phone_number: Customer phone number
            reopen: If True (default), re-opens resolved/archived chats.
                    Set to False for campaign/bulk sends to avoid disrupting resolved conversations.
        """
        if not account_id or not phone_number:
            return False

        if hasattr(account_id, 'id'):
            account_id = account_id.id

        # Standardize the phone number format to avoid duplicate chat creation
        phone_number = self.env['whatsapp.message']._normalize_phone(phone_number, account=self.env['whatsapp.account'].browse(account_id), strict=False)

        chat = self.search([
            ('account_id', '=', account_id),
            ('phone_number', '=', phone_number)
        ], limit=1)

        if not chat:
            chat = self.create({
                'account_id': account_id,
                'phone_number': phone_number,
                'state': 'open',
            })
            # Trigger Industrial Auto-Assignment
            chat._auto_assign_agent()
        else:
            # Un-archive if the chat was previously resolved/archived
            # (skip for campaign sends to avoid disrupting resolved conversations)
            if reopen and (chat.is_archived or chat.state in ('snoozed', 'resolved')):
                chat.sudo().write({'state': 'open', 'is_archived': False})
        return chat

    @api.model
    def _message_order_key(self, message):
        """Stable chronological order for messages created within the same second."""
        fallback_date = fields.Datetime.to_datetime('1970-01-01 00:00:00')
        return (message.create_date or fallback_date, message.id or 0)

    # --- CORE FIELDS ---
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact')
    # No default — new chats start as "Unassigned" and appear in the Unassigned pane.
    # The _auto_assign_agent() method handles real agent routing.
    # Previously defaulted to self.env.user, which was the bot user for webhook-created chats.
    assigned_user_id = fields.Many2one('res.users', string='Assigned Agent', index=True)
    phone_number = fields.Char('Phone Number', required=True)
    whatsapp_profile_name = fields.Char('WA Profile Name', readonly=True)
    whatsapp_profile_about = fields.Char('WA About', readonly=True)

    state = fields.Selection([
        ('open', 'Open'),
        ('snoozed', 'Snoozed'),
        ('resolved', 'Resolved')
    ], string='Status', default='open', index=True)

    chat_type = fields.Selection([
        ('individual', 'Individual'),
        ('group', 'Group')
    ], string='Chat Type', default='individual')

    is_archived = fields.Boolean('Archived', default=False)
    is_pinned = fields.Boolean('Pinned', default=False)
    # --- CHAT CATEGORIES (AiSensy‑style three‑pane) ---
    active_chat_ids = fields.Many2many('whatsapp.chat', compute='_compute_chat_categories', string='Active Chats')
    request_chat_ids = fields.Many2many('whatsapp.chat', compute='_compute_chat_categories', string='Requesting Chats')
    intervened_chat_ids = fields.Many2many('whatsapp.chat', compute='_compute_chat_categories', string='Intervened Chats')

    # --- COMPUTED UI FIELDS ---
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    display_name_initial = fields.Char('Initial', compute='_compute_display_name_initial')

    message_ids = fields.One2many('whatsapp.message', 'chat_id_ref', string='Messages')
    last_message_date = fields.Datetime('Last Message Date', compute='_compute_last_message', store=True)
    last_message_body = fields.Text('Last Message', compute='_compute_last_message', store=True)
    last_message_status = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('deleted', 'Deleted'),
    ], string='Last Message Status', compute='_compute_last_message', store=True)
    last_message_direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Last Message Direction', compute='_compute_last_message', store=True)

    unread_count = fields.Integer('Unread Count', compute='_compute_unread_count', store=True)
    partner_has_avatar = fields.Boolean('Has Contact Avatar', compute='_compute_partner_profile_data')
    last_inbound_date = fields.Datetime('Last Customer Message', compute='_compute_last_inbound', store=True)

    # CRM Integration
    lead_id = fields.Many2one('crm.lead', string='Active Lead', compute='_compute_lead', store=True)
    lead_state = fields.Char(related='lead_id.stage_id.name', string='Lead Stage', readonly=True)
    sale_order_count = fields.Integer(compute='_compute_crm_stats')
    invoice_count = fields.Integer(compute='_compute_crm_stats')

    partner_id_email = fields.Char(related='partner_id.email', string='Email', readonly=True)
    partner_job_title = fields.Char(related='partner_id.function', string='Job Title', readonly=True)
    partner_website = fields.Char(related='partner_id.website', string='Website', readonly=True)

    # Session Management (canonical field — also declared below via alias, kept for backward compat)
    session_open = fields.Boolean('24h Session Open', compute='_compute_session_status')

    # SLA Tracking
    sla_status = fields.Selection([
        ('active', 'Active'),
        ('breached', 'Breached'),
        ('met', 'Met')
    ], string='SLA Status', compute='_compute_sla_status')
    sla_timer_minutes = fields.Integer('Wait Time (Mins)', compute='_compute_sla_status')

    needs_reply = fields.Boolean('Needs Reply', compute='_compute_needs_reply', store=True)

    @api.depends('message_ids.direction', 'message_ids.create_date')
    def _compute_needs_reply(self):
        for record in self:
            last = record.message_ids.sorted(key=self._message_order_key, reverse=True)[:1]
            if last and last.direction == 'inbound':
                record.needs_reply = True
            else:
                record.needs_reply = False

    @api.depends('last_inbound_date')
    def _compute_session_status(self):
        now = fields.Datetime.now()
        for record in self:
            if record.last_inbound_date:
                diff = now - record.last_inbound_date
                record.session_open = diff.total_seconds() < 86400
            else:
                record.session_open = False

    def _compute_sla_status(self):
        now = fields.Datetime.now()
        for record in self:
            last_inbound = record.message_ids.filtered(
                lambda m: m.direction == 'inbound'
            ).sorted(key=self._message_order_key, reverse=True)[:1]
            last_outbound = record.message_ids.filtered(
                lambda m: m.direction == 'outbound'
            ).sorted(key=self._message_order_key, reverse=True)[:1]

            if last_inbound:
                if last_outbound and self._message_order_key(last_outbound) > self._message_order_key(last_inbound):
                    record.sla_status = 'met'
                    record.sla_timer_minutes = 0
                else:
                    diff = now - last_inbound.create_date
                    mins = diff.total_seconds() / 60
                    record.sla_timer_minutes = int(mins)
                    if mins > 15:  # 15 minute SLA threshold
                        record.sla_status = 'breached'
                    else:
                        record.sla_status = 'active'
            else:
                record.sla_status = 'met'
                record.sla_timer_minutes = 0

    def _compute_crm_stats(self):
        for record in self:
            if record.partner_id:
                record.sale_order_count = self.env['sale.order'].sudo().search_count([('partner_id', '=', record.partner_id.id)])
                record.invoice_count = self.env['account.move'].sudo().search_count([
                    ('partner_id', '=', record.partner_id.id),
                    ('move_type', '=', 'out_invoice')
                ])
            else:
                record.sale_order_count = 0
                record.invoice_count = 0

    # Input Area
    quick_reply_text = fields.Text('Quick Reply')
    quick_media_file = fields.Binary('Quick Attachment')
    quick_media_filename = fields.Char('Quick Filename')
    quick_template_id = fields.Many2one('whatsapp.template', string='Template')
    quick_template_preview_html = fields.Html('Template Preview', compute='_compute_quick_template_preview_html')
    quick_template_preview_text = fields.Text('Template Preview Text', compute='_compute_quick_template_preview_text')
    quick_form_id = fields.Many2one(
        'whatsapp.form',
        string='Quick Form',
        domain="[('active', '=', True)]",
        help='Optional form sent through the Send Form shortcut. If empty, the account default form is used.',
    )
    quick_invoice_id = fields.Many2one(
        'account.move',
        string='Payment Invoice',
        domain="[('partner_id', '=', partner_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'not in', ['paid', 'in_payment', 'reversed'])]",
        help='Optional invoice used by Send Payment Link. If empty, the latest unpaid invoice/quote is used.',
    )
    quick_sale_order_id = fields.Many2one(
        'sale.order',
        string='Payment Quotation',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['draft', 'sent', 'sale'])]",
        help='Optional quotation/order used by Send Payment Link when no invoice is selected.',
    )
    quick_action_help_text = fields.Text('Shortcut Guidance', compute='_compute_quick_action_help_text')
    ai_suggested_reply = fields.Text('AI Suggested Reply', readonly=True)
    ai_intent = fields.Char('AI Intent', readonly=True)
    ai_sentiment = fields.Selection([
        ('positive', 'Positive'),
        ('neutral', 'Neutral'),
        ('negative', 'Negative'),
    ], string='AI Sentiment', readonly=True)
    ai_urgency = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
    ], string='AI Urgency', readonly=True)
    ai_summary = fields.Text('AI Summary', readonly=True)
    ai_suggested_tags = fields.Char('AI Suggested Tags', readonly=True)
    ai_next_action = fields.Char('AI Next Action', readonly=True)
    ai_suggested_flow_id = fields.Many2one('whatsapp.bot.flow', string='AI Suggested Flow', readonly=True)
    ai_guidance_html = fields.Html('AI Draft Guidance', compute='_compute_ai_guidance_html', sanitize=False)

    # Metadata
    tag_ids = fields.Many2many('res.partner.category', string='Labels')
    note_ids = fields.One2many('whatsapp.chat.note', 'chat_id', string='Internal Notes')
    source_campaign_id = fields.Many2one('whatsapp.campaign', string='First Source Campaign', readonly=True)
    source_keyword = fields.Char('First Entry Keyword', readonly=True)
    source_medium = fields.Char('First Source Medium', readonly=True)
    source_first_message_id = fields.Many2one('whatsapp.message', string='First Source Message', readonly=True)
    # session_open already declared above — removed duplicate

    # Related Fields
    partner_avatar_128 = fields.Image(related='partner_id.avatar_128', readonly=True)

    # --- COMPUTE METHODS ---

    @api.depends('phone_number', 'partner_id.name', 'whatsapp_profile_name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.whatsapp_profile_name or (record.partner_id.name if record.partner_id else False) or record.phone_number

    @api.depends('display_name')
    def _compute_display_name_initial(self):
        for record in self:
            name = record.display_name or '?'
            record.display_name_initial = name[0].upper()

    @api.depends('state')
    def _compute_chat_categories(self):
        """Populate the three pane Many2many fields with chats grouped by state.
        This is a simple implementation for UI rendering.
        Note: The modern UI implementation (JS) manages its own lists via API routes,
        so this logic has been optimized to prevent N+1 queries.
        """
        for rec in self:
            rec.active_chat_ids = False
            rec.request_chat_ids = False
            rec.intervened_chat_ids = False

    @api.depends('message_ids.create_date', 'message_ids.body', 'message_ids.status', 'message_ids.direction', 'message_ids.message_type')
    def _compute_last_message(self):
        for record in self:
            last = record.message_ids.sorted(key=self._message_order_key, reverse=True)[:1]
            if last:
                record.last_message_date = last.create_date
                record.last_message_body = last.body or (f"<{last.message_type}>" if last.message_type != 'text' else "")
                record.last_message_status = last.status
                record.last_message_direction = last.direction
            else:
                record.last_message_date = False
                record.last_message_body = False
                record.last_message_status = False
                record.last_message_direction = False

    last_message_date_str = fields.Char('Last Message Time', compute='_compute_last_message_date_str')

    @api.depends('last_message_date')
    def _compute_last_message_date_str(self):
        import datetime
        import pytz
        for record in self:
            if not record.last_message_date:
                record.last_message_date_str = ''
                continue

            user_tz = pytz.timezone(self.env.user.tz or 'UTC')
            dt = pytz.utc.localize(record.last_message_date).astimezone(user_tz)
            now = datetime.datetime.now(user_tz)

            if dt.date() == now.date():
                _h = dt.strftime('%I').lstrip('0') or '12'
                _min = dt.strftime('%M')
                _ampm = dt.strftime('%p')
                record.last_message_date_str = f"{_h}:{_min} {_ampm}"
            elif dt.date() == (now - datetime.timedelta(days=1)).date():
                record.last_message_date_str = 'Yesterday'
            else:
                record.last_message_date_str = dt.strftime('%d/%m/%Y')

    @api.depends('message_ids', 'message_ids.status', 'message_ids.direction')
    def _compute_unread_count(self):
        for record in self:
            record.unread_count = self.env['whatsapp.message'].search_count([
                ('chat_id_ref', '=', record.id),
                ('direction', '=', 'inbound'),
                ('status', '!=', 'read')
            ])

    def action_mark_read(self):
        """Mark all unread inbound messages in this chat as read and trigger Meta Cloud API read receipt."""
        for chat in self:
            unread_msgs = self.env['whatsapp.message'].search([
                ('chat_id_ref', '=', chat.id),
                ('direction', '=', 'inbound'),
                ('status', '!=', 'read')
            ])
            if unread_msgs:
                unread_msgs.write({'status': 'read', 'read_date': fields.Datetime.now()})
                chat.unread_count = 0

                # Send Meta WABA Read Receipt for the latest message
                latest_msg = unread_msgs.sorted('create_date', reverse=True)[:1]
                if latest_msg and latest_msg.message_id and chat.account_id:
                    import requests
                    url = f"https://graph.facebook.com/{chat.account_id.api_version}/{chat.account_id.phone_number_id}/messages"
                    headers = {
                        'Authorization': f'Bearer {chat.account_id.access_token}',
                        'Content-Type': 'application/json'
                    }
                    payload = {
                        "messaging_product": "whatsapp",
                        "status": "read",
                        "message_id": latest_msg.message_id
                    }
                    try:
                        # Fire and forget (timeout=2)
                        requests.post(url, headers=headers, json=payload, timeout=2)
                    except Exception as e:
                        _logger.warning(f"[WABA] Failed to send read receipt to Meta: {e}")
        return True

    @api.depends('message_ids', 'message_ids.create_date', 'message_ids.direction')
    def _compute_last_inbound(self):
        for record in self:
            last = record.message_ids.filtered(
                lambda m: m.direction == 'inbound'
            ).sorted(key=self._message_order_key, reverse=True)[:1]
            record.last_inbound_date = last.create_date if last else False

    def _compute_partner_profile_data(self):
        for record in self:
            record.partner_has_avatar = bool(record.partner_id.avatar_128) if record.partner_id else False

    @api.depends('partner_id', 'phone_number')
    def _compute_lead(self):
        Lead = self.env['crm.lead'].sudo()
        for record in self:
            if record.partner_id:
                lead = Lead.search([
                    ('partner_id', '=', record.partner_id.id),
                    ('active', '=', True)
                ], order='create_date desc', limit=1)
                record.lead_id = lead.id if lead else False
            elif record.phone_number:
                phone_domain = [('phone', '=', record.phone_number)]
                if 'mobile' in Lead._fields:
                    phone_domain = ['|', ('phone', '=', record.phone_number), ('mobile', '=', record.phone_number)]
                lead = Lead.search([('active', '=', True)] + phone_domain, order='create_date desc', limit=1)
                record.lead_id = lead.id if lead else False
            else:
                record.lead_id = False

    def _sync_message_to_lead_chatter(self, message):
        """Mirror a new WhatsApp message into the linked CRM lead chatter."""
        for chat in self:
            if not message:
                continue

            lead = chat.lead_id
            if not lead and chat.partner_id:
                lead = self.env['crm.lead'].sudo().search([
                    ('partner_id', '=', chat.partner_id.id),
                    ('active', '=', True),
                ], order='create_date desc', limit=1)
            if not lead:
                continue

            marker = f'href="#wa-message-id-{message.id}"'
            already_posted = self.env['mail.message'].sudo().search_count([
                ('model', '=', 'crm.lead'),
                ('res_id', '=', lead.id),
                ('body', 'ilike', marker),
            ])
            if already_posted:
                continue

            sender = message.partner_id.display_name or chat.display_name or message.phone_number
            content = message.body or message.caption or f"[{message.message_type}]"
            content_html = Markup('<br/>').join(escape(line) for line in content.splitlines()) or Markup('&nbsp;')

            direction_label = "inbound from" if message.direction == 'inbound' else "outbound to"

            body = Markup(
                '<div>'
                '<a href="#wa-message-id-%s" style="display: none;"></a>'
                '<strong>WhatsApp %s %s</strong><br/>%s'
                '</div>'
            ) % (message.id, direction_label, escape(sender), content_html)

            try:
                lead.sudo().message_post(
                    body=body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as e:
                _logger.warning("Failed to mirror WhatsApp message %s into lead %s: %s", message.id, lead.id, e)

    # --- ACTIONS ---

    @api.model
    def get_sidebar_chats(self, filter_type='all', search_query='', offset=0, limit=50, pane=None, account_id=None, **kwargs):
        domain = [('is_archived', '=', False)]

        # Account isolation (AiSensy-style channel separation)
        # When an account is selected, only show chats from that WhatsApp Business number
        if account_id:
            domain.append(('account_id', '=', int(account_id)))

        # Pane logic (Three-pane UI)
        if pane == 'active':
            # "Mine" pane — chats assigned to the current user
            domain.append(('assigned_user_id', '=', self.env.user.id))
        elif pane == 'request':
            # "Unassigned" pane — chats with no agent
            domain.append(('assigned_user_id', '=', False))
        # pane == 'intervened' ("All") — no extra filter, show everything

        if filter_type == 'open':
            import datetime
            cutoff = fields.Datetime.now() - datetime.timedelta(days=1)
            domain.append(('last_inbound_date', '>=', cutoff))
            domain.append(('state', '=', 'open'))
        elif filter_type == 'mine':
            domain.append(('assigned_user_id', '=', self.env.user.id))
        elif filter_type == 'unread':
            domain.append(('unread_count', '>', 0))
        elif filter_type == 'snoozed':
            domain.append(('state', '=', 'snoozed'))
        elif filter_type == 'resolved':
            domain.append(('state', '=', 'resolved'))

        if search_query:
            domain.append('|')
            domain.append(('display_name', 'ilike', search_query))
            domain.append(('phone_number', 'ilike', search_query))

        chats = self.search(domain, order='last_message_date desc nulls last, id desc', offset=int(offset), limit=int(limit))

        result = []
        for chat in chats:
            result.append({
                'id': chat.id,
                'display_name': chat.display_name or chat.phone_number,
                'phone_number': chat.phone_number,
                'display_name_initial': chat.display_name_initial,
                'account_id': chat.account_id.id,
                'account_name': chat.account_id.name or '',
                'assigned_user_id': chat.assigned_user_id.id if chat.assigned_user_id else False,
                'assigned_user_name': chat.assigned_user_id.name if chat.assigned_user_id else '',
                'last_message_body': chat.last_message_body or 'No messages yet',
                'last_message_date_str': chat.last_message_date_str or '',
                'last_message_status': chat.last_message_status,
                'last_message_direction': chat.last_message_direction,
                'unread_count': chat.unread_count,
                'is_pinned': chat.is_pinned,
                'is_archived': chat.is_archived,
                'sla_status': chat.sla_status,
                'sla_timer_minutes': chat.sla_timer_minutes,
                'state': chat.state,
                'needs_reply': chat.needs_reply,
            })
        return result

    @api.model
    def get_sidebar_counts(self, filter_type='all', search_query='', account_id=None, **kwargs):
        """Returns the actual database counts of chats in the three panes (Mine, Unassigned, All)"""
        counts = {
            'active': 0,
            'request': 0,
            'intervened': 0,
        }

        base_domain = [('is_archived', '=', False)]

        # Account isolation — match the same account filter as get_sidebar_chats
        if account_id:
            base_domain.append(('account_id', '=', int(account_id)))

        if filter_type == 'open':
            import datetime
            cutoff = fields.Datetime.now() - datetime.timedelta(days=1)
            base_domain.append(('last_inbound_date', '>=', cutoff))
            base_domain.append(('state', '=', 'open'))
        elif filter_type == 'mine':
            base_domain.append(('assigned_user_id', '=', self.env.user.id))
        elif filter_type == 'unread':
            base_domain.append(('unread_count', '>', 0))
        elif filter_type == 'snoozed':
            base_domain.append(('state', '=', 'snoozed'))
        elif filter_type == 'resolved':
            base_domain.append(('state', '=', 'resolved'))

        if search_query:
            base_domain.append('|')
            base_domain.append(('display_name', 'ilike', search_query))
            base_domain.append(('phone_number', 'ilike', search_query))

        # Count "Mine" pane — chats assigned to current user
        domain_active = base_domain + [('assigned_user_id', '=', self.env.user.id)]
        counts['active'] = self.search_count(domain_active)

        # Count "Unassigned" pane — chats with no agent
        domain_request = base_domain + [('assigned_user_id', '=', False)]
        counts['request'] = self.search_count(domain_request)

        # Count "All" pane (intervened) — all chats regardless of assignment
        counts['intervened'] = self.search_count(base_domain)

        return counts

    def action_send_quick_reply(self):
        self.ensure_one()
        body = self.quick_reply_text or self.env.context.get('default_quick_reply_text')
        if not body and not self.quick_media_file:
            return

        if not self.session_open:
            raise UserError("24h window closed. Use a Template.")

        msg_type = 'text'
        if self.quick_media_file:
            ext = (self.quick_media_filename or '').split('.')[-1].lower()
            msg_type = 'image' if ext in ['jpg','jpeg','png','gif','webp'] else 'video' if ext in ['mp4','mov'] else 'audio' if ext in ['mp3','ogg'] else 'document'

        vals = {
            'account_id': self.account_id.id,
            'phone_number': self.phone_number,
            'body': body,
            'direction': 'outbound',
            'message_type': msg_type,
            'chat_id_ref': self.id,
            'media_file': self.quick_media_file,
            'media_filename': self.quick_media_filename,
            'caption': body if msg_type != 'text' else False,
        }
        msg = self.env['whatsapp.message'].create(vals)
        msg.action_send()
        self.write({'quick_reply_text': False, 'quick_media_file': False, 'quick_media_filename': False})
        # Explicitly invalidate history_html cache so the next read() returns fresh data
        self.env.invalidate_all()
        return True

    @api.depends('quick_template_id', 'quick_template_id.preview_html', 'partner_id')
    def _compute_quick_template_preview_html(self):
        for chat in self:
            if not chat.quick_template_id:
                chat.quick_template_preview_html = False
                continue
            chat.quick_template_preview_html = chat.quick_template_id._render_customer_preview_html(
                partner=chat.partner_id,
                shell=True,
                compact=True,
            )

    @api.depends(
        'quick_template_id',
        'quick_template_id.name',
        'quick_template_id.status',
        'quick_template_id.language',
        'quick_template_id.header_type',
        'quick_template_id.header_text',
        'quick_template_id.header_media_file',
        'quick_template_id.header_media_url',
        'quick_template_id.header_media_filename',
        'quick_template_id.body',
        'quick_template_id.footer',
        'quick_template_id.has_buttons',
        'quick_template_id.button_type',
        'quick_template_id.button_text_1',
        'quick_template_id.button_text_2',
        'quick_template_id.button_text_3',
        'quick_template_id.cta_url_text',
        'quick_template_id.cta_url_link',
        'quick_template_id.cta_phone_text',
        'quick_template_id.cta_phone_number',
        'quick_template_id.copy_code_example',
        'quick_template_id.is_carousel',
        'quick_template_id.card_ids.body',
        'partner_id',
    )
    def _compute_quick_template_preview_text(self):
        for chat in self:
            template = chat.quick_template_id
            if not template:
                chat.quick_template_preview_text = False
                continue

            def plain(value):
                return html2plaintext(str(value or '')).strip()

            lines = [
                _("Template: %(name)s") % {'name': template.display_name or template.name or ''},
                _("Status: %(status)s | Language: %(language)s") % {
                    'status': template.status or '-',
                    'language': template.language or '-',
                },
            ]

            header_type = (template.header_type or 'none').lower()
            if header_type and header_type != 'none':
                if header_type == 'text':
                    header = plain(template._render_preview_text(
                        template.header_text,
                        partner=chat.partner_id,
                        highlight=False,
                    ))
                    lines.append(_("Header: %s") % (header or _('Text header')))
                else:
                    filename = template.header_media_filename or template.name or _('media file')
                    ready = template._has_send_ready_header_media(account=chat.account_id)
                    lines.append(_("Header: %(type)s - %(file)s") % {
                        'type': header_type.title(),
                        'file': filename,
                    })
                    if ready:
                        lines.append(_("Header media is ready for sending."))
                    else:
                        lines.append(_(
                            "Warning: this %s header still needs a default send media file, WhatsApp media ID, "
                            "public HTTPS URL, or a previous successful send with this approved template."
                        ) % header_type)

            if template.is_carousel:
                lines.append(_("Carousel: %s card(s)") % len(template.card_ids))
                for idx, card in enumerate(template.card_ids.sorted('sequence')[:5], start=1):
                    lines.append("%s. %s" % (idx, plain(template._render_preview_text(
                        card.body,
                        partner=chat.partner_id,
                        highlight=False,
                    )) or _('Carousel card')))
            else:
                body = plain(template._render_preview_text(
                    template.body,
                    partner=chat.partner_id,
                    highlight=False,
                ))
                lines.append(_("Body:"))
                lines.append(body or _('No body text configured.'))

            if template.footer:
                lines.append(_("Footer: %s") % plain(template.footer))

            button_labels = []
            if template.has_buttons:
                if template.button_type == 'quick_reply':
                    button_labels = [template.button_text_1, template.button_text_2, template.button_text_3]
                elif template.button_type == 'call_to_action':
                    if template.cta_url_text:
                        button_labels.append("%s -> %s" % (template.cta_url_text, template.cta_url_link or _('URL missing')))
                    if template.cta_phone_text:
                        button_labels.append("%s -> %s" % (template.cta_phone_text, template.cta_phone_number or _('phone missing')))
                elif template.button_type == 'copy_code':
                    button_labels.append(_("Copy code: %s") % (template.copy_code_example or _('sample missing')))
            button_labels = [plain(label) for label in button_labels if label]
            if button_labels:
                lines.append(_("Buttons: %s") % " | ".join(button_labels))

            chat.quick_template_preview_text = "\n".join(lines)

    @api.depends(
        'session_open',
        'quick_form_id',
        'quick_invoice_id',
        'quick_sale_order_id',
        'partner_id',
        'account_id.default_form_id',
        'account_id.payment_link_mode',
        'account_id.payment_manual_url',
    )
    def _compute_quick_action_help_text(self):
        for chat in self:
            lines = []
            if chat.session_open:
                lines.append(_("Open session: you can send links, forms, media, and normal replies."))
            else:
                lines.append(_("Closed session: use an approved template. Free-form shortcut links will be blocked by WhatsApp."))

            if chat.quick_form_id:
                lines.append(_("Form: selected '%s'.") % chat.quick_form_id.display_name)
            elif chat.account_id.default_form_id:
                lines.append(_("Form: will use account default '%s'.") % chat.account_id.default_form_id.display_name)
            else:
                lines.append(_("Form: select a Quick Form or set a Default WhatsApp Form on the account."))

            if not chat.partner_id:
                lines.append(_("Payment: link this chat to a contact before sending a payment link."))
            elif chat.quick_invoice_id:
                lines.append(_("Payment: selected invoice %s.") % chat.quick_invoice_id.display_name)
            elif chat.quick_sale_order_id:
                lines.append(_("Payment: selected quotation/order %s.") % chat.quick_sale_order_id.display_name)
            elif chat.account_id.payment_link_mode == 'disabled':
                lines.append(_("Payment: disabled on this WhatsApp account."))
            elif chat.account_id.payment_link_mode == 'manual_url' and not chat.account_id.payment_manual_url:
                lines.append(_("Payment: manual mode is enabled, but no manual URL is configured."))
            else:
                lines.append(_("Payment: will use the account rule to find the latest unpaid invoice/quotation."))

            chat.quick_action_help_text = "\n".join(lines)

    def action_send_internal_note(self):
        self.ensure_one()
        body = self.quick_reply_text or self.env.context.get('default_quick_reply_text')
        if body:
            self.env['whatsapp.chat.note'].create({
                'chat_id': self.id,
                'assigned_user_id': self.env.user.id,
                'body': body
            })
            self.quick_reply_text = False
        return True

    def action_send_quick_template(self):
        self.ensure_one()
        template = self.quick_template_id
        if not template:
            raise UserError(_("Select an approved template before sending."))
        if template.status != 'approved':
            raise UserError(_("Only approved WhatsApp templates can be sent."))
        if (
            template.header_type in ('image', 'video', 'document')
            and not template._has_send_ready_header_media(account=self.account_id)
        ):
            action = self.action_open_send_wizard()
            action['name'] = _('Attach Header Media')
            context = dict(action.get('context') or {})
            context.update({
                'default_template_id': template.id,
                'default_account_id': self.account_id.id,
                'default_chat_id': self.id,
            })
            action['context'] = context
            return action
        template._validate_meta_constraints()

        payload = template._prepare_send_payload(
            partner=self.partner_id,
            account=self.account_id,
        )
        msg = self.env['whatsapp.message'].create({
            'account_id': self.account_id.id,
            'phone_number': self.phone_number,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'chat_id_ref': self.id,
            'message_type': 'template',
            'body': template.body,
            'template_id': template.id,
            'template_name': template._get_send_template_name(),
            'template_language': template._get_send_language_code(),
            'raw_data': json.dumps(payload),
            'media_filename': template.header_media_filename if template.header_type in ('image', 'video', 'document') else False,
            'direction': 'outbound',
        })
        msg.action_send()
        self.quick_template_id = False
        self.env.invalidate_all()
        return self.action_reload_chat()

    def _send_shortcut_text(self, body, message_type='text'):
        self.ensure_one()
        if not body:
            raise UserError(_("There is no message body to send."))
        if not self.session_open:
            raise UserError(_("24h window is closed. Send an approved template instead of a free-text shortcut."))
        msg = self.env['whatsapp.message'].create({
            'account_id': self.account_id.id,
            'phone_number': self.phone_number,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'body': body,
            'direction': 'outbound',
            'message_type': message_type,
            'chat_id_ref': self.id,
        })
        msg.action_send()
        self.env.invalidate_all()
        return msg

    def action_send_form_link(self):
        self.ensure_one()
        form = self.quick_form_id or self.account_id.default_form_id
        if not form:
            raise UserError(_("Select a Quick Form on this chat or configure a Default WhatsApp Form on the account."))
        if not form.public_url:
            raise UserError(_("The selected form does not have a public URL yet. Save the form or regenerate its link."))
        customer = self.partner_id.display_name or self.whatsapp_profile_name or self.display_name or _("Customer")
        body = _(
            "Hi %(name)s, please fill this short form so our team can help you faster:\n%(url)s"
        ) % {'name': customer, 'url': form.public_url}
        self._send_shortcut_text(body)
        self.quick_form_id = False
        return self.action_reload_chat()

    def action_send_payment_link(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Link this chat to a customer/contact before sending a payment link."))
        body = self.account_id._build_payment_link_message(
            partner=self.partner_id,
            invoice=self.quick_invoice_id,
            sale_order=False if self.quick_invoice_id else self.quick_sale_order_id,
        )
        self._send_shortcut_text(body)
        self.quick_invoice_id = False
        self.quick_sale_order_id = False
        return self.action_reload_chat()

    def action_mark_as_read(self):
        return self.action_mark_read()

    def action_resolve(self):
        self.write({'state': 'resolved'})

    def action_snooze(self):
        self.write({'state': 'snoozed'})

    def action_reopen(self):
        self.write({'state': 'open', 'is_archived': False})

    def action_toggle_pin(self):
        self.is_pinned = not self.is_pinned

    def action_toggle_archive(self):
        self.is_archived = not self.is_archived

    def action_open_chat(self):
        self.ensure_one()
        self.action_mark_read()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.chat',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_reload_chat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.chat',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': dict(self.env.context, active_test=False),
        }

    def action_open_meta_manager(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://business.facebook.com/wa/manage/message-templates/',
            'target': 'new',
        }

    def action_open_forms(self):
        action = self.env.ref('elsx_whatsapp_marketing.action_whatsapp_form').read()[0]
        action['target'] = 'current'
        return action

    def action_open_commerce_setup(self):
        action = self.env.ref('elsx_whatsapp_marketing.action_whatsapp_commerce_setup').read()[0]
        action['target'] = 'current'
        return action

    def action_generate_ai_reply(self):
        """Draft a reply from the current conversation context without sending it."""
        self.ensure_one()
        if not self.env['elsx.ai.provider']._whatsapp_draft_enabled():
            raise UserError(_("WhatsApp AI drafts are disabled in Settings."))
        last_inbound = self.env['whatsapp.message'].sudo().search([
            ('chat_id_ref', '=', self.id),
            ('direction', '=', 'inbound'),
        ], order='create_date desc, id desc', limit=1)
        customer_name = self.display_name or 'there'
        incoming = (last_inbound.body if last_inbound else '') or ''
        account = self.account_id
        brand_name = (
            account.ai_brand_name
            or 'our team'
        )
        ai_payload = {
            'brand_name': brand_name,
            'account_name': account.name or '',
            'tone': account.ai_reply_tone or 'professional',
            'business_context': account.ai_context or '',
            'reply_instructions': account.ai_reply_instructions or '',
            'reply_signature': account.ai_reply_signature or '',
            'customer_name': customer_name,
            'latest_inbound': incoming,
            'agent_name': self.env.user.display_name,
            'draft_only': True,
        }
        input_text = (
            "Create one editable WhatsApp reply draft.\n"
            "Do not send the message. Do not output JSON unless explicitly requested.\n"
            f"Brand/customer-facing company name: {brand_name}\n"
            f"Tone: {ai_payload['tone']}\n"
            f"Customer: {customer_name}\n"
            f"Latest inbound message: {incoming}\n"
            f"Business context: {account.ai_context or ''}\n"
            f"Reply rules: {account.ai_reply_instructions or ''}\n"
            f"Optional signature: {account.ai_reply_signature or ''}"
        )
        job = self.env['elsx.ai.job'].create_job(
            'whatsapp_reply',
            f'WhatsApp reply draft for {customer_name}',
            origin=self,
            input_text=input_text,
            input_payload=ai_payload,
            prompt_code='whatsapp_reply_default',
        )
        try:
            job.action_run()
        except UserError as exc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Draft Not Ready',
                    'message': str(exc),
                    'type': 'warning',
                }
            }
        draft = self._clean_ai_reply_text(job.response_text or '')
        if not draft:
            draft = job._rule_based_response()
        classification = self._ai_classify_chat(incoming)
        self.write({
            'ai_suggested_reply': draft,
            **classification,
        })
        return self.action_reload_chat()

    @api.depends(
        'ai_suggested_reply',
        'quick_reply_text',
        'ai_intent',
        'ai_sentiment',
        'ai_urgency',
        'ai_next_action',
        'ai_suggested_tags',
        'ai_suggested_flow_id',
    )
    def _compute_ai_guidance_html(self):
        sentiment_labels = dict(self._fields['ai_sentiment'].selection)
        urgency_labels = dict(self._fields['ai_urgency'].selection)
        for chat in self:
            if not any([
                chat.ai_suggested_reply,
                chat.ai_intent,
                chat.ai_sentiment,
                chat.ai_urgency,
                chat.ai_next_action,
                chat.ai_suggested_tags,
                chat.ai_suggested_flow_id,
            ]):
                chat.ai_guidance_html = False
                continue

            chips = []

            def add_chip(label, value, tone='neutral'):
                if value:
                    chips.append(
                        '<span class="wa-ai-chip wa-ai-chip-%s"><span>%s</span>%s</span>'
                        % (escape(tone), escape(label), escape(value))
                    )

            add_chip('Intent', chat.ai_intent, 'intent')
            add_chip('Sentiment', sentiment_labels.get(chat.ai_sentiment, chat.ai_sentiment), chat.ai_sentiment or 'neutral')
            add_chip('Urgency', urgency_labels.get(chat.ai_urgency, chat.ai_urgency), chat.ai_urgency or 'neutral')

            rows = []
            if chat.ai_next_action:
                rows.append(
                    '<div class="wa-ai-row"><span>Next</span><p>%s</p></div>'
                    % escape(chat.ai_next_action)
                )
            if chat.ai_suggested_tags:
                rows.append(
                    '<div class="wa-ai-row"><span>Tags</span><p>%s</p></div>'
                    % escape(chat.ai_suggested_tags)
                )
            if chat.ai_suggested_flow_id:
                rows.append(
                    '<div class="wa-ai-row"><span>Flow</span><p>%s</p></div>'
                    % escape(chat.ai_suggested_flow_id.display_name)
                )
            if chat.ai_suggested_reply:
                draft_preview = (chat.ai_suggested_reply or '').replace('\r\n', '\n').strip()
                if len(draft_preview) > 240:
                    draft_preview = draft_preview[:237] + '...'
                status = 'Draft placed in composer' if chat.quick_reply_text == chat.ai_suggested_reply else 'Draft ready'
                rows.append(
                    '<div class="wa-ai-row wa-ai-draft-row"><span>%s</span><p>%s</p></div>'
                    % (escape(status), escape(draft_preview))
                )

            chat.ai_guidance_html = Markup(
                '<div class="wa-ai-guidance-content">'
                '<div class="wa-ai-guidance-title"><i class="fa fa-lightbulb-o"></i><strong>AI draft guidance</strong></div>'
                '<div class="wa-ai-chips">%s</div>'
                '<div class="wa-ai-rows">%s</div>'
                '</div>'
            ) % (Markup(''.join(chips)), Markup(''.join(rows)))

    def _clean_ai_reply_text(self, value):
        """Return customer-safe draft text, never a raw provider JSON blob."""
        self.ensure_one()
        text = (value or '').strip()
        if not text:
            return ''

        def path_value(payload, path):
            current = payload
            for part in path.split('.'):
                if isinstance(current, list):
                    try:
                        current = current[int(part)]
                    except Exception:
                        return ''
                elif isinstance(current, dict):
                    current = current.get(part)
                else:
                    return ''
            return current if isinstance(current, str) else ''

        if text.startswith(('{', '[')):
            try:
                payload = json.loads(text)
            except Exception:
                payload = False
            if payload:
                for path in (
                    'reply',
                    'draft',
                    'response',
                    'message',
                    'content',
                    'output_text',
                    'choices.0.message.content',
                    'choices.0.text',
                ):
                    extracted = path_value(payload, path).strip()
                    if extracted:
                        return extracted[:4096]
                return ''

        # Guard against accidentally placing a serialized provider response in the composer.
        provider_markers = ('"choices"', '"usage"', '"prompt_tokens"', '"completion_tokens"', '"finish_reason"')
        if any(marker in text for marker in provider_markers):
            return ''
        return text[:4096]

    def action_use_ai_suggested_reply(self):
        self.ensure_one()
        if not self.ai_suggested_reply:
            raise UserError(_("Generate an AI draft before using it."))
        draft = self._clean_ai_reply_text(self.ai_suggested_reply)
        if not draft:
            raise UserError(_("The AI provider returned a raw/invalid response. Regenerate the draft or switch provider."))
        self.quick_reply_text = draft
        return self.action_reload_chat()

    def action_start_ai_suggested_flow(self):
        self.ensure_one()
        flow = self.ai_suggested_flow_id
        if not flow:
            raise UserError(_("No suggested flow is available for this chat."))
        last_message = self.env['whatsapp.message'].sudo().search([
            ('chat_id_ref', '=', self.id),
        ], order='create_date desc, id desc', limit=1)
        if not last_message:
            raise UserError(_("This chat needs at least one message before a flow can be started."))
        flow.sudo()._execute_flow(last_message, source='ai_suggested_flow')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Flow Started'),
                'message': _('Started suggested flow: %s') % flow.display_name,
                'type': 'success',
            }
        }

    def action_open_ai_flow_manager(self):
        self.ensure_one()
        domain = []
        context = {
            'default_account_id': self.account_id.id if self.account_id else False,
            'default_active': False,
        }
        if self.account_id:
            domain = ['|', ('account_id', '=', self.account_id.id), ('account_id', '=', False)]
        if self.ai_intent == 'sales_enquiry':
            context['default_flow_type'] = 'sales'
        elif self.ai_intent == 'support':
            context['default_flow_type'] = 'support'
        else:
            context['default_flow_type'] = 'custom'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manage WhatsApp Flows'),
            'res_model': 'whatsapp.bot.flow',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            'context': context,
            'target': 'current',
        }

    def action_clear_ai_guidance(self):
        for chat in self:
            vals = {
                'ai_suggested_reply': False,
                'ai_intent': False,
                'ai_sentiment': False,
                'ai_urgency': False,
                'ai_summary': False,
                'ai_suggested_tags': False,
                'ai_next_action': False,
                'ai_suggested_flow_id': False,
            }
            if chat.ai_suggested_reply and chat.quick_reply_text == chat.ai_suggested_reply:
                vals['quick_reply_text'] = False
            chat.write(vals)
        return self[:1].action_reload_chat() if self else True

    def _ai_classify_chat(self, latest_text):
        text = (latest_text or '').lower()
        negative_terms = ('problem', 'issue', 'delay', 'complaint', 'not received', 'wrong', 'urgent')
        sales_terms = ('price', 'quote', 'quotation', 'catalog', 'catalogue', 'dealer', 'buy', 'requirement')
        support_terms = ('support', 'help', 'problem', 'issue', 'complaint', 'warranty')
        intent = 'sales_enquiry' if any(term in text for term in sales_terms) else 'support' if any(term in text for term in support_terms) else 'general'
        sentiment = 'negative' if any(term in text for term in negative_terms) else 'neutral'
        urgency = 'high' if any(term in text for term in ('urgent', 'asap', 'immediately', 'complaint')) else 'normal'
        suggested_flow = self.env['whatsapp.bot.flow'].search([
            ('account_id', '=', self.account_id.id),
            ('active', '=', True),
            '|', ('flow_type', '=', 'sales' if intent == 'sales_enquiry' else 'support'), ('flow_type', '=', 'custom'),
        ], order='priority desc, id', limit=1)
        tag_map = {
            'sales_enquiry': 'Sales Lead, Catalogue/Price',
            'support': 'Support Required',
            'general': 'General Enquiry',
        }
        action_map = {
            'sales_enquiry': 'Share catalogue/pricing and create or update CRM opportunity',
            'support': 'Assign support agent and request order/project details',
            'general': 'Reply with greeting and ask for requirement',
        }
        return {
            'ai_intent': intent,
            'ai_sentiment': sentiment,
            'ai_urgency': urgency,
            'ai_summary': latest_text[:500] if latest_text else '',
            'ai_suggested_tags': tag_map.get(intent),
            'ai_next_action': action_map.get(intent),
            'ai_suggested_flow_id': suggested_flow.id if suggested_flow else False,
        }

    def action_touch_agent_presence(self, is_active=True):
        """Let the inbox tab refresh ERP presence so routing can avoid inactive agents."""
        inactivity_ms = 0 if is_active else (31 * 60 * 1000)
        try:
            with self.env.cr.savepoint():
                self.env['mail.presence']._update_presence(self.env.user, inactivity_period=inactivity_ms)
        except Exception as e:
                _logger.warning("Failed to update agent presence due to lock/concurrency contention: %s", e)
        return True

    @api.model
    def get_quick_reply_suggestions(self, chat_id=False, query=''):
        """Return canned replies for the composer slash palette."""
        chat = self.sudo().browse(int(chat_id)) if chat_id else self.browse()
        account = chat.account_id if chat and chat.exists() else False
        domain = [('active', '=', True)]
        if account:
            domain += ['|', ('account_id', '=', False), ('account_id', '=', account.id)]

        search_text = (query or '').strip()
        if search_text.startswith('/'):
            search_text = search_text[1:]
        if search_text:
            domain += [
                '|', '|',
                ('shortcut', 'ilike', search_text),
                ('name', 'ilike', search_text),
                ('message', 'ilike', search_text),
            ]

        replies = self.env['whatsapp.quick.reply'].sudo().search(domain, limit=8)
        result = []
        for reply in replies:
            message = reply.message or ''
            preview = message.replace('\n', ' ')
            if len(preview) > 120:
                preview = preview[:117] + '...'
            result.append({
                'id': reply.id,
                'name': reply.name,
                'shortcut': reply.shortcut,
                'message': message,
                'preview': preview,
            })
        return result

    @api.model
    def get_sidecar_url(self):
        """Retrieve the sidecar url securely for standard users without AccessError on ir.config_parameter"""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('whatsapp.realtime.mode', default='bus') != 'socket':
            return ''
        return params.get_param('whatsapp.sidecar.url') or ''

    def action_open_send_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_chat_id': self.id,
                'default_account_id': self.account_id.id,
                'default_phone_number': self.phone_number,
                'active_model': 'whatsapp.chat',
                'active_id': self.id,
                'active_ids': [self.id],
            }
        }

    def action_view_partner(self):
        self.ensure_one()
        if self.partner_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'res_id': self.partner_id.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return False

    def action_open_contact(self):
        self.ensure_one()
        contact = self.env['whatsapp.contact'].search([('phone_number', '=', self.phone_number)], limit=1)
        if contact:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'whatsapp.contact',
                'res_id': contact.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return False

    def action_create_opportunity(self):
        self.ensure_one()
        if not self.partner_id:
            # Optionally create partner
            pass
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Opportunity',
            'res_model': 'crm.lead',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_name': f"WhatsApp Opportunity: {self.display_name}",
                'default_phone': self.phone_number,
                'default_description': f"Created from WhatsApp Chat.\nLast Message: {self.last_message_body}",
            }
        }

    def action_create_quote(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Quotation',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.id if self.partner_id else False,
            }
        }

    def action_clear_media(self):
        self.write({'quick_media_file': False, 'quick_media_filename': False})
        return True

    def _auto_assign_agent(self):
        for chat in self:
            root = self.env.ref('base.user_root', raise_if_not_found=False)
            root_id = root.id if root else False
            if chat.assigned_user_id and chat.assigned_user_id.id != root_id:
                continue

            # 1. Sticky Routing (Twilio / AiSensy style)
            # Route back to the agent who handled this customer within the last 24h
            last_outbound = self.env['whatsapp.message'].sudo().search([
                ('chat_id_ref', '=', chat.id),
                ('direction', '=', 'outbound'),
                ('create_uid', '!=', root_id)
            ], order='create_date desc', limit=1)

            if last_outbound and last_outbound.create_uid:
                agent = last_outbound.create_uid
                presence = self.env['mail.presence'].sudo().search([('user_id', '=', agent.id)], limit=1)
                if presence and presence.status == 'online':
                    chat.write({'assigned_user_id': agent.id})
                    self.env['whatsapp.conversation.assignment'].sudo().create({
                        'chat_id': chat.id,
                        'assigned_user_id': agent.id,
                        'assigned_by': self.env.user.id,
                        'transfer_reason': 'sticky',
                    })
                    continue

            # 2. Strict Round-Robin Routing
            team_members = self.env['whatsapp.team.member'].sudo().search([
                ('account_id', '=', chat.account_id.id),
                ('is_available', '=', True),
                ('can_send_messages', '=', True),
                ('role', 'in', ['admin', 'manager', 'agent']),
            ])
            agents = team_members.mapped('user_id').filtered(lambda u: u.active and not u.share)
            max_by_user = {
                member.user_id.id: member.max_active_chats or 5
                for member in team_members
            }
            if not agents:
                agents = self.env['res.users'].sudo().search([('share', '=', False), ('active', '=', True)])
                max_by_user = {user.id: 5 for user in agents}
            online_ids = [p.user_id.id for p in self.env['mail.presence'].sudo().search([('user_id', 'in', agents.ids), ('status', '=', 'online')])]
            target_pool = agents.filtered(lambda a: a.id in online_ids) or agents

            if target_pool:
                self.env.cr.execute("""
                    SELECT assigned_user_id, count(id)
                    FROM whatsapp_chat
                    WHERE state = 'open' AND assigned_user_id IN %s
                    GROUP BY assigned_user_id
                """, (tuple(target_pool.ids),))
                counts = dict(self.env.cr.fetchall())

                # Filter by max active cap
                under_cap = target_pool.filtered(lambda u: counts.get(u.id, 0) < max_by_user.get(u.id, 10))
                target_pool = under_cap or target_pool

                # Round Robin: Find the agent with the oldest last assignment
                self.env.cr.execute("""
                    SELECT assigned_user_id, MAX(create_date)
                    FROM whatsapp_conversation_assignment
                    WHERE assigned_user_id IN %s
                    GROUP BY assigned_user_id
                """, (tuple(target_pool.ids),))
                last_assignments = dict(self.env.cr.fetchall())

                # Sort by last assignment date (oldest first)
                import datetime
                epoch = datetime.datetime(1970, 1, 1)
                target_pool = target_pool.sorted(key=lambda u: last_assignments.get(u.id, epoch))

                assigned_agent = target_pool[0]
                previous_user = chat.assigned_user_id
                chat.write({'assigned_user_id': assigned_agent.id})

                # Log assignment
                self.env['whatsapp.conversation.assignment'].sudo().create({
                    'chat_id': chat.id,
                    'assigned_user_id': assigned_agent.id,
                    'assigned_by': self.env.user.id,
                    'previous_user_id': previous_user.id if previous_user else False,
                    'transfer_reason': 'round_robin',
                })

    # History Rendering — explicitly depends on message fields so cache invalidates on new/updated messages
    history_html = fields.Html('History HTML', compute='_compute_history_html', sanitize=False)

    def action_load_more(self):
        self.ensure_one()
        default_limit = int(self.env['ir.config_parameter'].sudo().get_param('whatsapp.history.initial.limit', default=50) or 50)
        limit = int(self.env.context.get('wa_history_limit', default_limit)) + 100
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.chat',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': dict(self.env.context, wa_history_limit=limit, active_test=False),
        }

    @api.depends('message_ids', 'message_ids.body', 'message_ids.status',
                 'message_ids.create_date', 'message_ids.direction',
                 'message_ids.message_type', 'message_ids.media_file',
                 'message_ids.media_url', 'message_ids.media_filename',
                 'message_ids.media_mime_type', 'message_ids.caption',
                 'message_ids.button_text', 'message_ids.button_payload',
                 'message_ids.list_item_id', 'message_ids.list_item_title',
                 'message_ids.interactive_type', 'message_ids.button_url',
                 'message_ids.catalog_id', 'message_ids.product_retailer_id',
                 'message_ids.raw_data', 'message_ids.attachment_ids')
    @api.depends_context('wa_ts', 'wa_history_limit')
    def _compute_history_html(self):
        for record in self:
            html_parts = []
            last_date = None
            Message = self.env['whatsapp.message'].sudo()
            default_limit = int(self.env['ir.config_parameter'].sudo().get_param('whatsapp.history.initial.limit', default=50) or 50)
            limit = int(self.env.context.get('wa_history_limit', default_limit) or default_limit)
            domain = [('chat_id_ref', '=', record.id)]
            total_count = Message.search_count(domain)
            messages = Message.search(domain, order='create_date desc, id desc', limit=limit)

            def _template_record_for_message(message):
                template = message.template_id
                if not template and message.template_name:
                    domain = [
                        '|',
                        ('meta_template_name', '=', message.template_name),
                        ('name', '=', message.template_name),
                    ]
                    if message.account_id:
                        domain = ['&', ('account_id', 'in', [False, message.account_id.id])] + domain
                    template = self.env['whatsapp.template'].sudo().search(domain, limit=1)
                return template

            def _render_template_text(template, text):
                if not text:
                    return Markup('')
                rendered = escape(text)
                for var in template.variable_ids:
                    sample = escape(var.sample_value or var.name or '')
                    rendered = Markup(str(rendered).replace(escape(var.name), str(sample)))
                return rendered

            def _document_icon_class(filename):
                name = (filename or '').lower()
                if name.endswith(('.doc', '.docx')):
                    return 'fa-file-word-o text-primary'
                if name.endswith(('.xls', '.xlsx')):
                    return 'fa-file-excel-o text-success'
                if name.endswith(('.ppt', '.pptx')):
                    return 'fa-file-powerpoint-o text-warning'
                if name.endswith('.pdf'):
                    return 'fa-file-pdf-o text-danger'
                return 'fa-file-text-o text-muted'

            def _is_http_url(value):
                return bool(value and str(value).strip().startswith(('http://', 'https://')))

            def _media_urls(message):
                if message.media_file:
                    content_url = f"/web/content/whatsapp.message/{message.id}/media_file"
                    image_url = f"/web/image/whatsapp.message/{message.id}/media_file"
                    return {
                        'open': content_url,
                        'preview': image_url if message.message_type == 'image' else content_url,
                        'download': f"{content_url}?download=1",
                        'pending': False,
                    }
                if _is_http_url(message.media_url):
                    return {
                        'open': str(message.media_url).strip(),
                        'preview': str(message.media_url).strip(),
                        'download': str(message.media_url).strip(),
                        'pending': False,
                    }
                return {
                    'open': False,
                    'preview': False,
                    'download': False,
                    'pending': bool(message.media_url),
                }

            def _render_media_actions(message, urls):
                if urls.get('open'):
                    return Markup(
                        '<div class="wa-msg-media-actions d-flex gap-1 flex-wrap mt-2">'
                        '<a href="%s" target="_blank" class="btn btn-sm btn-outline-secondary py-1 px-2">'
                        '<i class="fa fa-external-link me-1"></i>Open</a>'
                        '<a href="%s" target="_blank" download class="btn btn-sm btn-outline-primary py-1 px-2">'
                        '<i class="fa fa-download me-1"></i>Download</a>'
                        '</div>'
                    ) % (escape(urls['open']), escape(urls.get('download') or urls['open']))
                if urls.get('pending'):
                    return Markup(
                        '<div class="wa-msg-media-actions mt-2">'
                        '<button type="button" class="btn btn-sm btn-outline-primary py-1 px-2" '
                        'data-wa-retry-media-id="%s">'
                        '<i class="fa fa-refresh me-1"></i>Retry download</button>'
                        '</div>'
                    ) % message.id
                return Markup('')

            def _render_media_message(message, fallback_content):
                urls = _media_urls(message)
                filename = message.media_filename or {
                    'image': 'Image',
                    'video': 'Video',
                    'document': 'Document',
                    'audio': 'Audio',
                }.get(message.message_type, 'Media')
                meta = message.media_mime_type or message.message_type.title()
                actions = _render_media_actions(message, urls)
                if urls.get('preview') and message.message_type == 'image':
                    media = Markup(
                        '<div class="wa-msg-media mb-2">'
                        '<a href="%s" class="wa-lightbox-trigger" data-media-type="image">'
                        '<img src="%s" class="img-fluid rounded shadow-sm" style="max-height:250px;"/>'
                        '</a>%s</div>'
                    ) % (escape(urls['open'] or urls['preview']), escape(urls['preview']), actions)
                    return media + fallback_content
                if urls.get('preview') and message.message_type == 'video':
                    media = Markup(
                        '<div class="wa-msg-media mb-2">'
                        '<video src="%s" controls class="img-fluid rounded shadow-sm" style="max-height:250px;"></video>'
                        '%s</div>'
                    ) % (escape(urls['preview']), actions)
                    return media + fallback_content
                if urls.get('preview') and message.message_type == 'audio':
                    media = Markup(
                        '<div class="wa-msg-media mb-2">'
                        '<audio src="%s" controls style="height:40px;width:100%%;"></audio>'
                        '%s</div>'
                    ) % (escape(urls['preview']), actions)
                    return media + fallback_content

                icon = _document_icon_class(filename) if message.message_type == 'document' else {
                    'image': 'fa-image text-muted',
                    'video': 'fa-video-camera text-muted',
                    'audio': 'fa-microphone text-muted',
                }.get(message.message_type, 'fa-file text-muted')
                if urls.get('open'):
                    title = Markup(
                        '<a href="%s" target="_blank" class="text-decoration-none text-dark fw-semibold text-truncate">%s</a>'
                    ) % (escape(urls['open']), escape(filename))
                    state_text = escape(meta)
                else:
                    title = escape(filename)
                    state_text = escape('Media is being downloaded from Meta.' if urls.get('pending') else 'Media not attached yet.')
                media = Markup(
                    '<div class="wa-msg-media mb-2 bg-white p-2 rounded border shadow-sm">'
                    '<div class="d-flex align-items-center gap-2">'
                    '<i class="fa %s fa-2x"></i>'
                    '<div class="min-w-0 flex-grow-1">%s'
                    '<div class="small text-muted text-truncate">%s</div></div>'
                    '</div>%s</div>'
                ) % (icon, title, state_text, actions)
                return media + fallback_content

            def _raw_interactive_payload(message):
                try:
                    raw = json.loads(message.raw_data or '{}')
                except Exception:
                    return {}
                if isinstance(raw, dict) and isinstance(raw.get('interactive'), dict):
                    return raw['interactive']
                if isinstance(raw, dict) and raw.get('type') and (raw.get('body') or raw.get('action')):
                    return raw
                return {}

            def _render_interactive_message(message, fallback_content):
                payload = _raw_interactive_payload(message)
                itype = message.interactive_type or payload.get('type') or 'interactive'
                if message.direction == 'inbound' and (
                    message.button_text or message.button_payload or message.list_item_title or message.list_item_id
                ):
                    label = message.button_text or message.list_item_title or message.body or 'Selected option'
                    value = message.button_payload or message.list_item_id or ''
                    return Markup(
                        '<div class="wa-msg-interactive wa-msg-interactive-reply bg-white border rounded p-2 shadow-sm">'
                        '<div class="small text-muted mb-1"><i class="fa fa-reply me-1"></i>Customer selected</div>'
                        '<div class="fw-semibold">%s</div>'
                        '%s'
                        '</div>'
                    ) % (
                        escape(label),
                        Markup('<div class="small text-muted text-break">%s</div>' % escape(value)) if value else Markup(''),
                    )

                header = payload.get('header') or {}
                body = (payload.get('body') or {}).get('text') or message.body or ''
                footer = (payload.get('footer') or {}).get('text') or ''
                header_html = Markup('')
                if header.get('type') == 'text' and header.get('text'):
                    header_html = Markup('<div class="fw-bold mb-1">%s</div>') % escape(header.get('text'))
                body_html = Markup('<div style="white-space:pre-wrap;">%s</div>') % escape(body)
                footer_html = Markup('<div class="small text-muted mt-2">%s</div>') % escape(footer) if footer else Markup('')
                action_html = Markup('')
                action = payload.get('action') or {}

                if itype == 'button':
                    buttons = action.get('buttons') or []
                    items = []
                    for btn in buttons:
                        reply = btn.get('reply') if isinstance(btn, dict) else {}
                        title = (reply or {}).get('title') or btn.get('title') if isinstance(btn, dict) else ''
                        button_id = (reply or {}).get('id') or ''
                        if title:
                            items.append(
                                '<div class="wa-template-button text-center fw-semibold" '
                                'style="border-top:1px solid #e9edef;padding:9px 10px;color:#00a884;background:#fff;">'
                                '<i class="fa fa-reply me-1"></i>%s%s</div>' % (
                                    escape(title),
                                    ('<div class="small text-muted fw-normal">%s</div>' % escape(button_id)) if button_id else '',
                                )
                            )
                    if items:
                        action_html = Markup('<div class="rounded overflow-hidden mt-2">%s</div>') % Markup(''.join(items))
                elif itype == 'list':
                    sections = action.get('sections') or []
                    rows_html = []
                    for section in sections:
                        section_title = section.get('title') or 'Options'
                        rows_html.append('<div class="small text-muted fw-bold mt-2">%s</div>' % escape(section_title))
                        for row in section.get('rows') or []:
                            rows_html.append(
                                '<div class="border-top py-2">'
                                '<div class="fw-semibold">%s</div>'
                                '%s'
                                '%s'
                                '</div>' % (
                                    escape(row.get('title') or row.get('id') or 'Option'),
                                    ('<div class="small text-muted">%s</div>' % escape(row.get('description'))) if row.get('description') else '',
                                    ('<div class="small text-muted text-break">%s</div>' % escape(row.get('id'))) if row.get('id') else '',
                                )
                            )
                    if rows_html:
                        action_html = Markup('<div class="wa-msg-list-options bg-white rounded mt-2 px-2">%s</div>') % Markup(''.join(rows_html))
                elif itype == 'cta_url':
                    params = action.get('parameters') or {}
                    label = message.button_text or params.get('display_text') or 'Open link'
                    url = message.button_url or params.get('url')
                    if url:
                        action_html = Markup(
                            '<div class="mt-2"><a href="%s" target="_blank" '
                            'class="btn btn-sm btn-outline-primary w-100">'
                            '<i class="fa fa-external-link me-1"></i>%s</a></div>'
                        ) % (escape(url), escape(label))
                elif itype in ('product', 'product_list', 'catalog_message'):
                    product_label = {
                        'product': 'Single product message',
                        'product_list': 'Product list message',
                        'catalog_message': 'Catalogue / shop message',
                    }.get(itype, 'Commerce message')
                    details = []
                    catalog_id = message.catalog_id or action.get('catalog_id')
                    if catalog_id:
                        details.append('Catalog: %s' % catalog_id)
                    if message.product_retailer_id:
                        details.append('Product: %s' % message.product_retailer_id)
                    action_html = Markup(
                        '<div class="wa-msg-commerce bg-white border rounded p-2 mt-2">'
                        '<div class="fw-semibold"><i class="fa fa-shopping-bag me-1"></i>%s</div>'
                        '%s</div>'
                    ) % (
                        escape(product_label),
                        Markup('<div class="small text-muted text-break">%s</div>' % escape(' | '.join(details))) if details else Markup(''),
                    )

                return Markup(
                    '<div class="wa-msg-interactive bg-light border rounded p-2">'
                    '<div class="small text-muted mb-1"><i class="fa fa-hand-pointer-o me-1"></i>%s</div>'
                    '%s%s%s%s</div>'
                ) % (escape(itype.replace('_', ' ').title()), header_html, body_html, footer_html, action_html)

            def _render_template_header(message, template):
                header_type = template.header_type
                filename = message.media_filename or template.header_media_filename or template.name or 'Attachment'
                if header_type == 'text' and template.header_text:
                    return Markup(
                        '<div class="wa-template-header-text fw-bold mb-2">%s</div>'
                    ) % _render_template_text(template, template.header_text)
                if header_type == 'image':
                    img_url = False
                    if message.media_file:
                        img_url = f"/web/image/whatsapp.message/{message.id}/media_file"
                    elif template.header_media_file:
                        img_url = f"/web/image/whatsapp.template/{template.id}/header_media_file"
                    elif message.media_url and str(message.media_url).startswith(('http://', 'https://')):
                        img_url = message.media_url
                    elif template.header_media_url and str(template.header_media_url).startswith(('http://', 'https://')):
                        img_url = template.header_media_url
                    if img_url:
                        return Markup(
                            '<div class="wa-template-header-media mb-2">'
                            '<img src="%s" class="img-fluid rounded" style="max-height:260px;width:100%%;object-fit:cover;"/>'
                            '</div>'
                        ) % escape(img_url)
                    return Markup(
                        '<div class="wa-template-header-media bg-light border rounded p-3 mb-2 text-center text-muted">'
                        '<i class="fa fa-image me-1"></i> Image header'
                        '</div>'
                    )
                if header_type == 'video':
                    video_url = False
                    if message.media_file:
                        video_url = f"/web/content/whatsapp.message/{message.id}/media_file"
                    elif template.header_media_file:
                        video_url = f"/web/content/whatsapp.template/{template.id}/header_media_file"
                    elif message.media_url and str(message.media_url).startswith(('http://', 'https://')):
                        video_url = message.media_url
                    elif template.header_media_url and str(template.header_media_url).startswith(('http://', 'https://')):
                        video_url = template.header_media_url
                    if video_url:
                        return Markup(
                            '<div class="wa-template-header-media mb-2">'
                            '<video src="%s" controls class="img-fluid rounded" style="max-height:260px;width:100%%;"></video>'
                            '</div>'
                        ) % escape(video_url)
                    return Markup(
                        '<div class="wa-template-header-media bg-dark rounded p-3 mb-2 text-center text-white">'
                        '<i class="fa fa-play-circle me-1"></i> Video header'
                        '</div>'
                    )
                if header_type == 'document':
                    doc_url = False
                    if message.media_file:
                        doc_url = f"/web/content/whatsapp.message/{message.id}/media_file"
                    elif template.header_media_file:
                        doc_url = f"/web/content/whatsapp.template/{template.id}/header_media_file"
                    elif message.media_url and str(message.media_url).startswith(('http://', 'https://')):
                        doc_url = message.media_url
                    elif template.header_media_url and str(template.header_media_url).startswith(('http://', 'https://')):
                        doc_url = template.header_media_url
                    icon = _document_icon_class(filename)
                    link_open = f'<a href="{escape(doc_url)}" target="_blank" class="text-decoration-none text-dark fw-semibold text-truncate">' if doc_url else '<span class="text-dark fw-semibold text-truncate">'
                    link_close = '</a>' if doc_url else '</span>'
                    return Markup(
                        '<div class="wa-template-header-document d-flex align-items-center bg-white border rounded p-2 mb-2 shadow-sm">'
                        '<i class="fa %s fa-2x me-2"></i>'
                        '<div class="min-w-0 flex-grow-1">%s%s%s'
                        '<div class="small text-muted">Document header</div></div>'
                        '</div>'
                    ) % (icon, Markup(link_open), escape(filename), Markup(link_close))
                return Markup('')

            def _render_template_buttons(template):
                if not template.has_buttons:
                    return Markup('')
                labels = []
                if template.button_type == 'quick_reply':
                    labels = [('fa-reply', template.button_text_1), ('fa-reply', template.button_text_2), ('fa-reply', template.button_text_3)]
                elif template.button_type == 'call_to_action':
                    labels = [('fa-external-link', template.cta_url_text), ('fa-phone', template.cta_phone_text)]
                elif template.button_type == 'copy_code':
                    labels = [('fa-copy', 'Copy code')]
                buttons = ''.join(
                    '<div class="wa-template-button text-center fw-semibold" '
                    'style="border-top:1px solid #e9edef;padding:9px 10px;color:#00a884;background:#fff;">'
                    f'<i class="fa {icon} me-1"></i>{escape(label)}</div>'
                    for icon, label in labels if label
                )
                if not buttons:
                    return Markup('')
                return Markup(
                    '<div class="wa-template-buttons rounded overflow-hidden mt-2" '
                    'style="box-shadow:0 1px 1px rgba(11,20,26,.08);">%s</div>'
                ) % Markup(buttons)

            if total_count > limit:
                html_parts.append(f'''
                    <div class="text-center my-4 o_whatsapp_load_more_container">
                        <button type="object" name="action_load_more" class="btn btn-sm btn-outline-secondary rounded-pill px-4 shadow-sm" data-limit-next="{limit + 100}">
                            <i class="fa fa-history me-1"></i> Load Older Messages ({total_count - limit} remaining)
                        </button>
                    </div>
                ''')

            for msg in reversed(messages):
                m_date_local = fields.Datetime.context_timestamp(self, msg.create_date) if msg.create_date else None
                m_date = m_date_local.date() if m_date_local else None
                if m_date != last_date:
                    local_today = fields.Datetime.context_timestamp(self, fields.Datetime.now()).date()
                    from datetime import timedelta
                    local_yesterday = local_today - timedelta(days=1)
                    if m_date == local_today:
                        label = 'Today'
                    elif m_date == local_yesterday:
                        label = 'Yesterday'
                    else:
                        label = m_date.strftime('%B %d, %Y') if m_date else ''
                    if label:
                        date_key = m_date.isoformat() if m_date else ''
                        html_parts.append(
                            f'<div class="text-center my-3 wa-date-separator" data-wa-date-label="{date_key}">'
                            f'<span class="wa-date-label">{label}</span></div>'
                        )
                    last_date = m_date

                direction = 'o_whatsapp_msg_outbound' if msg.direction == 'outbound' else 'o_whatsapp_msg_inbound'

                # WhatsApp-style status ticks (outbound only)
                status_icon = ''
                if msg.direction == 'outbound':
                    st = msg.status or 'sent'
                    if st in ('queued', 'draft'):
                        # Clock icon — message pending
                        status_icon = (
                            '<span class="wa-msg-tick wa-tick-pending">'
                            '<i class="fa fa-clock-o" style="font-size:0.7rem;"></i>'
                            '</span>'
                        )
                    elif st == 'sent':
                        # Single grey tick
                        status_icon = (
                            '<span class="wa-msg-tick wa-tick-sent" style="color:#8696a0;font-size:0.7rem;">'
                            '<i class="fa fa-check"></i>'
                            '</span>'
                        )
                    elif st == 'delivered':
                        # Double grey ticks
                        status_icon = (
                            '<span class="wa-msg-tick wa-tick-delivered" style="color:#8696a0;font-size:0.7rem;display:inline-flex;gap:-2px;">'
                            '<i class="fa fa-check"></i><i class="fa fa-check" style="margin-left:-4px;"></i>'
                            '</span>'
                        )
                    elif st == 'read':
                        # Double BLUE ticks
                        status_icon = (
                            '<span class="wa-msg-tick wa-tick-read" style="color:#34b7f1;font-size:0.7rem;display:inline-flex;gap:-2px;">'
                            '<i class="fa fa-check"></i><i class="fa fa-check" style="margin-left:-4px;"></i>'
                            '</span>'
                        )
                    elif st == 'failed':
                        status_icon = (
                            '<span class="wa-msg-tick wa-tick-failed" style="color:#ea0038;font-size:0.75rem;">'
                            '<i class="fa fa-exclamation-circle" title="Failed"></i>'
                            '</span>'
                        )

                # Format time in 12h WhatsApp style: "1:22 am" (Linux/Docker safe)
                if m_date_local:
                    _h = m_date_local.strftime('%I').lstrip('0') or '12'
                    _min = m_date_local.strftime('%M')
                    _ampm = m_date_local.strftime('%p').lower()
                    time_str = f'{_h}:{_min} {_ampm}'
                else:
                    time_str = ''

                content = escape(msg.body or '')

                if msg.message_type == 'template':
                    template = _template_record_for_message(msg)
                    template_name = escape(
                        msg.template_name
                        or (template._get_send_template_name() if template else False)
                        or 'Template'
                    )
                    if template:
                        content = Markup(template._render_customer_preview_html(
                            partner=record.partner_id,
                            message=msg,
                            body_override=msg.body or False,
                            shell=False,
                            compact=True,
                            include_template_name=True,
                        ))
                        date_key = m_date.isoformat() if m_date else ''
                        is_note = getattr(msg, 'is_internal_note', False)
                        note_class = ' wa-msg-internal-note' if is_note else ''
                        html_parts.append(
                            f'<div class="wa-message-row {direction}{note_class}" '
                            f'data-wa-message-id="{msg.id}" '
                            f'data-wa-message-date="{date_key}" '
                            f'data-wa-direction="{msg.direction}">'
                            f'<div class="o_whatsapp_msg_bubble">'
                            f'<div class="wa-msg-body">{content}</div>'
                            f'<div class="wa-msg-time">{time_str}{status_icon}</div>'
                            f'</div>'
                            f'</div>'
                        )
                        continue
                    header_html = _render_template_header(msg, template) if template else Markup('')
                    body_html = _render_template_text(template, msg.body or template.body or '') if template else content
                    footer_html = Markup(
                        '<div class="small text-muted mt-2">%s</div>'
                    ) % escape(template.footer) if template and template.footer else Markup('')
                    buttons_html = _render_template_buttons(template) if template else Markup('')
                    content = Markup(
                        '<div class="wa-msg-template-box bg-light border p-2 rounded mb-1" style="background-color:#f0f2f5!important;">'
                        '<div class="fw-bold text-muted small mb-2"><i class="fa fa-bolt me-1"></i>%s</div>'
                        '%s<div style="white-space:pre-wrap;">%s</div>%s%s</div>'
                    ) % (template_name, header_html, body_html, footer_html, buttons_html)
                elif msg.message_type in ('image', 'video', 'document', 'audio'):
                    content = _render_media_message(msg, content)
                elif msg.message_type == 'interactive' or msg.button_text or msg.button_payload or msg.list_item_title or msg.list_item_id:
                    content = _render_interactive_message(msg, content)

                date_key = m_date.isoformat() if m_date else ''
                is_note = getattr(msg, 'is_internal_note', False)
                note_class = ' wa-msg-internal-note' if is_note else ''

                # Complete bubble HTML: row > bubble > (body + time-row)
                html_parts.append(
                    f'<div class="wa-message-row {direction}{note_class}" '
                    f'data-wa-message-id="{msg.id}" '
                    f'data-wa-message-date="{date_key}" '
                    f'data-wa-direction="{msg.direction}">'
                    f'<div class="o_whatsapp_msg_bubble">'
                    f'<div class="wa-msg-body">{content}</div>'
                    f'<div class="wa-msg-time">{time_str}{status_icon}</div>'
                    f'</div>'
                    f'</div>'
                )

            record.history_html = Markup(''.join(html_parts))
