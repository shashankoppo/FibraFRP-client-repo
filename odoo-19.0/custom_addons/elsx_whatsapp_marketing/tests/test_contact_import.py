import base64
import json

from odoo.tests.common import TransactionCase


class TestWhatsAppAdvancedContactImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['whatsapp.account'].create({
            'name': 'Import Account',
            'phone_number': '15550000001',
            'phone_number_id': 'import-phone-id',
            'business_account_id': 'import-business-id',
            'access_token': 'test-token',
            'default_country_code': '91',
        })

    def _wizard(self, csv_text, **values):
        return self.env['whatsapp.import.wizard'].create({
            'file': base64.b64encode(csv_text.encode('utf-8')),
            'file_name': 'contacts.csv',
            'file_type': 'csv',
            'account_id': self.account.id,
            **values,
        })

    def test_imports_flexible_headers_tags_consent_and_attributes(self):
        wizard = self._wizard(
            'Full Name;Mobile;Email Address;Labels;Consent;Language;Company;Custom: Tier\n'
            'Rohit Karday;9881934777;rohit@example.com;VIP|Dealer;Yes;en_US;Fibera;Gold\n'
        )

        wizard.action_import()

        contact = self.env['whatsapp.contact'].search([('phone_number', '=', '919881934777')])
        self.assertEqual(len(contact), 1)
        self.assertEqual(contact.email, 'rohit@example.com')
        self.assertEqual(contact.company_name, 'Fibera')
        self.assertEqual(set(contact.tag_ids.mapped('name')), {'VIP', 'Dealer'})
        self.assertEqual(set(contact.partner_id.category_id.mapped('name')), {'VIP', 'Dealer'})
        self.assertEqual(json.loads(contact.custom_attributes)['tier'], 'Gold')
        self.assertTrue(contact.opt_in)
        self.assertEqual(wizard.imported_count, 1)
        self.assertEqual(wizard.error_count, 0)
        self.assertTrue(self.env['whatsapp.consent.log'].search_count([
            ('partner_id', '=', contact.partner_id.id),
            ('source', '=', 'import'),
        ]))

    def test_fill_missing_does_not_overwrite_existing_values(self):
        partner = self.env['res.partner'].create({
            'name': 'Existing Name',
            'phone': '919881934777',
            'email': 'existing@example.com',
        })
        wizard = self._wizard(
            'Name,Phone,Email\nReplacement Name,9881934777,replacement@example.com\n'
        )

        wizard.action_import()

        self.assertEqual(partner.name, 'Existing Name')
        self.assertEqual(partner.email, 'existing@example.com')
        self.assertEqual(wizard.updated_count, 1)

    def test_fill_missing_preserves_partner_without_synced_contact(self):
        partner = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create({
            'name': 'Protected Client Name',
            'phone': '919881934777',
            'email': 'protected@example.com',
        })
        wizard = self._wizard(
            'Name,Phone,Email\nImported Name,9881934777,imported@example.com\n'
        )

        wizard.action_import()

        contact = self.env['whatsapp.contact'].search([('partner_id', '=', partner.id)])
        self.assertEqual(contact.name, 'Protected Client Name')
        self.assertEqual(partner.name, 'Protected Client Name')
        self.assertEqual(partner.email, 'protected@example.com')

    def test_default_opt_out_applies_to_new_auto_synced_contact(self):
        wizard = self._wizard(
            'Name,Phone\nNo Marketing,9881934777\n',
            default_opt_in=False,
        )

        wizard.action_import()

        contact = self.env['whatsapp.contact'].search([('phone_number', '=', '919881934777')])
        self.assertFalse(contact.opt_in)
        self.assertFalse(contact.partner_id.whatsapp_opt_in)
        self.assertTrue(contact.opt_out_date)

    def test_invalid_row_does_not_block_valid_rows(self):
        wizard = self._wizard(
            'Name,Phone,Email\nBad,,not-an-email\nGood,9881934777,good@example.com\n'
        )

        wizard.action_import()

        self.assertEqual(wizard.imported_count, 1)
        self.assertEqual(wizard.error_count, 1)
        self.assertTrue(wizard.report_file)
