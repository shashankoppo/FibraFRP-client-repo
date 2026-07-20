# -*- coding: utf-8 -*-
from odoo import models, fields


class WhatsAppChatNote(models.Model):
    """Internal agent notes on a chat — not sent to WhatsApp"""
    _name = 'whatsapp.chat.note'
    _description = 'Chat Internal Note'
    _order = 'create_date desc'

    chat_id = fields.Many2one('whatsapp.chat', string='Chat', required=True, ondelete='cascade', index=True)
    assigned_user_id = fields.Many2one('res.users', string='Agent', default=lambda self: self.env.user, required=True)
    body = fields.Text('Note', required=True)
    create_date = fields.Datetime('Created', readonly=True)

    # Display helpers
    user_name = fields.Char(related='assigned_user_id.name', string='Agent Name', store=True)
    user_avatar = fields.Binary(related='assigned_user_id.image_128', string='Avatar')
