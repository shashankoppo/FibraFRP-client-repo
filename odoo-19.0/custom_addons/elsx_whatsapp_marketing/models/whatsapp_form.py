# -*- coding: utf-8 -*-
import json
import re
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _slugify(value):
    slug = re.sub(r'[^a-z0-9_]+', '_', (value or '').strip().lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug or 'field'


class WhatsAppForm(models.Model):
    _name = 'whatsapp.form'
    _description = 'WhatsApp Web Form'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', ondelete='set null')
    form_type = fields.Selection([
        ('lead', 'Lead Capture'),
        ('support', 'Support Request'),
        ('feedback', 'Feedback'),
        ('custom', 'Custom'),
    ], default='lead', required=True)
    public_token = fields.Char(
        default=lambda self: secrets.token_urlsafe(24),
        required=True,
        copy=False,
        index=True,
    )
    title = fields.Char(default='Tell us your requirement')
    description = fields.Text(
        default='Please share the details below. Our team will review your request and reply on WhatsApp.'
    )
    submit_label = fields.Char(default='Submit')
    success_message = fields.Text(default='Thank you. Your details were received successfully.')
    field_ids = fields.One2many('whatsapp.form.field', 'form_id', string='Fields')
    submission_ids = fields.One2many('whatsapp.form.submission', 'form_id', string='Submissions')
    submission_count = fields.Integer(compute='_compute_submission_count')
    public_url = fields.Char(compute='_compute_public_url')
    auto_create_lead = fields.Boolean(
        'Auto-create Lead After Submission',
        default=False,
        help='Keep disabled unless the form is trusted. When enabled, a CRM lead is created from mapped fields after submission.',
    )
    require_consent = fields.Boolean(
        'Require Consent Field',
        default=False,
        help='Warn admins to include a required consent checkbox before using the form in campaigns.',
    )

    _public_token_unique = models.Constraint(
        'unique(public_token)',
        'WhatsApp form public tokens must be unique.',
    )

    @api.depends('submission_ids')
    def _compute_submission_count(self):
        grouped = self.env['whatsapp.form.submission']._read_group(
            domain=[('form_id', 'in', self.ids)],
            groupby=['form_id'],
            aggregates=['__count'],
        )
        counts = {form.id: count for form, count in grouped}
        for form in self:
            form.submission_count = counts.get(form.id, 0)

    def _compute_public_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', default='')
        for form in self:
            form.public_url = form._get_public_url(base_url=base_url)

    def _get_public_url(self, base_url=False):
        self.ensure_one()
        base_url = base_url or self.env['ir.config_parameter'].sudo().get_param('web.base.url', default='')
        return '%s/whatsapp/form/%s' % ((base_url or '').rstrip('/'), self.public_token)

    def action_regenerate_token(self):
        for form in self:
            form.public_token = secrets.token_urlsafe(24)
        return True

    def action_open_public_url(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.public_url,
            'target': 'new',
        }

    def action_view_submissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Form Submissions'),
            'res_model': 'whatsapp.form.submission',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('form_id', '=', self.id)],
            'context': {'default_form_id': self.id},
        }

    def action_create_sample_fields(self):
        for form in self:
            if form.field_ids:
                continue
            field_values = [
                ('Name', 'name', 'text', True),
                ('Phone', 'phone', 'phone', True),
                ('City', 'city', 'text', False),
                ('Requirement', 'requirement', 'textarea', True),
            ]
            for index, (label, key, field_type, required) in enumerate(field_values, start=1):
                self.env['whatsapp.form.field'].create({
                    'form_id': form.id,
                    'sequence': index * 10,
                    'name': label,
                    'field_key': key,
                    'field_type': field_type,
                    'required': required,
                })
        return True

    @api.model
    def _seed_fiberafrp_production_forms(self):
        """Create reusable form templates without overwriting existing forms."""
        account = self.env['whatsapp.account'].sudo()._get_default_account()
        definitions = [
            {
                'name': 'Lead Enquiry',
                'sequence': 10,
                'form_type': 'lead',
                'title': 'Tell us about your FRP requirement',
                'description': 'Share product, quantity, city, and project details. Our sales team will reply on WhatsApp.',
                'success_message': 'Thank you. Your sales enquiry was received. Our team will contact you shortly.',
                'require_consent': True,
                'fields': [
                    ('Name', 'name', 'text', True, 'Your full name', 'name', False),
                    ('Phone', 'phone', 'phone', True, 'WhatsApp number with country code', 'phone', False),
                    ('Company', 'company', 'text', False, 'Company or project name', 'description', False),
                    ('Product Interest', 'product_interest', 'select', True, 'Select the product family', 'description', 'Manhole Cover\nGully Cover\nDrain Cover\nFRP Grating\nTank Cover\nOther'),
                    ('Quantity', 'quantity', 'number', False, 'Approximate quantity', 'description', False),
                    ('Delivery City', 'city', 'text', True, 'City / site location', 'city', False),
                    ('Project Details', 'requirement', 'textarea', True, 'Size, load rating, use case, timeline', 'description', False),
                    ('Drawing / Photo', 'attachment', 'file', False, 'Upload drawing, photo, BOQ, or requirement sheet', 'none', False),
                    ('Consent', 'consent', 'consent', True, 'I agree to be contacted on WhatsApp about this enquiry.', 'none', False),
                ],
            },
            {
                'name': 'Support Ticket',
                'sequence': 20,
                'form_type': 'support',
                'title': 'Create a WhatsApp support request',
                'description': 'Share order, invoice, issue details, and any photos so support can respond faster.',
                'success_message': 'Thank you. Your support request was received and assigned for review.',
                'require_consent': True,
                'fields': [
                    ('Name', 'name', 'text', True, 'Your full name', 'name', False),
                    ('Phone', 'phone', 'phone', True, 'WhatsApp number with country code', 'phone', False),
                    ('Order / Invoice Number', 'order_reference', 'text', False, 'Sales order, invoice, or delivery reference', 'description', False),
                    ('Issue Type', 'issue_type', 'select', True, 'Choose the closest issue type', 'description', 'Order Status\nPayment / Invoice\nProduct Issue\nDelivery Issue\nWarranty / Replacement\nOther'),
                    ('Issue Details', 'issue_details', 'textarea', True, 'Describe the issue clearly', 'description', False),
                    ('Photo / Document', 'attachment', 'file', False, 'Attach image, invoice, delivery proof, or document', 'none', False),
                    ('Site / Delivery Location', 'location', 'location', False, 'Share location if relevant', 'none', False),
                    ('Consent', 'consent', 'consent', True, 'I agree to be contacted on WhatsApp about this support request.', 'none', False),
                ],
            },
            {
                'name': 'Catalogue Request',
                'sequence': 30,
                'form_type': 'lead',
                'title': 'Request FiberaFRP catalogue',
                'description': 'Tell us which catalogue or product range you need.',
                'success_message': 'Thank you. Your catalogue request was received.',
                'require_consent': True,
                'fields': [
                    ('Name', 'name', 'text', True, 'Your full name', 'name', False),
                    ('Phone', 'phone', 'phone', True, 'WhatsApp number with country code', 'phone', False),
                    ('Company', 'company', 'text', False, 'Company or project name', 'description', False),
                    ('City', 'city', 'text', False, 'City / state', 'city', False),
                    ('Catalogue Type', 'catalogue_type', 'select', True, 'Select what you want to review', 'description', 'Full Product Catalogue\nManhole Covers\nDrainage / Gully Covers\nFRP Gratings\nCustom Project Products'),
                    ('Consent', 'consent', 'consent', True, 'I agree to be contacted on WhatsApp about this catalogue request.', 'none', False),
                ],
            },
            {
                'name': 'Quote Request',
                'sequence': 40,
                'form_type': 'lead',
                'title': 'Request a quotation',
                'description': 'Share product specs and quantity so sales can prepare pricing.',
                'success_message': 'Thank you. Your quotation request was received.',
                'require_consent': True,
                'fields': [
                    ('Name', 'name', 'text', True, 'Your full name', 'name', False),
                    ('Phone', 'phone', 'phone', True, 'WhatsApp number with country code', 'phone', False),
                    ('Product Type', 'product_type', 'select', True, 'Select product type', 'description', 'Manhole Cover\nTank Cover\nGully Cover\nDrain Cover\nFRP Grating\nCustom Product'),
                    ('Size / Load Rating', 'size_load', 'text', True, 'Example: 600x600, 10T, heavy duty', 'description', False),
                    ('Quantity', 'quantity', 'number', True, 'Approximate quantity', 'description', False),
                    ('Delivery City', 'city', 'text', True, 'City / site location', 'city', False),
                    ('Requirement Details', 'requirement', 'textarea', True, 'Timeline, project, application, special notes', 'description', False),
                    ('Drawing / BOQ', 'attachment', 'file', False, 'Upload drawing, BOQ, or reference file', 'none', False),
                    ('Consent', 'consent', 'consent', True, 'I agree to be contacted on WhatsApp about this quote request.', 'none', False),
                ],
            },
            {
                'name': 'Feedback',
                'sequence': 50,
                'form_type': 'feedback',
                'title': 'Share your feedback',
                'description': 'Tell us how your experience was and what we should improve.',
                'success_message': 'Thank you for your feedback.',
                'require_consent': False,
                'fields': [
                    ('Name', 'name', 'text', False, 'Your name', 'name', False),
                    ('Phone', 'phone', 'phone', False, 'WhatsApp number', 'phone', False),
                    ('Rating', 'rating', 'select', True, 'Rate your experience', 'description', '5 - Excellent\n4 - Good\n3 - Average\n2 - Poor\n1 - Very Poor'),
                    ('Feedback', 'feedback', 'textarea', True, 'Share comments, issue, or suggestion', 'description', False),
                    ('May We Contact You?', 'consent', 'consent', False, 'I agree to be contacted about this feedback.', 'none', False),
                ],
            },
        ]
        created = self.browse()
        Field = self.env['whatsapp.form.field'].sudo()
        for definition in definitions:
            form = self.sudo().search([('name', '=', definition['name'])], limit=1)
            if form:
                continue
            vals = {
                key: definition[key]
                for key in ('name', 'sequence', 'form_type', 'title', 'description', 'success_message', 'require_consent')
            }
            if account:
                vals['account_id'] = account.id
            form = self.sudo().create(vals)
            for index, (label, key, field_type, required, placeholder, mapping, options) in enumerate(definition['fields'], start=1):
                Field.create({
                    'form_id': form.id,
                    'sequence': index * 10,
                    'name': label,
                    'field_key': key,
                    'field_type': field_type,
                    'required': required,
                    'placeholder': placeholder,
                    'crm_mapping': mapping or 'none',
                    'options_text': options or False,
                })
            created |= form
        return created


