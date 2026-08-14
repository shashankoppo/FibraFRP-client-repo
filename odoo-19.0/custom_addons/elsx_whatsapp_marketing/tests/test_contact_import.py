import base64
import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.whatsapp_account import WhatsAppAccount


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
            'status': 'connected',
        })

    def _wizard(self, csv_text, **values):
        return self.env['whatsapp.import.wizard'].create({
            'file': base64.b64encode(csv_text.encode('utf-8')),
            'file_name': 'contacts.csv',
            'file_type': 'csv',
            'account_id': self.account.id,
            **values,
        })

    def test_contact_name_is_optional_for_standard_imports(self):
        self.assertFalse(self.env['whatsapp.contact']._fields['name'].required)

    def test_contact_phone_is_optional_for_incomplete_import_rows(self):
        self.assertFalse(self.env['whatsapp.contact']._fields['phone_number'].required)
        result = self.env['whatsapp.contact'].load(
            ['name', 'phone_number', 'email'],
            [['Email Only', '', 'email-only@example.com']],
        )

        errors = [message for message in result['messages'] if message.get('type') == 'error']
        self.assertFalse(errors)
        contact = self.env['whatsapp.contact'].browse(result['ids'])
        self.assertEqual(contact.name, 'Email Only')
        self.assertFalse(contact.phone_number)
        self.assertEqual(contact.email, 'email-only@example.com')

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

    def test_standard_odoo_import_uses_phone_when_name_is_blank(self):
        result = self.env['whatsapp.contact'].load(
            ['name', 'phone_number', 'email'],
            [['', '919881934777', 'standard-import@example.com']],
        )

        errors = [message for message in result['messages'] if message.get('type') == 'error']
        self.assertFalse(errors)
        contact = self.env['whatsapp.contact'].browse(result['ids'])
        self.assertEqual(contact.name, '919881934777')

    def test_blank_name_update_preserves_existing_name(self):
        contact = self.env['whatsapp.contact'].create({
            'name': 'Keep This Name',
            'phone_number': '919881934777',
        })

        contact.write({'name': False, 'email': 'updated@example.com'})

        self.assertEqual(contact.name, 'Keep This Name')
        self.assertEqual(contact.email, 'updated@example.com')

    def test_tagged_imports_reconcile_load_and_dispatch(self):
        tag = self.env['whatsapp.contact.tag'].create({'name': 'Campaign Audience'})
        Contact = self.env['whatsapp.contact']
        contacts = Contact.create([
            {'name': 'One', 'phone_number': '919881934771', 'tag_ids': [(6, 0, tag.ids)]},
            {'name': 'One Duplicate', 'phone_number': '919881934771', 'tag_ids': [(6, 0, tag.ids)]},
            {'name': 'Two', 'phone_number': '919881934772', 'tag_ids': [(6, 0, tag.ids)]},
            {'name': 'Email Only', 'email': 'email-only@example.com', 'tag_ids': [(6, 0, tag.ids)]},
        ])
        self.assertTrue(all(contact.partner_id for contact in contacts))

        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Import Audience Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'tags',
            'tag_ids': [(6, 0, tag.partner_category_id.ids)],
            'message_body': 'Hello {{name}}',
            'exclude_recently_contacted': False,
        })
        campaign.action_load_recipients()

        self.assertEqual(campaign.audience_source_count, 4)
        self.assertEqual(campaign.audience_unique_count, 3)
        self.assertEqual(campaign.audience_duplicate_count, 1)
        self.assertEqual(campaign.audience_missing_phone_count, 1)
        self.assertEqual(len(campaign.partner_ids), 2)
        self.assertEqual(campaign.excluded_count, 2)

        def fake_send(account, _to_number, message_type='text', **kwargs):
            message = kwargs['existing_message']
            message.write({'status': 'sent', 'message_id': f'test-{message.id}'})
            return message

        with patch.object(WhatsAppAccount, 'send_message', new=fake_send):
            campaign.action_send_campaign()

        self.assertEqual(len(campaign.message_ids), 2)
        self.assertTrue(all(message.status == 'sent' for message in campaign.message_ids))

    def test_historical_unlinked_contact_is_reconciled(self):
        tag = self.env['whatsapp.contact.tag'].create({'name': 'Historical Import'})
        contact = self.env['whatsapp.contact'].with_context(skip_partner_sync=True).create({
            'name': 'Historical Contact',
            'phone_number': '919881934779',
            'email': 'historical@example.com',
            'tag_ids': [(6, 0, tag.ids)],
        })
        self.assertFalse(contact.partner_id)

        result = contact.with_context(skip_partner_sync=False)._reconcile_partner_links()

        self.assertEqual(result['linked'], 1)
        self.assertTrue(contact.partner_id)
        self.assertIn(tag.partner_category_id, contact.partner_id.category_id)

    def test_tag_audience_matches_legacy_duplicate_category_by_name(self):
        contact_tag = self.env['whatsapp.contact.tag'].create({'name': 'Legacy Audience'})
        selected_category = self.env['res.partner.category'].create({'name': 'legacy audience'})
        contact = self.env['whatsapp.contact'].create({
            'name': 'Legacy Tagged Contact',
            'phone_number': '919881934778',
            'tag_ids': [(6, 0, contact_tag.ids)],
        })
        self.assertNotEqual(contact_tag.partner_category_id, selected_category)

        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Legacy Tag Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'tags',
            'tag_ids': [(6, 0, selected_category.ids)],
            'message_body': 'Hello',
            'exclude_recently_contacted': False,
        })

        campaign.action_load_recipients()

        self.assertIn(contact.partner_id, campaign.partner_ids)
        self.assertEqual(campaign.audience_source_count, 1)

    def test_campaign_delivery_crons_are_repaired(self):
        self.env['whatsapp.campaign']._repair_delivery_crons()

        queue_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue')
        direct_queue_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_direct_message_queue')
        retry_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_retry_failed_messages')
        webhook_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_recover_received_webhooks')
        self.assertTrue(queue_cron.active)
        self.assertEqual(queue_cron.model_id.model, 'whatsapp.campaign')
        self.assertEqual(queue_cron.code, 'model._cron_process_global_queue()')
        self.assertTrue(retry_cron.active)
        self.assertEqual(retry_cron.model_id.model, 'whatsapp.message')
        self.assertTrue(direct_queue_cron.active)
        self.assertEqual(direct_queue_cron.model_id.model, 'whatsapp.message')
        self.assertEqual(direct_queue_cron.code, 'model._cron_process_broadcast_queue()')
        self.assertTrue(webhook_cron.active)
        self.assertEqual(webhook_cron.model_id.model, 'whatsapp.webhook.log')
        self.assertEqual(webhook_cron.code, 'model._cron_recover_received()')

    def test_phone_matching_does_not_merge_different_country_codes(self):
        us_partner = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create({
            'name': 'US Contact',
            'phone': ' 14155552671 ',
        })
        india_partner = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create({
            'name': 'India Contact',
            'phone': ' 914155552671 ',
        })

        matcher = self.env['whatsapp.message']
        self.assertEqual(matcher._find_partner_by_phone('14155552671'), us_partner)
        self.assertEqual(matcher._find_partner_by_phone('914155552671'), india_partner)

    def test_queued_outbound_message_does_not_notify_sidecar(self):
        with patch('odoo.addons.elsx_whatsapp_marketing.models.whatsapp_message.notify_sidecar_background') as notify:
            self.env['whatsapp.message'].create({
                'account_id': self.account.id,
                'phone_number': '919881934777',
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Queued campaign message',
            })
            notify.assert_not_called()

            sent_message = self.env['whatsapp.message'].create({
                'account_id': self.account.id,
                'phone_number': '919881934778',
                'direction': 'outbound',
                'status': 'sent',
                'body': 'Sent message',
            })
            notify.assert_called_once_with(self.env, sent_message.id)

    def test_immediate_campaign_launch_leaves_delivery_to_background_queue(self):
        partner = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create({
            'name': 'Campaign Recipient',
            'phone': '919881934779',
        })
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'No Inline Dispatch',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partner.ids)],
            'message_body': 'Hello from queue',
            'exclude_recently_contacted': False,
        })

        with patch.object(type(campaign), 'action_process_queue') as process_queue:
            campaign.action_send_campaign()

        process_queue.assert_not_called()
        self.assertEqual(campaign.state, 'running')
        queued = self.env['whatsapp.message'].search([
            ('campaign_id', '=', campaign.id),
            ('phone_number', '=', '919881934779'),
        ])
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued.status, 'queued')
