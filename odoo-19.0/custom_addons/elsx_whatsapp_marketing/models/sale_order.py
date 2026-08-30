# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


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
        res = super(SaleOrder, self).action_confirm()
        auto_send = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.sale.confirmation.auto_send',
            default='False',
        )
        if str(auto_send).lower() != 'true':
            return res
        for order in self:
            order._send_whatsapp_confirmation()
        return res

    def _send_whatsapp_confirmation(self):
        """Helper to send WhatsApp confirmation message"""
        account = self.env['whatsapp.account']._get_default_account()
        if not account:
            return

        partner = self.partner_id
        phone = getattr(partner, 'mobile', False) or partner.phone
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

        try:
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
            message.action_send()
        except Exception as exc:
            if 'message' in locals():
                message.sudo().write({
                    'status': 'failed',
                    'error_message': str(exc),
                })
            _logger.exception("Failed to send WhatsApp order confirmation for %s", self.name)

    def action_open_whatsapp_link(self):
        self.ensure_one()
        message = _(
            "Hello %(customer)s,\n\n"
            "Regarding your order %(order)s for %(amount)s.\n\n"
            "Thank you."
        ) % {
            'customer': self.partner_id.display_name,
            'order': self.name,
            'amount': self.currency_id.format(self.amount_total),
        }
        return self.partner_id._elsx_open_whatsapp_link(message=message, title=_('Open WhatsApp'))
