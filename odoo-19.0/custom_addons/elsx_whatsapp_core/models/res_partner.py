# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # WhatsApp fields only - removed problematic ELSX fields
    whatsapp_message_ids = fields.One2many('whatsapp.message', 'partner_id', string='WhatsApp Message History')
    whatsapp_message_count = fields.Integer('WhatsApp Message Count', compute='_compute_whatsapp_count')
    whatsapp_opt_in = fields.Boolean('WhatsApp Opt-in', default=True, help='Contact has opted in to receive WhatsApp messages')
    whatsapp_last_message_date = fields.Datetime('Last WhatsApp Message', compute='_compute_whatsapp_last_message')
    whatsapp_custom_attributes = fields.Text(
        'WhatsApp Custom Attributes',
        default='{}',
        help='JSON object populated by WhatsApp bot flows and campaign reply automations.',
    )
    whatsapp_last_exclusion_reason = fields.Char(
        'Last WhatsApp Exclusion Reason',
        help='Why this contact was most recently excluded from a WhatsApp campaign audience.',
    )
    whatsapp_last_reply_action = fields.Char(
        'Last WhatsApp Reply Action',
        help='Last automation action applied because this contact replied to a campaign/template.',
    )

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

    @api.model_create_multi
    def create(self, vals_list):
        records = super(ResPartner, self).create(vals_list)
        for record in records:
            record._sync_to_whatsapp_contact()
        return records

    def write(self, vals):
        res = super(ResPartner, self).write(vals)
        fields_to_check = ['name', 'phone', 'whatsapp_opt_in']
        if 'mobile' in self._fields:
            fields_to_check.append('mobile')
        if any(f in vals for f in fields_to_check):
            for record in self:
                record._sync_to_whatsapp_contact()
        return res

    def _sync_to_whatsapp_contact(self):
        self.ensure_one()
        if self.env.context.get('skip_whatsapp_contact_sync'):
            return

        phone = getattr(self, 'mobile', False) or self.phone
        if not phone:
            return

        normalized_phone = phone
        try:
            account = self.env['whatsapp.account'].sudo()._get_default_account()
            normalized_phone = self.env['whatsapp.message']._normalize_phone(phone, account=account)
        except Exception:
            normalized_phone = ''.join(c for c in phone if c.isdigit())

        if not normalized_phone:
            return

        WhatsAppContact = self.env['whatsapp.contact'].sudo()
        contact = WhatsAppContact.search([
            '|', ('partner_id', '=', self.id), ('phone_number', '=', normalized_phone)
        ], limit=1)

        contact_vals = {
            'name': self.name,
            'phone_number': normalized_phone,
            'partner_id': self.id,
            'opt_in': self.whatsapp_opt_in,
        }

        if contact:
            update_vals = {}
            if contact.name != self.name:
                update_vals['name'] = self.name
            if contact.phone_number != normalized_phone:
                update_vals['phone_number'] = normalized_phone
            if contact.partner_id != self:
                update_vals['partner_id'] = self.id
            if contact.opt_in != self.whatsapp_opt_in:
                update_vals['opt_in'] = self.whatsapp_opt_in
            if update_vals:
                contact.with_context(skip_partner_sync=True).write(update_vals)
        else:
            WhatsAppContact.with_context(skip_partner_sync=True).create(contact_vals)

    def action_send_whatsapp(self):
        """Open wizard to send WhatsApp message"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
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
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id}
        }
