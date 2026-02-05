# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    elsx_delivery_priority = fields.Selection([
        ('luxury', 'ELSX Luxury (Same Day)'),
        ('high', 'High Priority'),
        ('standard', 'Standard')
    ], string='Delivery Priority', default='standard')
    elsx_blockchain_hash_short = fields.Char('Blockchain Proof', readonly=True)
    elsx_ai_discount_recommendation = fields.Float('AI Discount Rec (%)', readonly=True)

    def action_confirm(self):
        """Override confirm to send WhatsApp notification"""
        res = super(SaleOrder, self).action_confirm()
        for order in self:
            order._send_whatsapp_confirmation()
        return res

    def _send_whatsapp_confirmation(self):
        """Helper to send WhatsApp confirmation message"""
        # Find active WhatsApp account
        account = self.env['whatsapp.account'].search([('active', '=', True)], limit=1)
        if not account:
            return

        partner = self.partner_id
        phone = partner.mobile or partner.phone
        if not phone:
            return

        # Personalize message
        message_body = (
            f"Hello {partner.name}!\n\n"
            f"Your Order *{self.name}* has been confirmed.\n"
            f"Total Amount: {self.currency_id.symbol}{self.amount_total}\n"
            f"We will notify you once it's shipped.\n\n"
            f"Thank you for choosing ELSX ERP!"
        )

        # Create message record
        message = self.env['whatsapp.message'].create({
            'account_id': account.id,
            'partner_id': partner.id,
            'phone_number': phone,
            'message_type': 'text',
            'body': message_body,
            'direction': 'outbound',
            'is_automated': True,
            'trigger_event': 'Order Confirmation',
        })

        # Send asynchronously/retry in background if needed
        try:
            message.action_send()
        except Exception:
            pass # Fails silently for now, status will be 'failed' in Odoo
