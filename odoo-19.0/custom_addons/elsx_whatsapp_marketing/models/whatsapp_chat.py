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

    # Sidebar hack for Team Inbox Form View
    active_chat_ids = fields.Many2many('whatsapp.chat', 'whatsapp_chat_sidebar_rel', 'chat_id', 'sidebar_id', compute='_compute_active_chats', string='Active Sidebar Chats')

    # CRM Integration
    lead_id = fields.Many2one('crm.lead', string='Active Lead', compute='_compute_lead', store=True)
    lead_state = fields.Char(related='lead_id.stage_id.name', string='Lead Stage', readonly=True)
    sale_order_count = fields.Integer(compute='_compute_crm_stats')
    invoice_count = fields.Integer(compute='_compute_crm_stats')

    # Input Area
    quick_reply_text = fields.Text('Quick Reply')
    quick_media_file = fields.Binary('Quick Attachment')
    quick_media_filename = fields.Char('Quick Filename')
    quick_template_id = fields.Many2one('whatsapp.template', string='Template')
    ai_suggested_reply = fields.Text('AI Suggested Reply', readonly=True)
    
    # Metadata
    tag_ids = fields.Many2many('res.partner.category', string='Labels')
    note_ids = fields.One2many('whatsapp.chat.note', 'chat_id', string='Internal Notes')
    session_open = fields.Boolean('24h Session Open', compute='_compute_session_open')

    # Related Fields
    partner_id_email = fields.Char(related='partner_id.email', readonly=True)
    partner_job_title = fields.Char(related='partner_id.function', readonly=True)
    partner_website = fields.Char(related='partner_id.website', readonly=True)
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

    @api.depends('message_ids', 'message_ids.create_date', 'message_ids.status')
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

    @api.depends('message_ids', 'message_ids.status', 'message_ids.direction')
    def _compute_unread_count(self):
        for record in self:
            record.unread_count = self.env['whatsapp.message'].search_count([
                ('chat_id_ref', '=', record.id),
                ('direction', '=', 'inbound'),
                ('status', '!=', 'read')
            ])

    @api.depends('message_ids', 'message_ids.create_date', 'message_ids.direction')
    def _compute_last_inbound(self):
        for record in self:
            last = record.message_ids.filtered(lambda m: m.direction == 'inbound').sorted('create_date', reverse=True)[:1]
            record.last_inbound_date = last.create_date if last else False

    def _compute_partner_profile_data(self):
        for record in self:
            record.partner_has_avatar = bool(record.partner_id.avatar_128) if record.partner_id else False

    def _compute_active_chats(self):
        all_chats = self.search([('is_archived', '=', False)], order='last_message_date desc')
        for record in self:
            record.active_chat_ids = all_chats

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

    def _compute_crm_stats(self):
        for record in self:
            if record.partner_id:
                record.sale_order_count = self.env['sale.order'].search_count([('partner_id', '=', record.partner_id.id)])
                record.invoice_count = self.env['account.move'].search_count([('partner_id', '=', record.partner_id.id), ('move_type', '=', 'out_invoice')])
            else:
                record.sale_order_count = 0
                record.invoice_count = 0

    @api.depends('last_inbound_date')
    def _compute_session_open(self):
        now = fields.Datetime.now()
        for record in self:
            if not record.last_inbound_date:
                record.session_open = False
                continue
            diff = now - record.last_inbound_date
            record.session_open = diff.total_seconds() < 86400

    # --- ACTIONS ---

    def action_send_quick_reply(self):
        self.ensure_one()
        body = self.quick_reply_text or self.env.context.get('default_quick_reply_text')
        if not body and not self.quick_media_file:
            return
            
        if not self.session_open and not self.quick_media_file:
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
        self.action_mark_as_read()
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
        self.env['mail.presence']._update_presence(self.env.user, inactivity_period=inactivity_ms)
        return True

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

    # History Rendering
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
                m_date = msg.create_date.date() if msg.create_date else None
                if m_date != last_date:
                    label = 'Today' if m_date == fields.Date.today() else m_date.strftime('%B %d, %Y')
                    html_parts.append(f'<div class="text-center my-3"><span class="wa-date-label">{label}</span></div>')
                    last_date = m_date
                
                direction = 'o_whatsapp_msg_outbound' if msg.direction == 'outbound' else 'o_whatsapp_msg_inbound'
                status_icon = ''
                if msg.direction == 'outbound':
                    icn = 'check' if msg.status in ['sent','delivered','read'] else 'clock-o'
                    col = '#34b7f1' if msg.status == 'read' else '#8696a0'
                    status_icon = f'<span style="color:{col};margin-left:4px;"><i class="fa fa-{icn}"></i></span>'
                
                time = msg.create_date.strftime('%H:%M') if msg.create_date else ''
                content = escape(msg.body or '')
                
                if msg.message_type in ['image', 'video', 'document', 'audio']:
                    if msg.attachment_ids:
                        attachment = msg.attachment_ids[0]
                        url = f"/web/content/{attachment.id}?access_token={attachment.access_token or ''}"
                        if msg.message_type == 'image':
                            content = Markup(f'<div class="wa-msg-media"><a href="{url}" class="wa-lightbox-trigger" data-media-type="image"><img src="{url}" class="img-fluid rounded" style="max-height: 250px;"/></a></div>') + content
                        elif msg.message_type == 'video':
                            content = Markup(f'<div class="wa-msg-media"><video src="{url}" controls class="img-fluid rounded" style="max-height: 250px;"/></div>') + content
                        elif msg.message_type == 'document':
                            content = Markup(f'<div class="wa-msg-media d-flex align-items-center bg-light p-2 rounded"><i class="fa fa-file-pdf-o fa-2x me-2 text-danger"></i><a href="{url}" target="_blank">{escape(attachment.name)}</a></div>') + content
                        elif msg.message_type == 'audio':
                            content = Markup(f'<div class="wa-msg-media"><audio src="{url}" controls style="height: 30px;"/></div>') + content
                    else:
                        if msg.message_type == 'image':
                            content = Markup(f'<div class="wa-msg-media d-flex align-items-center bg-light p-2 rounded border"><i class="fa fa-image fa-2x me-2 text-muted"></i><span class="text-muted small ms-2">Processing Image...</span></div>') + content
                        elif msg.message_type == 'video':
                            content = Markup(f'<div class="wa-msg-media d-flex align-items-center bg-light p-2 rounded border"><i class="fa fa-video-camera fa-2x me-2 text-muted"></i><span class="text-muted small ms-2">Processing Video...</span></div>') + content
                        elif msg.message_type == 'document':
                            content = Markup(f'<div class="wa-msg-media d-flex align-items-center bg-light p-2 rounded border"><i class="fa fa-file-text-o fa-2x me-2 text-muted"></i><span class="text-muted small ms-2">Processing Document...</span></div>') + content
                        elif msg.message_type == 'audio':
                            content = Markup(f'<div class="wa-msg-media d-flex align-items-center bg-light p-2 rounded border"><i class="fa fa-microphone fa-2x me-2 text-muted"></i><span class="text-muted small ms-2">Processing Audio...</span></div>') + content

                html_parts.append(f'<div class="o_whatsapp_msg_bubble {direction}"><div class="wa-msg-body">{content}</div><div class="wa-msg-time">{time}{status_icon}</div></div>')
            
            record.history_html = Markup(''.join(html_parts))


class WhatsAppConversationAssignment(models.Model):
    _name = 'whatsapp.conversation.assignment'
    _description = 'WhatsApp Conversation Assignment Log'
    _order = 'create_date desc'

    chat_id = fields.Many2one('whatsapp.chat', string='Conversation', required=True, ondelete='cascade')
    assigned_user_id = fields.Many2one('res.users', string='Assigned Agent', required=True)
    assigned_by = fields.Many2one('res.users', string='Assigned By')
    previous_user_id = fields.Many2one('res.users', string='Previous Agent')
    transfer_reason = fields.Selection([
        ('initial', 'Initial Assignment'),
        ('manual', 'Manual Transfer'),
        ('workload', 'Workload Balancing'),
        ('sticky', 'Sticky Routing'),
        ('bot', 'Bot Transfer'),
    ], string='Reason', default='manual')
