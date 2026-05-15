# -*- coding: utf-8 -*-
from odoo import models, fields, api

class WhatsAppNewChatWizard(models.TransientModel):
    _name = 'whatsapp.new.chat.wizard'
    _description = 'Start New WhatsApp Conversation'

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    partner_id = fields.Many2one('res.partner', string='Select Contact')
    phone_number = fields.Char('Phone Number', help='Enter phone number with country code if not selecting a contact')

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if self.partner_id:
            mobile = getattr(self.partner_id, 'mobile', False)
            self.phone_number = mobile or self.partner_id.phone

    def action_start_chat(self):
        self.ensure_one()
        phone = self.phone_number
        if not phone and self.partner_id:
            mobile = getattr(self.partner_id, 'mobile', False)
            phone = mobile or self.partner_id.phone
        
        if not phone:
            from odoo.exceptions import UserError
            raise UserError("Please provide a phone number.")

        # Normalize and validate phone before opening a conversation
        phone = self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id, strict=True)
        
        # Find or create chat
        chat = self.env['whatsapp.chat'].sudo().search([
            ('account_id', '=', self.account_id.id),
            ('phone_number', '=', phone)
        ], limit=1)
        
        if not chat:
            chat = self.env['whatsapp.chat'].sudo().create({
                'account_id': self.account_id.id,
                'phone_number': phone,
                'partner_id': self.partner_id.id if self.partner_id else False,
            })
            
        return chat.action_open_chat()
