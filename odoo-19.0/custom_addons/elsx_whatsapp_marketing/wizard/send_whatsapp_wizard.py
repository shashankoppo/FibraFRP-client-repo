# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WhatsAppSendWizard(models.TransientModel):
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message Wizard'

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    partner_ids = fields.Many2many('res.partner', string='Recipients', required=True)
    message_body = fields.Text('Message', required=True)

    def action_send(self):
        """Send WhatsApp message to selected partners"""
        for partner in self.partner_ids:
            phone = partner.mobile or partner.phone
            if not phone:
                continue
            
            # Create and send message
            message = self.env['whatsapp.message'].create({
                'account_id': self.account_id.id,
                'partner_id': partner.id,
                'phone_number': phone,
                'message_type': 'text',
                'body': self.message_body,
                'direction': 'outbound',
            })
            
            try:
                message.action_send()
            except Exception as e:
                pass  # Error is logged in the message record
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Messages Sent',
                'message': f'WhatsApp messages sent to {len(self.partner_ids)} recipients',
                'type': 'success',
            }
        }
