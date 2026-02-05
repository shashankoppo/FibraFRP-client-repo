# -*- coding: utf-8 -*-
from odoo import models, fields


class WhatsAppContact(models.Model):
    _name = 'whatsapp.contact'
    _description = 'WhatsApp Contact'
    _rec_name = 'name'

    name = fields.Char('Name', required=True)
    phone_number = fields.Char('Phone Number', required=True)
    partner_id = fields.Many2one('res.partner', string='Related Contact')
    
    # Opt-in status
    opt_in = fields.Boolean('Opted In', default=True)
    opt_in_date = fields.Datetime('Opt-in Date')
    opt_out_date = fields.Datetime('Opt-out Date')
    
    # Conversation status
    last_message_date = fields.Datetime('Last Message')
    last_message_direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Last Message Direction')
    
    # Tags and segmentation
    tag_ids = fields.Many2many('whatsapp.contact.tag', string='Tags')
    
    # Statistics
    message_count = fields.Integer('Total Messages', default=0)
    campaign_count = fields.Integer('Campaigns Received', default=0)
    
    active = fields.Boolean('Active', default=True)


class WhatsAppContactTag(models.Model):
    _name = 'whatsapp.contact.tag'
    _description = 'WhatsApp Contact Tag'
    _rec_name = 'name'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color', default=1)
    contact_ids = fields.Many2many('whatsapp.contact', string='Contacts')
