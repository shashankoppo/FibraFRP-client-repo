# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # WhatsApp fields only - removed problematic ELSX fields
    whatsapp_message_ids = fields.One2many('whatsapp.message', 'partner_id', string='WhatsApp Message History')
    whatsapp_message_count = fields.Integer('WhatsApp Message Count', compute='_compute_whatsapp_count')
    whatsapp_opt_in = fields.Boolean('WhatsApp Opt-in', default=True, help='Contact has opted in to receive WhatsApp messages')
    whatsapp_last_message_date = fields.Datetime('Last WhatsApp Message', compute='_compute_whatsapp_last_message')
    
    @api.depends('whatsapp_message_ids')
    def _compute_whatsapp_count(self):
        for partner in self:
            partner.whatsapp_message_count = len(partner.whatsapp_message_ids)
    
    @api.depends('whatsapp_message_ids.create_date')
    def _compute_whatsapp_last_message(self):
        for partner in self:
            if partner.whatsapp_message_ids:
                partner.whatsapp_last_message_date = max(partner.whatsapp_message_ids.mapped('create_date'))
            else:
                partner.whatsapp_last_message_date = False
    
    def action_send_whatsapp(self):
        """Open wizard to send WhatsApp message"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_ids': [(6, 0, self.ids)],
            }
        }
    
    def action_view_whatsapp_messages(self):
        """View all WhatsApp messages for this contact"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Messages',
            'res_model': 'whatsapp.message',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id}
        }
