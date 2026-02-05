# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WhatsAppCampaignStep(models.Model):
    _name = 'whatsapp.campaign.step'
    _description = 'WhatsApp Drip Campaign Step'
    _order = 'sequence'

    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign', required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Step Name', required=True)
    
    # Timing
    delay_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
    ], string='Delay Type', default='days')
    delay_unit = fields.Integer('Delay Unit', default=1)
    
    # Content
    template_id = fields.Many2one('whatsapp.template', string='Template')
    message_body = fields.Text('Message Body')
    
    # Conditions
    condition_type = fields.Selection([
        ('none', 'No Condition'),
        ('last_read', 'If Last Message Was Read'),
        ('last_not_read', 'If Last Message Was NOT Read'),
    ], string='Condition', default='none')
