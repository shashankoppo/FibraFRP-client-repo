# -*- coding: utf-8 -*-
from odoo import models, fields, api

class WhatsAppChat(models.Model):
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc'
    _rec_name = 'display_name'

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact')
    phone_number = fields.Char('Phone Number', required=True)
    
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    
    message_ids = fields.One2many('whatsapp.message', 'chat_id_ref', string='Messages')
    
    last_message_date = fields.Datetime('Last Message Date', compute='_compute_last_message', store=True)
    last_message_body = fields.Text('Last Message', compute='_compute_last_message', store=True)
    
    unread_count = fields.Integer('Unread Count', compute='_compute_unread_count')
    quick_reply_text = fields.Text('Quick Reply')
    
    @api.depends('phone_number', 'partner_id')
    def _compute_display_name(self):
        for record in self:
            name = record.partner_id.name if record.partner_id else record.phone_number
            record.display_name = f"{name} ({record.account_id.name})"

    @api.depends('message_ids')
    def _compute_last_message(self):
        for record in self:
            last_msg = self.env['whatsapp.message'].search([
                ('chat_id_ref', '=', record.id)
            ], order='create_date desc', limit=1)
            if last_msg:
                record.last_message_date = last_msg.create_date
                record.last_message_body = last_msg.body or last_msg.caption or f"[{last_msg.message_type}]"
            else:
                record.last_message_date = False
                record.last_message_body = False

    def _compute_unread_count(self):
        for record in self:
            record.unread_count = self.env['whatsapp.message'].search_count([
                ('chat_id_ref', '=', record.id),
                ('direction', '=', 'inbound'),
                ('status', '!=', 'read')
            ])

    def action_mark_as_read(self):
        """Mark all inbound messages in this chat as read"""
        for record in self:
            messages = record.message_ids.filtered(lambda m: m.direction == 'inbound' and m.status != 'read')
            messages.write({'status': 'read', 'read_date': fields.Datetime.now()})
        return True

    def action_send_quick_reply(self):
        """Send a quick reply message and clear the text box"""
        self.ensure_one()
        if not self.quick_reply_text:
            return
        
        # Create the message
        message = self.env['whatsapp.message'].create({
            'account_id': self.account_id.id,
            'phone_number': self.phone_number,
            'body': self.quick_reply_text,
            'direction': 'outbound',
            'message_type': 'text',
            'chat_id_ref': self.id,
        })
        
        # Send it
        message.action_send()
        
        # Clear the box
        self.quick_reply_text = False
        return True

    def action_open_chat(self):
        self.ensure_one()
        self.action_mark_as_read()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Chat with {self.display_name}',
            'res_model': 'whatsapp.chat',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_open_send_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reply via WhatsApp',
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_account_id': self.account_id.id,
                'default_partner_ids': [(4, self.partner_id.id)] if self.partner_id else [],
                'default_phone_number': self.phone_number,
            },
        }