class WhatsAppFormField(models.Model):
    _name = 'whatsapp.form.field'
    _description = 'WhatsApp Form Field'
    _order = 'form_id, sequence, id'

    form_id = fields.Many2one('whatsapp.form', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char('Label', required=True)
    field_key = fields.Char('Technical Key', required=True)
    field_type = fields.Selection([
        ('text', 'Short Text'),
        ('textarea', 'Long Text'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('number', 'Number'),
        ('select', 'Dropdown'),
        ('checkbox', 'Checkbox'),
        ('consent', 'Consent Checkbox'),
        ('date', 'Date'),
        ('file', 'File Upload'),
        ('location', 'Location'),
    ], default='text', required=True)
    required = fields.Boolean(default=False)
    placeholder = fields.Char()
    help_text = fields.Char()
    options_text = fields.Text(
        'Options',
        help='One option per line. Used only for Dropdown fields.',
    )
    crm_mapping = fields.Selection([
        ('none', 'Do Not Map'),
        ('name', 'Lead Name / Contact Name'),
        ('phone', 'Phone'),
        ('email_from', 'Email'),
        ('city', 'City'),
        ('description', 'Lead Description'),
    ], string='CRM Mapping', default='none',
        help='Optional mapping used when a user creates a lead/contact from the submission.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('field_key'):
                vals['field_key'] = _slugify(vals.get('name'))
            else:
                vals['field_key'] = _slugify(vals['field_key'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('field_key'):
            vals = dict(vals, field_key=_slugify(vals['field_key']))
        return super().write(vals)

    @api.constrains('form_id', 'field_key')
    def _check_unique_key_per_form(self):
        for field in self:
            duplicate = self.search_count([
                ('id', '!=', field.id),
                ('form_id', '=', field.form_id.id),
                ('field_key', '=', field.field_key),
            ])
            if duplicate:
                raise ValidationError(_('Field key "%s" is already used on this form.') % field.field_key)


class WhatsAppFormSubmission(models.Model):
    _name = 'whatsapp.form.submission'
    _description = 'WhatsApp Form Submission'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    form_id = fields.Many2one('whatsapp.form', required=True, ondelete='cascade')
    account_id = fields.Many2one('whatsapp.account', related='form_id.account_id', store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Contact')
    chat_id = fields.Many2one('whatsapp.chat', string='Conversation')
    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign')
    lead_id = fields.Many2one('crm.lead', string='Created Lead', readonly=True)
    source = fields.Char(default='whatsapp_form')
    customer_name = fields.Char('Name')
    phone = fields.Char()
    email = fields.Char()
    values_json = fields.Text('Submitted Values')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'whatsapp_form_submission_attachment_rel',
        'submission_id',
        'attachment_id',
        string='Uploaded Files',
        readonly=True,
    )
    display_name = fields.Char(compute='_compute_display_name', store=True)
    summary = fields.Text(compute='_compute_summary')
    state = fields.Selection([
        ('new', 'New'),
        ('reviewed', 'Reviewed'),
        ('lead_created', 'Lead Created'),
        ('ignored', 'Ignored'),
    ], default='new')

    @api.depends('customer_name', 'phone', 'form_id.name')
    def _compute_display_name(self):
        for submission in self:
            submission.display_name = '%s - %s' % (
                submission.customer_name or submission.phone or _('Anonymous'),
                submission.form_id.name or _('WhatsApp Form'),
            )

    def _compute_summary(self):
        for submission in self:
            try:
                values = json.loads(submission.values_json or '{}')
            except Exception:
                values = {}
            if not isinstance(values, dict):
                values = {}
            lines = []
            labels = {field.field_key: field.name for field in submission.form_id.field_ids}
            for key, value in values.items():
                label = labels.get(key, key)
                lines.append('%s: %s' % (label, value))
            submission.summary = '\n'.join(lines)

    @api.model_create_multi
    def create(self, vals_list):
        Message = self.env['whatsapp.message'].sudo()
        for vals in vals_list:
            values = vals.get('values_json')
            payload = {}
            if values:
                try:
                    payload = json.loads(values)
                except Exception:
                    payload = {}
            if isinstance(payload, dict):
                vals.setdefault('customer_name', payload.get('name') or payload.get('customer_name'))
                vals.setdefault('phone', payload.get('phone') or payload.get('mobile'))
                vals.setdefault('email', payload.get('email'))
            if vals.get('phone') and not vals.get('partner_id'):
                partner = Message._find_partner_by_phone(vals['phone'])
                if partner:
                    vals['partner_id'] = partner.id
        submissions = super().create(vals_list)
        auto_submissions = submissions.filtered(lambda submission: submission.form_id.auto_create_lead)
        if auto_submissions:
            auto_submissions.action_create_lead()
        return submissions

    def action_create_lead(self):
        Lead = self.env['crm.lead'].sudo()
        for submission in self:
            if submission.lead_id:
                continue
            partner = submission.partner_id
            values = submission._submitted_values()
            mapped = submission._mapped_crm_values(values)
            lead_vals = {
                'name': _('WhatsApp Form: %s') % (submission.customer_name or submission.phone or submission.form_id.name),
                'partner_id': partner.id if partner else False,
                'phone': submission.phone,
                'email_from': submission.email,
                'type': 'lead',
                'description': submission.summary,
            }
            lead_vals.update({key: value for key, value in mapped.items() if value})
            if submission.attachment_ids:
                lead_vals['description'] = '%s\n\nUploaded files: %s' % (
                    lead_vals.get('description') or '',
                    ', '.join(submission.attachment_ids.mapped('name')),
                )
            lead = Lead.create(lead_vals)
            submission.write({'lead_id': lead.id, 'state': 'lead_created'})
        return True

    def action_mark_reviewed(self):
        self.write({'state': 'reviewed'})
        return True

    def action_update_contact_from_mapping(self):
        for submission in self:
            partner = submission.partner_id
            if not partner:
                partner = self.env['res.partner'].sudo().create({
                    'name': submission.customer_name or submission.phone or _('WhatsApp Contact'),
                    'phone': submission.phone,
                    'email': submission.email,
                })
                submission.partner_id = partner.id
            values = submission._submitted_values()
            mapped = submission._mapped_crm_values(values)
            vals = {}
            if mapped.get('name'):
                vals['name'] = mapped['name']
            if mapped.get('phone'):
                vals['phone'] = mapped['phone']
            if mapped.get('email_from'):
                vals['email'] = mapped['email_from']
            if mapped.get('city'):
                vals['city'] = mapped['city']
            if vals:
                partner.write(vals)
            submission.state = 'reviewed'
        return True

    def _submitted_values(self):
        self.ensure_one()
        try:
            values = json.loads(self.values_json or '{}')
        except Exception:
            values = {}
        return values if isinstance(values, dict) else {}

    def _mapped_crm_values(self, values):
        self.ensure_one()
        mapped = {}
        description_lines = []
        for field in self.form_id.field_ids:
            target = field.crm_mapping or 'none'
            if target == 'none':
                continue
            value = values.get(field.field_key)
            if value in (None, False, ''):
                continue
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            if target == 'description':
                description_lines.append('%s: %s' % (field.name, value))
            else:
                mapped[target] = str(value)
        if description_lines:
            existing = mapped.get('description') or self.summary or ''
            mapped['description'] = '%s\n%s' % (existing, '\n'.join(description_lines)) if existing else '\n'.join(description_lines)
        return mapped
