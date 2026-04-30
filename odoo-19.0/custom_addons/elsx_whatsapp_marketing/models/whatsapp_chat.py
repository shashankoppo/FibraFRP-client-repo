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

    def action_open_chat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Chat with {self.display_name}',
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('chat_id_ref', '=', self.id)],
            'context': {
                'default_chat_id_ref': self.id,
                'default_phone_number': self.phone_number,
                'default_account_id': self.account_id.id,
                'default_partner_id': self.partner_id.id,
            }
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
