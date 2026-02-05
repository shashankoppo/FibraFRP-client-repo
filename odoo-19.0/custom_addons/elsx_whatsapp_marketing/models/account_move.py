# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    elsx_payment_risk = fields.Selection([
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk')
    ], string='Payment Risk Score', readonly=True)
    elsx_blockchain_proof_url = fields.Char('Blockchain Proof URL', readonly=True)

    def action_post(self):
        """Override post to send WhatsApp notification for invoices"""
        res = super(AccountMove, self).action_post()
        for move in self:
            if move.move_type == 'out_invoice':
                move._send_whatsapp_invoice_notification()
        return res

    def _send_whatsapp_invoice_notification(self):
        """Helper to send WhatsApp invoice notification"""
        account = self.env['whatsapp.account'].search([('active', '=', True)], limit=1)
        if not account:
            return

        partner = self.partner_id
        phone = partner.mobile or partner.phone
        if not phone:
            return

        # Personalize message
        message_body = (
            f"Hi {partner.name}!\n\n"
            f"Your Invoice *{self.name}* is ready.\n"
            f"Amount Due: {self.currency_id.symbol}{self.amount_total}\n"
            f"Due Date: {self.invoice_date_due}\n\n"
            f"Best regards,\n"
            f"{self.company_id.name}"
        )

        # Create message record
        self.env['whatsapp.message'].create({
            'account_id': account.id,
            'partner_id': partner.id,
            'phone_number': phone,
            'message_type': 'text',
            'body': message_body,
            'direction': 'outbound',
            'is_automated': True,
            'trigger_event': 'Invoice Posted',
        }).action_send()
