# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class WhatsAppQuickReply(models.Model):
    """Saved Quick Replies (canned responses) for agents"""
    _name = 'whatsapp.quick.reply'
    _description = 'WhatsApp Quick Reply Template'
    _rec_name = 'shortcut'
    _order = 'shortcut'

    shortcut = fields.Char('Shortcut', required=True, help='e.g. /greeting, /payment')
    name = fields.Char('Name', required=True)
    message = fields.Text('Message', required=True)
    account_id = fields.Many2one('whatsapp.account', string='Account', help='Leave blank for global')
    user_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.user)
    active = fields.Boolean('Active', default=True)
    use_count = fields.Integer('Use Count', default=0)
