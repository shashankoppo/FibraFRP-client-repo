# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
from markupsafe import Markup, escape

_logger = logging.getLogger(__name__)

class WhatsAppChat(models.Model):
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc'
    _rec_name = 'display_name'

    @api.model
    def _get_or_create_chat(self, account_id, phone_number):
        """Find or create a conversation for a specific phone number and account"""
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
            if chat.is_archived or chat.state in ('snoozed', 'resolved'):
                chat.sudo().write({'state': 'open', 'is_archived': False})
        return chat

    # --- CORE FIELDS ---
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact')
    assigned_user_id = fields.Many2one('res.users', string='Assigned Agent', index=True, default=lambda self: self.env.user)
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
            last_inbound = record.message_ids.filtered(lambda m: m.direction == 'inbound').sorted('create_date', reverse=True)[:1]
            last_outbound = record.message_ids.filtered(lambda m: m.direction == 'outbound').sorted('create_date', reverse=True)[:1]
            
            if last_inbound:
                if last_outbound and last_outbound.create_date > last_inbound.create_date:
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
    ai_suggested_reply = fields.Text('AI Suggested Reply', readonly=True)
    
    # Metadata
    tag_ids = fields.Many2many('res.partner.category', string='Labels')
    note_ids = fields.One2many('whatsapp.chat.note', 'chat_id', string='Internal Notes')
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
        This is a simple implementation for UI rendering; in production you may replace
        with a more efficient lazy‑loaded approach.
        """
        active_chats = self.env['whatsapp.chat'].search([('state', '=', 'open')])
        request_chats = self.env['whatsapp.chat'].search([('state', '=', 'snoozed')])
        intervened_chats = self.env['whatsapp.chat'].search([('state', '=', 'resolved')])
        for rec in self:
            rec.active_chat_ids = active_chats
            rec.request_chat_ids = request_chats
            rec.intervened_chat_ids = intervened_chats

    @api.depends('message_ids.create_date', 'message_ids.body', 'message_ids.status', 'message_ids.direction', 'message_ids.message_type')
    def _compute_last_message(self):
        for record in self:
            last = record.message_ids.sorted('create_date', reverse=True)[:1]
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
                unread_msgs.write({'status': 'read'})
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
            last = record.message_ids.filtered(lambda m: m.direction == 'inbound').sorted('create_date', reverse=True)[:1]
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
        """Mirror a new inbound WhatsApp message into the linked CRM lead chatter."""
        for chat in self:
            if not message or message.direction != 'inbound':
                continue

            lead = chat.lead_id
            if not lead and chat.partner_id:
                lead = self.env['crm.lead'].sudo().search([
                    ('partner_id', '=', chat.partner_id.id),
                    ('active', '=', True),
                ], order='create_date desc', limit=1)
            if not lead:
                continue

            marker = f'data-wa-message-id="{message.id}"'
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
            body = Markup(
                '<div data-wa-message-id="%s">'
                '<strong>WhatsApp inbound from %s</strong><br/>%s'
                '</div>'
            ) % (message.id, escape(sender), content_html)

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
    def get_sidebar_chats(self, filter_type='all', search_query='', offset=0, limit=50, pane=None, **kwargs):
        domain = [('is_archived', '=', False)]
        
        # Pane logic (Three-pane UI)
        if pane == 'active':
            domain.append(('assigned_user_id', '=', self.env.user.id))
        elif pane == 'request':
            # Chats that are unassigned
            domain.append(('assigned_user_id', '=', False))
        elif pane == 'intervened':
            # Chats assigned to OTHER users
            domain.append(('assigned_user_id', '!=', False))
            domain.append(('assigned_user_id', '!=', self.env.user.id))
        
        if filter_type == 'open':
            import datetime
            cutoff = fields.Datetime.now() - datetime.timedelta(days=1)
            domain.append(('last_inbound_date', '>=', cutoff))
            domain.append(('state', '=', 'open'))
        elif filter_type == 'mine':
            domain.append(('assigned_user_id', '=', self.env.user.id))
        elif filter_type == 'unread':
            domain.append(('unread_count', '>', 0))
        elif filter_type == 'resolved':
            domain.append(('state', '=', 'resolved'))
        elif filter_type == 'snoozed':
            domain.append(('state', '=', 'snoozed'))

        if search_query:
            domain.append('|')
            domain.append(('display_name', 'ilike', search_query))
            domain.append(('phone_number', 'ilike', search_query))

        chats = self.search(domain, order='last_message_date desc, id desc', offset=int(offset), limit=int(limit))
        
        result = []
        for chat in chats:
            result.append({
                'id': chat.id,
                'display_name': chat.display_name or chat.phone_number,
                'display_name_initial': chat.display_name_initial,
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
            })
        return result

    @api.model
    def get_sidebar_counts(self, filter_type='all', search_query='', **kwargs):
        """Returns the actual database counts of chats in the three panes (active, request, intervened)"""
        counts = {
            'active': 0,
            'request': 0,
            'intervened': 0,
        }
        
        base_domain = [('is_archived', '=', False)]
        
        if filter_type == 'open':
            import datetime
            cutoff = fields.Datetime.now() - datetime.timedelta(days=1)
            base_domain.append(('last_inbound_date', '>=', cutoff))
            base_domain.append(('state', '=', 'open'))
        elif filter_type == 'unread':
            base_domain.append(('unread_count', '>', 0))
        elif filter_type == 'resolved':
            base_domain.append(('state', '=', 'resolved'))
        elif filter_type == 'snoozed':
            base_domain.append(('state', '=', 'snoozed'))

        if search_query:
            base_domain.append('|')
            base_domain.append(('display_name', 'ilike', search_query))
            base_domain.append(('phone_number', 'ilike', search_query))

        # Count active (Mine)
        domain_active = base_domain + [('assigned_user_id', '=', self.env.user.id)]
        counts['active'] = self.search_count(domain_active)

        # Count request (Unassigned)
        domain_request = base_domain + [('assigned_user_id', '=', False)]
        counts['request'] = self.search_count(domain_request)

        # Count intervened (All other assigned users)
        domain_intervened = base_domain + [
            ('assigned_user_id', '!=', False),
            ('assigned_user_id', '!=', self.env.user.id)
        ]
        counts['intervened'] = self.search_count(domain_intervened)

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
        if self.quick_template_id:
            self.env['whatsapp.send.wizard'].create({
                'account_id': self.account_id.id,
                'template_id': self.quick_template_id.id,
                'phone_number': self.phone_number,
                'partner_ids': [(4, self.partner_id.id)] if self.partner_id else False,
            }).action_send()
            self.quick_template_id = False
        return True

    def action_mark_as_read(self):
        for record in self:
            unread = record.message_ids.filtered(lambda m: m.direction == 'inbound' and m.status != 'read')
            unread.sudo().write({'status': 'read'})
        return True

    def action_resolve(self):
        self.write({'state': 'resolved', 'is_archived': True})

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
            'target': 'current',
        }

    def action_reload_chat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.chat',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context, active_test=False),
        }

    def action_open_meta_manager(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://business.facebook.com/wa/manage/message-templates/',
            'target': 'new',
        }

    def action_generate_ai_reply(self):
        """Draft a reply from the current conversation context without sending it."""
        self.ensure_one()
        last_inbound = self.message_ids.filtered(lambda m: m.direction == 'inbound').sorted('create_date', reverse=True)[:1]
        customer_name = self.display_name or 'there'
        incoming = (last_inbound.body if last_inbound else '') or ''
        if 'elsx.marketing.ai' in self.env.registry.models:
            ai_record = self.env['elsx.marketing.ai'].sudo().create({
                'name': f'WhatsApp reply draft for {customer_name}',
                'target_audience': f'WhatsApp contact {customer_name}: {incoming[:200]}',
                'platform': 'email',
            })
            ai_record.action_generate_content()
            draft = (ai_record.generated_content or '').split('\n\n', 1)[-1].strip()
        else:
            draft = (
                f"Hi {customer_name}, thanks for your message. "
                "I am checking this now and will help you with the next step."
            )
        self.write({
            'ai_suggested_reply': draft,
            'quick_reply_text': draft,
        })
        return True

    def action_touch_agent_presence(self, is_active=True):
        """Let the inbox tab refresh Odoo presence so routing can avoid inactive agents."""
        inactivity_ms = 0 if is_active else (31 * 60 * 1000)
        try:
            with self.env.cr.savepoint():
                self.env['mail.presence']._update_presence(self.env.user, inactivity_period=inactivity_ms)
        except Exception as e:
            _logger.warning("Failed to update agent presence due to lock/concurrency contention: %s", e)
        return True

    @api.model
    def get_sidecar_url(self):
        """Retrieve the sidecar url securely for standard users without AccessError on ir.config_parameter"""
        return self.env['ir.config_parameter'].sudo().get_param('whatsapp.sidecar.url') or ''

    def action_open_send_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_chat_id': self.id,
                'default_phone_number': self.phone_number,
                'default_partner_id': self.partner_id.id if self.partner_id else False,
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
                'target': 'current',
            }
        return False

    def action_clear_media(self):
        self.write({'quick_media_file': False, 'quick_media_filename': False})
        return True

    def _auto_assign_agent(self):
        for chat in self:
            root = self.env.ref('base.user_root', raise_if_not_found=False)
            root_id = root.id if root else False
            if chat.assigned_user_id and chat.assigned_user_id.id != root_id:
                continue
            
            # Sticky Routing
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
                    continue

            # Workload-aware routing: prefer available team members, then fall back to internal users.
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
                under_cap = target_pool.filtered(lambda u: counts.get(u.id, 0) < max_by_user.get(u.id, 10))
                target_pool = under_cap or target_pool
                
                # Sort pool by count (least busy first)
                target_pool = target_pool.sorted(key=lambda u: counts.get(u.id, 0))
                
                assigned_agent = target_pool[0]
                previous_user = chat.assigned_user_id
                chat.write({'assigned_user_id': assigned_agent.id})
                
                # Log assignment
                self.env['whatsapp.conversation.assignment'].sudo().create({
                    'chat_id': chat.id,
                    'assigned_user_id': assigned_agent.id,
                    'assigned_by': self.env.user.id,
                    'previous_user_id': previous_user.id if previous_user else False,
                    'transfer_reason': 'workload',
                })

    # History Rendering — explicitly depends on message fields so cache invalidates on new/updated messages
    history_html = fields.Html('History HTML', compute='_compute_history_html', sanitize=False)
    
    def action_load_more(self):
        self.ensure_one()
        limit = int(self.env.context.get('wa_history_limit', 100)) + 100
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.chat',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context, wa_history_limit=limit, active_test=False),
        }

    @api.depends('message_ids', 'message_ids.body', 'message_ids.status',
                 'message_ids.create_date', 'message_ids.direction',
                 'message_ids.message_type', 'message_ids.media_file',
                 'message_ids.media_url')
    @api.depends_context('wa_ts', 'wa_history_limit')
    def _compute_history_html(self):
        for record in self:
            html_parts = []
            last_date = None
            all_messages = record.message_ids.sudo()
            total_count = len(all_messages)
            limit = self.env.context.get('wa_history_limit', 100)
            messages = all_messages.sorted('create_date', reverse=True)[:limit]
            
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
                    template_name = escape(msg.template_name or 'Template')
                    content = Markup(
                        f'<div class="wa-msg-template-box bg-light border p-2 rounded mb-1" style="background-color:#f0f2f5!important;">'
                        f'<div class="fw-bold text-muted small mb-1"><i class="fa fa-bolt me-1"></i>{template_name}</div>'
                        f'{content}</div>'
                    )
                elif msg.message_type in ('image', 'video', 'document', 'audio'):
                    if msg.media_file or msg.media_url:
                        if msg.media_file:
                            url = f"/web/image/whatsapp.message/{msg.id}/media_file"
                            if msg.message_type in ('video', 'document', 'audio'):
                                url = f"/web/content/whatsapp.message/{msg.id}/media_file"
                        else:
                            url = msg.media_url
                        if msg.message_type == 'image':
                            content = Markup(
                                f'<div class="wa-msg-media mb-1">'
                                f'<a href="{url}" class="wa-lightbox-trigger" data-media-type="image">'
                                f'<img src="{url}" class="img-fluid rounded shadow-sm" style="max-height:250px;"/>'
                                f'</a></div>'
                            ) + content
                        elif msg.message_type == 'video':
                            content = Markup(
                                f'<div class="wa-msg-media mb-1">'
                                f'<video src="{url}" controls class="img-fluid rounded shadow-sm" style="max-height:250px;"></video>'
                                f'</div>'
                            ) + content
                        elif msg.message_type == 'document':
                            fname = escape(msg.media_filename or 'Document')
                            content = Markup(
                                f'<div class="wa-msg-media mb-1 d-flex align-items-center bg-white p-2 rounded border shadow-sm">'
                                f'<i class="fa fa-file-pdf-o fa-2x me-2 text-danger"></i>'
                                f'<a href="{url}" target="_blank" class="text-decoration-none text-dark fw-bold text-truncate" style="max-width:200px;">{fname}</a>'
                                f'</div>'
                            ) + content
                        elif msg.message_type == 'audio':
                            content = Markup(
                                f'<div class="wa-msg-media mb-1">'
                                f'<audio src="{url}" controls style="height:40px;width:100%;"></audio>'
                                f'</div>'
                            ) + content
                    else:
                        icons = {'image': 'fa-image', 'video': 'fa-video-camera', 'document': 'fa-file-text-o', 'audio': 'fa-microphone'}
                        labels = {'image': 'Processing Image...', 'video': 'Processing Video...', 'document': 'Processing Document...', 'audio': 'Processing Audio...'}
                        icon_cls = icons.get(msg.message_type, 'fa-file')
                        label_txt = labels.get(msg.message_type, 'Processing...')
                        content = Markup(
                            f'<div class="wa-msg-media d-flex align-items-center bg-light p-2 rounded border mb-1">'
                            f'<i class="fa {icon_cls} fa-2x me-2 text-muted"></i>'
                            f'<span class="text-muted small ms-2">{label_txt}</span>'
                            f'</div>'
                        ) + content

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

