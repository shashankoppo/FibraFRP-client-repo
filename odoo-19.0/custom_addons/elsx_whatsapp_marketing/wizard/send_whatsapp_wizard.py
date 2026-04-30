# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhatsAppSendWizard(models.TransientModel):
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message Wizard'

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    phone_number = fields.Char(
        'Direct Phone Number',
        help='Send to a number not in contacts (include country code, e.g. 917247558873)'
    )
    message_body = fields.Text('Message', required=True)

    def _normalize_phone(self, phone):
        """Strip +, spaces, dashes. Add 91 prefix for 10-digit Indian numbers."""
        if not phone:
            return phone
        clean = phone.strip().replace('+', '').replace('-', '').replace(' ', '')
        if len(clean) == 10 and clean[0] in '6789':
            clean = '91' + clean
        return clean

    def action_send(self):
        """Send WhatsApp message to selected partners or direct phone number"""
        self.ensure_one()
        sent_count = 0
        errors = []

        if not self.partner_ids and not self.phone_number:
            from odoo.exceptions import UserError
            raise UserError('Please select at least one recipient or enter a Direct Phone Number.')

        # Send to direct phone number if provided
        if self.phone_number:
            phone = self._normalize_phone(self.phone_number)
            try:
                self.account_id.send_message(
                    to_number=phone,
                    message_type='text',
                    body=self.message_body,
                )
                sent_count += 1
            except Exception as e:
                errors.append(f"{phone}: {str(e)}")

        # Send to each partner
        for partner in self.partner_ids:
            # Odoo 19 uses 'phone'; older versions had 'mobile' — handle gracefully
            phone = getattr(partner, 'mobile', None) or getattr(partner, 'phone', None)
            if not phone:
                errors.append(f"{partner.name}: No phone number on record")
                continue
            phone = phone.strip().replace(' ', '').replace('+', '')
            try:
                self.account_id.send_message(
                    to_number=phone,
                    message_type='text',
                    body=self.message_body,
                    partner_id=partner.id,
                )
                sent_count += 1
            except Exception as e:
                errors.append(f"{partner.name}: {str(e)}")

        if errors and not sent_count:
            raise UserError(_("All messages failed to send:\n%s") % "\n".join(errors))

        msg = f'WhatsApp messages sent to {sent_count} recipient(s).'
        if errors:
            msg += '\n\nWarnings:\n' + '\n'.join(errors)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Done' if not errors else 'Sent with Warnings',
                'message': msg,
                'type': 'success' if not errors else 'warning',
                'sticky': bool(errors),
            }
        }
