# -*- coding: utf-8 -*-
import base64
import csv
import io
import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class WhatsAppImportWizard(models.TransientModel):
    _name = 'whatsapp.import.wizard'
    _description = 'WhatsApp Contact Import Wizard'

    HEADER_ALIASES = {
        'name': {'name', 'full_name', 'contact_name', 'customer_name'},
        'phone': {'phone', 'phone_number', 'mobile', 'mobile_number', 'whatsapp', 'whatsapp_number'},
        'email': {'email', 'email_address', 'mail'},
        'tags': {'tag', 'tags', 'label', 'labels'},
        'opt_in': {'opt_in', 'opted_in', 'consent', 'subscribed'},
        'language': {'language', 'language_code', 'lang'},
        'company': {'company', 'company_name', 'organization'},
        'external_reference': {'external_reference', 'reference', 'ref'},
    }

    @api.model
    def _default_account_id(self):
        return self.env['whatsapp.account']._get_default_account()

    @api.model
    def _default_country_code(self):
        account = self._default_account_id()
        return account.default_country_code if account and account.default_country_code else '91'

    file = fields.Binary('Select File', required=True)
    file_name = fields.Char('File Name')
    file_type = fields.Selection([
        ('csv', 'CSV File'),
        ('excel', 'Excel File'),
    ], string='File Format', required=True, default='excel')
    account_id = fields.Many2one(
        'whatsapp.account',
        string='WhatsApp Account',
        required=True,
        default=_default_account_id,
    )
    campaign_id = fields.Many2one('whatsapp.campaign', string='Add to Campaign')
    default_tag_ids = fields.Many2many('whatsapp.contact.tag', string='Default Tags')
    duplicate_policy = fields.Selection([
        ('update_missing', 'Fill Missing Data'),
        ('overwrite', 'Update From File'),
        ('skip', 'Skip Existing'),
    ], default='update_missing', required=True)
    create_missing_tags = fields.Boolean('Create Missing Tags', default=True)
    default_opt_in = fields.Boolean('Default Opt-in', default=False)
    auto_format_numbers = fields.Boolean(
        'Auto-format Phone Numbers',
        default=True,
        help='Removes spaces and punctuation and applies the default country code.',
    )
    default_country_code = fields.Char(
        'Default Country Code',
        default=_default_country_code,
        help='For example, 91 for India.',
    )
    preview_text = fields.Text('Preview', readonly=True)
    imported_count = fields.Integer(readonly=True)
    updated_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    report_file = fields.Binary('Import Report', readonly=True)
    report_filename = fields.Char(readonly=True)
    template_file = fields.Binary(readonly=True)
    template_filename = fields.Char(readonly=True)

    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id and self.account_id.default_country_code:
            self.default_country_code = self.account_id.default_country_code

    @api.onchange('file', 'file_name', 'file_type')
    def _onchange_file(self):
        self.preview_text = False
        self.report_file = False
        self.report_filename = False

    @api.model
    def _normalize_header(self, value):
        return re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')

    @api.model
    def _canonical_header(self, value):
        normalized = self._normalize_header(value)
        for canonical, aliases in self.HEADER_ALIASES.items():
            if normalized in aliases:
                return canonical
        return normalized

    @api.model
    def _string_value(self, value):
        if value is None:
            return ''
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @api.model
    def _parse_boolean(self, value):
        normalized = self._normalize_header(value)
        if not normalized:
            return None
        if normalized in {'1', 'true', 'yes', 'y', 'opted_in', 'subscribed'}:
            return True
        if normalized in {'0', 'false', 'no', 'n', 'opted_out', 'unsubscribed'}:
            return False
        raise ValueError(_('Opt-in must be Yes/No, True/False, 1/0, or blank.'))

    @api.model
    def _parse_tags(self, value):
        return [
            item.strip()
            for item in re.split(r'[,;|]', self._string_value(value))
            if item.strip()
        ]

    def _read_matrix(self):
        self.ensure_one()
        try:
            content = base64.b64decode(self.file or b'', validate=True)
        except Exception as exc:
            raise UserError(_('The uploaded file is not valid base64 data.')) from exc
        if not content:
            raise UserError(_('The uploaded file is empty.'))

        file_name = (self.file_name or '').lower()
        if self.file_type == 'csv' or file_name.endswith('.csv'):
            text = None
            for encoding in ('utf-8-sig', 'utf-8', 'cp1252'):
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                raise UserError(_('CSV encoding is unsupported. Save the file as UTF-8 CSV.'))
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
            except csv.Error:
                dialect = csv.excel
            return list(csv.reader(io.StringIO(text), dialect))

        try:
            import openpyxl

            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            return [list(row) for row in sheet.iter_rows(values_only=True)]
        except Exception as xlsx_error:
            try:
                import xlrd

                workbook = xlrd.open_workbook(file_contents=content)
                sheet = workbook.sheet_by_index(0)
                return [sheet.row_values(index) for index in range(sheet.nrows)]
            except Exception as xls_error:
                _logger.info('Excel import failed with openpyxl: %s', xlsx_error)
                raise UserError(
                    _('Could not read the Excel file. Save it as a valid XLSX, XLS, or UTF-8 CSV file: %s')
                    % xls_error
                ) from xls_error

    def _mapped_rows(self):
        matrix = self._read_matrix()
        if not matrix:
            raise UserError(_('The uploaded file has no rows.'))
        headers = [self._canonical_header(value) for value in matrix[0]]
        if 'phone' not in headers:
            raise UserError(
                _('A phone column is required. Supported headers include Phone, Phone Number, Mobile, and WhatsApp Number.')
            )

        rows = []
        for row_number, values in enumerate(matrix[1:], start=2):
            mapped = {}
            attributes = {}
            for index, header in enumerate(headers):
                if not header:
                    continue
                value = self._string_value(values[index] if index < len(values) else '')
                if header.startswith('custom_') or header.startswith('attribute_'):
                    key = re.sub(r'^(custom|attribute)_', '', header)
                    if key and value:
                        attributes[key] = value
                elif header in self.HEADER_ALIASES:
                    mapped[header] = value
            if any(mapped.values()) or attributes:
                mapped['_row'] = row_number
                mapped['_attributes'] = attributes
                rows.append(mapped)
        if not rows:
            raise UserError(_('The uploaded file contains no data rows.'))
        return rows

    def _normalized_phone(self, value):
        phone = self._string_value(value)
        if self.auto_format_numbers:
            phone = re.sub(r'\D', '', phone)
            country = re.sub(r'\D', '', self.default_country_code or '')
            if country and len(phone) == 10 and not phone.startswith(country):
                phone = country + phone
        return self.env['whatsapp.message']._normalize_phone(
            phone,
            account=self.account_id,
            strict=False,
        )

    def _find_contact_and_partner(self, phone, email=False):
        Contact = self.env['whatsapp.contact'].sudo()
        contact = Contact.search([('phone_number', '=', phone)], limit=1)
        partner = contact.partner_id
        if not partner:
            partner = self.env['whatsapp.message'].sudo()._find_partner_by_phone(phone)
        if not partner and email:
            partner = self.env['res.partner'].sudo().search([('email', '=ilike', email)], limit=1)
        return contact, partner

    def _partner_values(self, row, phone, partner=False):
        values = {}
        candidates = {
            'name': row.get('name') or phone,
            'phone': phone,
            'email': row.get('email'),
            'company_name': row.get('company'),
            'ref': row.get('external_reference'),
        }
        if 'mobile' in self.env['res.partner']._fields:
            candidates['mobile'] = phone
        language = row.get('language')
        if language and self.env['res.lang'].sudo().with_context(active_test=False).search_count([('code', '=', language)]):
            candidates['lang'] = language

        for field_name, value in candidates.items():
            if field_name not in self.env['res.partner']._fields or not value:
                continue
            if not partner or self.duplicate_policy == 'overwrite' or not partner[field_name]:
                values[field_name] = value
        return values

    def _get_tags(self, names):
        Tag = self.env['whatsapp.contact.tag'].sudo()
        tags = self.default_tag_ids.sudo()
        for name in names:
            tag = Tag.search([('name', '=ilike', name)], limit=1)
            if not tag and self.create_missing_tags:
                tag = Tag.create({'name': name})
            if tag:
                tags |= tag
        return tags

    def _apply_row(self, row):
        phone = self._normalized_phone(row.get('phone'))
        if not phone:
            raise ValueError(_('Phone number is empty or invalid.'))
        email = row.get('email')
        if email and ('@' not in email or email.startswith('@') or email.endswith('@')):
            raise ValueError(_('Email address is invalid.'))

        contact, partner = self._find_contact_and_partner(phone, email=email)
        existed = bool(contact or partner)
        if existed and self.duplicate_policy == 'skip':
            return 'skipped', partner, phone, _('Existing contact skipped.')

        partner_values = self._partner_values(row, phone, partner=partner)
        if partner:
            if partner_values:
                partner.write(partner_values)
        else:
            partner = self.env['res.partner'].sudo().create(partner_values)

        if not contact:
            contact = self.env['whatsapp.contact'].sudo().search([
                '|', ('partner_id', '=', partner.id), ('phone_number', '=', phone),
            ], limit=1)
        is_new_contact = not contact
        opt_in = self._parse_boolean(row.get('opt_in'))
        contact_name = row.get('name') or partner.name or phone
        if existed and self.duplicate_policy != 'overwrite' and partner.name:
            contact_name = partner.name
        contact_candidates = {
            'name': contact_name,
            'phone_number': phone,
            'email': email,
            'partner_id': partner.id,
            'company_name': row.get('company'),
            'language_code': row.get('language'),
            'external_reference': row.get('external_reference'),
            'import_source': 'bulk_import',
            'last_import_date': fields.Datetime.now(),
        }
        if is_new_contact:
            contact_candidates['opt_in'] = self.default_opt_in if opt_in is None else opt_in
            contact = self.env['whatsapp.contact'].sudo().create({
                key: value for key, value in contact_candidates.items() if value is not None
            })
        else:
            contact_values = {}
            for field_name, value in contact_candidates.items():
                if value in (None, ''):
                    continue
                if self.duplicate_policy == 'overwrite' or not contact[field_name] or field_name in ('last_import_date', 'import_source'):
                    contact_values[field_name] = value
            if opt_in is not None:
                contact_values['opt_in'] = opt_in
            elif not existed:
                contact_values['opt_in'] = self.default_opt_in
            if contact_values:
                contact.write(contact_values)

        tag_names = self._parse_tags(row.get('tags'))
        tags = self._get_tags(tag_names)
        if tags:
            contact.write({'tag_ids': [(4, tag_id) for tag_id in tags.ids]})

        attributes = dict(row.get('_attributes') or {})
        if attributes:
            try:
                current_attributes = json.loads(contact.custom_attributes or '{}')
                if not isinstance(current_attributes, dict):
                    current_attributes = {}
            except (TypeError, ValueError):
                current_attributes = {}
            current_attributes.update(attributes)
            contact.write({'custom_attributes': json.dumps(current_attributes, ensure_ascii=True, sort_keys=True)})

        effective_opt_in = contact.opt_in
        if opt_in is not None or not existed:
            now = fields.Datetime.now()
            contact.write({
                'opt_in_date': now if effective_opt_in and not contact.opt_in_date else contact.opt_in_date,
                'opt_out_date': now if not effective_opt_in else False,
            })
            self.env['whatsapp.consent.log'].sudo().create({
                'partner_id': partner.id,
                'account_id': self.account_id.id,
                'consent_type': 'all',
                'status': 'opted_in' if effective_opt_in else 'opted_out',
                'source': 'import',
                'notes': _('Imported from %s, row %s.') % (self.file_name or 'contact file', row['_row']),
            })

        return ('updated' if existed else 'created'), partner, phone, False

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_preview(self):
        self.ensure_one()
        rows = self._mapped_rows()
        lines = [_('%s data rows detected.') % len(rows)]
        for row in rows[:20]:
            phone = self._normalized_phone(row.get('phone'))
            contact, partner = self._find_contact_and_partner(phone, email=row.get('email')) if phone else (False, False)
            state = _('existing') if contact or partner else _('new')
            lines.append(
                _('Row %(row)s: %(name)s | %(phone)s | %(email)s | %(state)s') % {
                    'row': row['_row'],
                    'name': row.get('name') or '-',
                    'phone': phone or _('invalid phone'),
                    'email': row.get('email') or '-',
                    'state': state,
                }
            )
        if len(rows) > 20:
            lines.append(_('Preview limited to the first 20 rows.'))
        self.preview_text = '\n'.join(lines)
        return self._reopen()

    def action_download_template(self):
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Name', 'Phone Number', 'Email', 'Tags', 'Opt In', 'Language Code',
            'Company', 'External Reference', 'Custom: Customer Type',
        ])
        writer.writerow([
            'Example Contact', '919876543210', 'contact@example.com', 'VIP,Customer',
            'Yes', 'en_US', 'Example Company', 'CRM-1001', 'Distributor',
        ])
        self.write({
            'template_file': base64.b64encode(output.getvalue().encode('utf-8-sig')),
            'template_filename': 'whatsapp_contact_import_template.csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/{self._name}/{self.id}/template_file/'
                f'{self.template_filename}?download=true'
            ),
            'target': 'self',
        }

    def action_import(self):
        self.ensure_one()
        rows = self._mapped_rows()
        created_partners = self.env['res.partner']
        counts = {'created': 0, 'updated': 0, 'skipped': 0, 'error': 0}
        report_rows = [['Row', 'Status', 'Name', 'Phone', 'Message']]

        for row in rows:
            try:
                with self.env.cr.savepoint():
                    status, partner, phone, message = self._apply_row(row)
                    if partner:
                        created_partners |= partner
                    counts[status] += 1
                    report_rows.append([
                        row['_row'], status, row.get('name') or '', phone or '', message or '',
                    ])
            except Exception as exc:
                counts['error'] += 1
                report_rows.append([
                    row['_row'], 'error', row.get('name') or '', row.get('phone') or '', str(exc),
                ])
                _logger.warning('WhatsApp contact import row %s failed: %s', row['_row'], exc)

        if self.campaign_id and created_partners:
            self.campaign_id.write({'partner_ids': [(4, partner_id) for partner_id in created_partners.ids]})

        report = io.StringIO()
        csv.writer(report).writerows(report_rows)
        self.write({
            'imported_count': counts['created'],
            'updated_count': counts['updated'],
            'skipped_count': counts['skipped'],
            'error_count': counts['error'],
            'report_file': base64.b64encode(report.getvalue().encode('utf-8-sig')),
            'report_filename': 'whatsapp_contact_import_report.csv',
            'preview_text': _(
                'Created: %(created)s | Updated: %(updated)s | Skipped: %(skipped)s | Errors: %(errors)s'
            ) % {
                'created': counts['created'],
                'updated': counts['updated'],
                'skipped': counts['skipped'],
                'errors': counts['error'],
            },
        })
        return self._reopen()
