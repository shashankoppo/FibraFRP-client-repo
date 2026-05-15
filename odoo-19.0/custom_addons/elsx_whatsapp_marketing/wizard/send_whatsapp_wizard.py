# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhatsAppSendWizard(models.TransientModel):
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message Wizard'

    @api.model
    def _default_account_id(self):
        return self.env['whatsapp.account'].search([('active', '=', True)], limit=1)

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, default=_default_account_id)
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    phone_number = fields.Char(
        'Direct Phone Number',
        help='Send to a number not in contacts (include country code, e.g. 917247558873)'
    )
    template_id = fields.Many2one(
        'whatsapp.template',
        string='Template',
        domain="[('account_id', '=', account_id), ('status', '=', 'approved')]",
    )
    media_file = fields.Binary('Media / Voice File')
    media_filename = fields.Char('Media Filename')
    message_body = fields.Text('Message', help="Leave empty to use template body or send media without a caption")

    def _normalize_phone(self, phone):
        """Normalize and validate recipient numbers before calling Meta."""
        return self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id, strict=True)

    def _detect_media_type(self):
        filename = (self.media_filename or '').lower()
        if filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            return 'image'
        if filename.endswith(('.mp4', '.mov', '.avi', '.3gp')):
            return 'video'
        if filename.endswith(('.mp3', '.ogg', '.wav', '.aac', '.m4a', '.opus')):
            return 'audio'
        return 'document'

    def _send_to_recipient(self, phone, partner=False):
        partner_id = partner.id if partner else False
        if self.template_id:
            self.account_id.send_message(
                to_number=phone,
                message_type='template',
                template_record=self.template_id,
                partner_id=partner_id,
            )
            return

        if self.media_file:
            media_type = self._detect_media_type()
            message = self.env['whatsapp.message'].create({
                'account_id': self.account_id.id,
                'phone_number': phone,
                'partner_id': partner_id,
                'message_type': media_type,
                'body': self.message_body or False,
                'caption': self.message_body if media_type in ('image', 'video', 'document') else False,
                'media_file': self.media_file,
                'media_filename': self.media_filename or 'attachment',
                'direction': 'outbound',
            })
            message.action_send()
            return

        self.account_id.send_message(
            to_number=phone,
            message_type='text',
            body=self.message_body,
            partner_id=partner_id,
        )

    def action_send(self):
        """Send WhatsApp message to selected partners or direct phone number"""
        self.ensure_one()
        sent_count = 0
        errors = []

        if not self.partner_ids and not self.phone_number:
            raise UserError(_('Please select at least one recipient or enter a Direct Phone Number.'))

        # Send to direct phone number if provided
        if self.phone_number:
            phone = self._normalize_phone(self.phone_number)
            try:
                self._send_to_recipient(phone)
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
            phone = self._normalize_phone(phone)
            try:
                self._send_to_recipient(phone, partner=partner)
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
