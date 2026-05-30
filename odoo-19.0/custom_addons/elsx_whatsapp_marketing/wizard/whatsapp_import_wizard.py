# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import base64
import csv
import io
import xlrd
import logging
import re
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class WhatsAppImportWizard(models.TransientModel):
    _name = 'whatsapp.import.wizard'
    _description = 'WhatsApp Contact Import Wizard'

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
    
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, default=_default_account_id)
    campaign_id = fields.Many2one('whatsapp.campaign', string='Add to Campaign')
    
    auto_format_numbers = fields.Boolean('Auto-format Phone Numbers', default=True, help="Removes spaces, dashes, and ensures country code.")
    default_country_code = fields.Char(
        'Default Country Code',
        default=_default_country_code,
        help="e.g. 91 for India",
    )

    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id and self.account_id.default_country_code:
            self.default_country_code = self.account_id.default_country_code

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Please upload a file first."))

        contacts_data = []
        file_content = base64.b64decode(self.file)

        if self.file_type == 'excel':
            try:
                import openpyxl
                file_stream = io.BytesIO(file_content)
                workbook = openpyxl.load_workbook(file_stream, data_only=True)
                sheet = workbook.active
                # openpyxl is 1-indexed, but if we iterate rows it yields tuples
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not row or len(row) < 2:
                        continue
                    name = row[0]
                    phone = row[1]
                    if phone:
                        contacts_data.append({
                            'name': str(name) if name else '',
                            'phone': str(phone),
                        })
            except Exception as e:
                _logger.warning("Failed to import with openpyxl, trying xlrd: %s", e)
                try:
                    workbook = xlrd.open_workbook(file_contents=file_content)
                    sheet = workbook.sheet_by_index(0)
                    for i in range(1, sheet.nrows):
                        name = sheet.cell_value(i, 0)
                        phone = sheet.cell_value(i, 1)
                        if isinstance(phone, float):
                            phone = str(int(phone))
                        contacts_data.append({
                            'name': str(name),
                            'phone': str(phone),
                        })
                except Exception as inner_e:
                    raise UserError(_("Could not read excel file. Please ensure it is a valid .xls or .xlsx file. Error: %s") % inner_e)
        else:
            stream = io.StringIO(file_content.decode('utf-8'))
            reader = csv.DictReader(stream)
            for row in reader:
                contacts_data.append({
                    'name': row.get('name', ''),
                    'phone': row.get('phone', ''),
                })

        created_partners = self.env['res.partner']
        normalizer = self.env['whatsapp.message']
        default_cc = ''.join(ch for ch in (self.default_country_code or '') if ch.isdigit())
        for data in contacts_data:
            phone = str(data['phone']).strip()
            if self.auto_format_numbers:
                phone = re.sub(r'\D', '', phone)
                if default_cc and len(phone) == 10 and not phone.startswith(default_cc):
                    phone = default_cc + phone

            phone = normalizer._normalize_phone(phone, account=self.account_id, strict=False)
            if not phone:
                continue
            
            # Find or create partner safely
            search_domain = [('phone', '=', phone)]
            if 'mobile' in self.env['res.partner']._fields:
                search_domain = ['|', ('mobile', '=', phone)] + search_domain
            
            partner = self.env['res.partner'].sudo().search(search_domain, limit=1)
            if not partner:
                partner_vals = {
                    'name': data['name'] or phone,
                    'phone': phone,
                }
                if 'mobile' in self.env['res.partner']._fields:
                    partner_vals['mobile'] = phone
                partner = self.env['res.partner'].sudo().create(partner_vals)
            created_partners |= partner

        if self.campaign_id:
            self.campaign_id.partner_ids = [(4, p.id) for p in created_partners]

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Successful'),
                'message': _('Successfully imported %s contacts.') % len(created_partners),
                'type': 'success',
                'sticky': False,
            }
        }
