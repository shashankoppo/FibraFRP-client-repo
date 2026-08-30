# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models


_logger = logging.getLogger(__name__)


class WhatsAppContact(models.Model):
    _name = 'whatsapp.contact'
    _description = 'WhatsApp Contact'
    _rec_name = 'name'

    name = fields.Char('Name', default='Unknown WhatsApp Contact')
    phone_number = fields.Char(
        'Phone Number',
        index=True,
        help='Required for WhatsApp delivery. Incomplete imported contacts can be completed later.',
    )
    email = fields.Char('Email')
    company_name = fields.Char('Company')
    language_code = fields.Char('Language Code')
    external_reference = fields.Char('External Reference', index=True)
    import_source = fields.Char('Import Source')
    last_import_date = fields.Datetime('Last Imported', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Related Contact')

    # Opt-in status
    opt_in = fields.Boolean('Opted In', default=False)
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
            if not vals.get('name'):
                partner = self.env['res.partner'].sudo().browse(vals.get('partner_id')).exists()
                vals['name'] = (
                    vals.get('phone_number')
                    or vals.get('email')
                    or partner.name
                    or _('Unknown WhatsApp Contact')
                )
            if not vals.get('partner_id') and vals.get('phone_number'):
                partner = self.env['whatsapp.message']._find_partner_by_phone(vals['phone_number'])
                if partner:
                    vals['partner_id'] = partner.id

        records = super(WhatsAppContact, self).create(vals_list)
        for record in records:
            record._sync_to_partner()
        return records

    def write(self, vals):
        if 'name' in vals and not vals['name']:
            vals = dict(vals)
            vals.pop('name')
        res = super(WhatsAppContact, self).write(vals)
        fields_to_check = ['opt_in', 'partner_id', 'phone_number', 'name', 'email', 'tag_ids']
        if any(f in vals for f in fields_to_check):
            for record in self:
                record._sync_to_partner()
        return res

    def _sync_to_partner(self):
        self.ensure_one()
        if self.env.context.get('skip_partner_sync'):
            return

        if not self.partner_id:
            partner = False
            if self.phone_number:
                partner = self.env['whatsapp.message']._find_partner_by_phone(self.phone_number)
            if not partner and self.email:
                partner = self.env['res.partner'].sudo().search([
                    ('email', '=ilike', self.email.strip()),
                ], limit=1)
            if not partner and (self.phone_number or self.email):
                partner_values = {
                    'name': self.name or self.phone_number or self.email,
                    'email': self.email or False,
                    'whatsapp_opt_in': self.opt_in,
                }
                if self.phone_number:
                    partner_values['phone'] = self.phone_number
                    if 'mobile' in self.env['res.partner']._fields:
                        partner_values['mobile'] = self.phone_number
                partner = self.env['res.partner'].sudo().with_context(
                    skip_whatsapp_contact_sync=True,
                ).create(partner_values)
            if partner:
                self.with_context(skip_partner_sync=True).write({'partner_id': partner.id})
            else:
                return

        partner = self.partner_id.sudo()
        update_vals = {}
        if partner.whatsapp_opt_in != self.opt_in:
            update_vals['whatsapp_opt_in'] = self.opt_in
        placeholder_names = {
            self.phone_number,
            self.email,
            _('Unknown WhatsApp Contact'),
        }
        if self.name and (
            not partner.name
            or partner.name in placeholder_names
            or partner.name in {partner.phone, getattr(partner, 'mobile', False)}
        ) and partner.name != self.name:
            update_vals['name'] = self.name
        if self.phone_number:
            if not partner.phone:
                update_vals['phone'] = self.phone_number
            if 'mobile' in partner._fields and not partner.mobile:
                update_vals['mobile'] = self.phone_number
        if self.email and not partner.email:
            update_vals['email'] = self.email
        partner_categories = self.tag_ids._ensure_partner_categories()
        missing_categories = partner_categories - partner.category_id
        if missing_categories:
            update_vals['category_id'] = [(4, category_id) for category_id in missing_categories.ids]

        if update_vals:
            partner.with_context(skip_whatsapp_contact_sync=True).write(update_vals)

    def _reconcile_partner_links(self):
        contacts = self.sudo() if self else self.sudo().search([])
        linked = 0
        failed = 0
        for contact in contacts:
            had_partner = bool(contact.partner_id)
            try:
                with self.env.cr.savepoint():
                    contact.with_context(skip_partner_sync=False)._sync_to_partner()
                if not had_partner and contact.partner_id:
                    linked += 1
            except Exception:
                failed += 1
                _logger.exception(
                    'WhatsApp contact reconciliation failed for contact_id=%s',
                    contact.id,
                )
        _logger.info(
            'WhatsApp contact reconciliation processed=%s newly_linked=%s failed=%s',
            len(contacts),
            linked,
            failed,
        )
        return {'processed': len(contacts), 'linked': linked, 'failed': failed}

    @api.model
    def _reconcile_all_partner_links(self):
        """Reconcile every imported contact during a module upgrade."""
        return self.sudo().search([])._reconcile_partner_links()


class WhatsAppContactTag(models.Model):
    _name = 'whatsapp.contact.tag'
    _description = 'WhatsApp Contact Tag'
    _rec_name = 'name'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color', default=1)
    partner_category_id = fields.Many2one(
        'res.partner.category',
        string='Campaign Tag',
        ondelete='set null',
        readonly=True,
    )
    contact_ids = fields.Many2many('whatsapp.contact', string='Contacts')

    @api.model_create_multi
    def create(self, vals_list):
        Category = self.env['res.partner.category'].sudo()
        for vals in vals_list:
            if vals.get('partner_category_id') or not vals.get('name'):
                continue
            category = Category.search([('name', '=ilike', vals['name'])], limit=1)
            if not category:
                category = Category.create({'name': vals['name']})
            vals['partner_category_id'] = category.id
        return super().create(vals_list)

    def _ensure_partner_categories(self):
        Category = self.env['res.partner.category'].sudo()
        for tag in self.filtered(lambda record: not record.partner_category_id):
            category = Category.search([('name', '=ilike', tag.name)], limit=1)
            if not category:
                category = Category.create({'name': tag.name})
            tag.sudo().write({'partner_category_id': category.id})
        return self.mapped('partner_category_id')
