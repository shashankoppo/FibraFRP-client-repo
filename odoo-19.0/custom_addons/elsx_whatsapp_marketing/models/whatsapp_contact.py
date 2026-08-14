# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WhatsAppContact(models.Model):
    _name = 'whatsapp.contact'
    _description = 'WhatsApp Contact'
    _rec_name = 'name'

    name = fields.Char('Name', required=True)
    phone_number = fields.Char('Phone Number', required=True)
    email = fields.Char('Email')
    partner_id = fields.Many2one('res.partner', string='Related Contact')

    # Opt-in status
    opt_in = fields.Boolean('Opted In', default=True)
    opt_in_date = fields.Datetime('Opt-in Date')
    opt_out_date = fields.Datetime('Opt-out Date')

    # Conversation status
    last_message_date = fields.Datetime('Last Message')
    last_message_direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Last Message Direction')

    # Tags and segmentation
    tag_ids = fields.Many2many('whatsapp.contact.tag', string='Tags')

    # Statistics
    message_count = fields.Integer('Total Messages', default=0)
    campaign_count = fields.Integer('Campaigns Received', default=0)
    custom_attributes = fields.Text(
        'Custom Attributes',
        default='{}',
        help='JSON object populated by bot flows and reply automation.',
    )

    active = fields.Boolean('Active', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id') and vals.get('phone_number'):
                partner = self.env['whatsapp.message']._find_partner_by_phone(vals['phone_number'])
                if partner:
                    vals['partner_id'] = partner.id

        records = super(WhatsAppContact, self).create(vals_list)
        for record in records:
            record._sync_to_partner()
        return records

    def write(self, vals):
        res = super(WhatsAppContact, self).write(vals)
        fields_to_check = ['opt_in', 'partner_id', 'phone_number', 'name', 'email']
        if any(f in vals for f in fields_to_check):
            for record in self:
                record._sync_to_partner()
        return res

    def _sync_to_partner(self):
        self.ensure_one()
        if self.env.context.get('skip_partner_sync'):
            return

        if not self.partner_id:
            if self.phone_number:
                partner = self.env['whatsapp.message']._find_partner_by_phone(self.phone_number)
                if partner:
                    self.with_context(skip_partner_sync=True).write({'partner_id': partner.id})
            return

        partner = self.partner_id.sudo()
        update_vals = {}
        if partner.whatsapp_opt_in != self.opt_in:
            update_vals['whatsapp_opt_in'] = self.opt_in
        if partner.name != self.name:
            update_vals['name'] = self.name
        if self.email and not partner.email:
            update_vals['email'] = self.email

        if update_vals:
            partner.with_context(skip_whatsapp_contact_sync=True).write(update_vals)


class WhatsAppContactTag(models.Model):
    _name = 'whatsapp.contact.tag'
    _description = 'WhatsApp Contact Tag'
    _rec_name = 'name'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color', default=1)
    contact_ids = fields.Many2many('whatsapp.contact', string='Contacts')
