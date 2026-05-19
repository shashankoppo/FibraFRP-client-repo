# -*- coding: utf-8 -*-
from odoo import models, fields, api

class WhatsAppQuickReply(models.Model):
    """Canned responses for agents to use in chat"""
    _name = 'whatsapp.quick.reply'
    _description = 'WhatsApp Quick Reply (Canned Response)'
    _order = 'shortcut'

    name = fields.Char('Response Title', required=True)
    shortcut = fields.Char('Shortcut (e.g. /greet)', required=True, help="Keyword prefix for agents")
    message = fields.Text('Response Message', required=True)
    account_id = fields.Many2one('whatsapp.account', string='Account Filter', 
                                help="If set, this reply only appears for this account.")
    active = fields.Boolean('Active', default=True)
    
    _shortcut_unique = models.Constraint(
        'unique(shortcut)',
        'The shortcut must be unique!',
    )
