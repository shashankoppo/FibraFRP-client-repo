import base64
import json
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..models import whatsapp_message as message_module
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
        stale_nextcall = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        queue_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue')
        queue_cron.write({'active': False, 'nextcall': stale_nextcall})

        self.env['whatsapp.campaign']._repair_delivery_crons()

        queue_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue')
        direct_queue_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_direct_message_queue')
        retry_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_retry_failed_messages')
        webhook_cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_recover_received_webhooks')
        self.assertTrue(queue_cron.active)
        self.assertEqual(queue_cron.model_id.model, 'whatsapp.campaign')
        self.assertEqual(queue_cron.code, 'model._cron_process_global_queue()')
        self.assertGreaterEqual(queue_cron.nextcall, stale_nextcall)
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

    def test_bus_realtime_notification_does_not_open_cursor_or_thread(self):
        self.env['ir.config_parameter'].sudo().set_param('whatsapp.realtime.mode', 'bus')
        message = self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'phone_number': '919881934780',
            'direction': 'outbound',
            'status': 'queued',
            'body': 'Bus notification check',
        })

        with (
            patch.object(message_module.SIDECAR_NOTIFY_EXECUTOR, 'submit') as submit,
            patch.object(message_module.odoo.modules.registry, 'Registry') as registry,
        ):
            notified = message_module.notify_sidecar_background(self.env, message.id)

        self.assertFalse(notified)
        submit.assert_not_called()
        registry.assert_not_called()

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

    def test_running_campaign_queue_repair_releases_one_batch(self):
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Stuck Running Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Hello',
            'batch_size': 2,
            'batch_interval': 5,
            'state': 'running',
            'last_batch_at': fields.Datetime.now(),
        })
        future = fields.Datetime.add(fields.Datetime.now(), hours=1)
        messages = self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'phone_number': f'91988193478{i}',
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Queued',
                'next_retry_at': future,
            }
            for i in range(3)
        ])

        repaired = self.env['whatsapp.campaign']._repair_running_campaign_queues()

        messages.invalidate_recordset(['next_retry_at'])
        due = messages.filtered(lambda msg: msg.next_retry_at <= fields.Datetime.now())
        self.assertEqual(repaired, 2)
        self.assertEqual(len(due), 2)
        self.assertFalse(campaign.last_batch_at)

    def test_manual_process_queue_only_releases_batch(self):
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Manual Queue Kick',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Hello',
            'batch_size': 2,
            'batch_interval': 5,
            'state': 'running',
        })
        future = fields.Datetime.add(fields.Datetime.now(), hours=1)
        messages = self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'phone_number': f'91988193555{i}',
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Queued',
                'next_retry_at': future,
            }
            for i in range(3)
        ])

        with patch.object(type(self.env['whatsapp.message']), 'action_send') as action_send:
            campaign.action_process_queue()

        action_send.assert_not_called()
        messages.invalidate_recordset(['next_retry_at'])
        due = messages.filtered(lambda msg: msg.next_retry_at <= fields.Datetime.now())
        self.assertEqual(len(due), 2)

    def test_campaign_percentage_widgets_receive_ratios(self):
        partners = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create([
            {'name': 'Delivered Recipient', 'phone': '919881936001'},
            {'name': 'Sent Recipient', 'phone': '919881936002'},
        ])
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Accurate Campaign Rates',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partners.ids)],
            'message_body': 'Hello',
        })
        self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'partner_id': partners[0].id,
                'phone_number': partners[0].phone,
                'direction': 'outbound',
                'status': 'delivered',
                'body': 'Delivered',
            },
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'partner_id': partners[1].id,
                'phone_number': partners[1].phone,
                'direction': 'outbound',
                'status': 'sent',
                'body': 'Sent',
            },
        ])

        campaign.invalidate_recordset([
            'total_recipients', 'sent_count', 'delivered_count', 'delivery_rate', 'read_rate',
        ])
        self.assertEqual(campaign.sent_count, 2)
        self.assertEqual(campaign.delivered_count, 1)
        self.assertEqual(campaign.delivery_rate, 0.5)
        self.assertEqual(campaign.read_rate, 0.0)

    def test_campaign_cron_does_not_reschedule_itself_while_batch_is_paced(self):
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Paced Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Hello',
            'batch_size': 50,
            'batch_interval': 5,
            'state': 'running',
            'last_batch_at': fields.Datetime.now(),
        })
        self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'campaign_id': campaign.id,
            'phone_number': '919881936003',
            'direction': 'outbound',
            'status': 'queued',
            'body': 'Queued',
            'next_retry_at': fields.Datetime.now(),
        })

        with patch.object(type(campaign), '_schedule_next_campaign_queue_run') as schedule_next:
            self.env['whatsapp.campaign']._cron_process_global_queue()

        schedule_next.assert_not_called()

    def test_cancel_campaign_stops_pending_delivery_without_losing_history(self):
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Campaign To Cancel',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Hello',
            'state': 'running',
        })
        future = fields.Datetime.add(fields.Datetime.now(), hours=1)
        queued, failed, sent = self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'phone_number': '919881936101',
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Queued',
                'next_retry_at': future,
            },
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'phone_number': '919881936102',
                'direction': 'outbound',
                'status': 'failed',
                'body': 'Failed',
                'next_retry_at': future,
                'error_message': 'Temporary failure',
            },
            {
                'account_id': self.account.id,
                'campaign_id': campaign.id,
                'phone_number': '919881936103',
                'direction': 'outbound',
                'status': 'sent',
                'body': 'Sent',
            },
        ])

        campaign.action_cancel()

        (queued | failed | sent).invalidate_recordset(['status', 'next_retry_at'])
        self.assertEqual(campaign.state, 'cancelled')
        self.assertEqual(queued.status, 'cancelled')
        self.assertFalse(queued.next_retry_at)
        self.assertEqual(failed.status, 'failed')
        self.assertFalse(failed.next_retry_at)
        self.assertEqual(sent.status, 'sent')

    def test_campaign_with_delivery_history_cannot_be_deleted(self):
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Deletion Protected Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Hello',
        })
        message = self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'campaign_id': campaign.id,
            'phone_number': '919881936104',
            'direction': 'outbound',
            'status': 'queued',
            'body': 'Queued',
        })

        self.assertTrue(message.is_campaign_message)
        self.assertEqual(message.campaign_origin_id, campaign.id)
        with self.assertRaises(UserError):
            campaign.unlink()
        self.assertEqual(message.campaign_id, campaign)

    def test_detached_campaign_message_is_never_adopted_by_direct_queue(self):
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Detached Queue Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Hello',
        })
        message = self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'campaign_id': campaign.id,
            'phone_number': '919881936105',
            'direction': 'outbound',
            'status': 'queued',
            'body': 'Queued',
        })
        message.write({'campaign_id': False})

        with patch.object(type(message), 'action_send') as action_send:
            self.env['whatsapp.message']._cron_process_broadcast_queue()

        action_send.assert_not_called()
        with self.assertRaises(UserError):
            message.action_send()

        result = self.env['whatsapp.message']._repair_campaign_message_provenance()
        message.invalidate_recordset(['status', 'next_retry_at'])
        self.assertGreaterEqual(result['orphaned'], 1)
        self.assertEqual(message.status, 'cancelled')
        self.assertFalse(message.next_retry_at)

    def test_deleted_campaign_recovery_preserves_accepted_and_cancels_pending(self):
        partners = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create([
            {'name': 'Recovered Sent Recipient', 'phone': '919881936106'},
            {'name': 'Recovered Pending Recipient', 'phone': '919881936107'},
        ])
        reference = self.env['whatsapp.campaign'].create({
            'name': 'Reference Campaign Copy',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partners.ids)],
            'message_body': 'Recovery content',
        })
        deleted = reference.copy({'name': 'Campaign Deleted During Delivery'})
        sent, queued = self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': deleted.id,
                'partner_id': partners[0].id,
                'phone_number': partners[0].phone,
                'direction': 'outbound',
                'status': 'sent',
                'body': 'Recovery content',
            },
            {
                'account_id': self.account.id,
                'campaign_id': deleted.id,
                'partner_id': partners[1].id,
                'phone_number': partners[1].phone,
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Recovery content',
            },
        ])
        (sent | queued).write({'campaign_id': False})
        deleted.unlink()

        dry_run = self.env['whatsapp.campaign'].recover_deleted_campaign_messages(
            reference.id, apply=False,
        )
        self.assertEqual(dry_run['message_count'], 2)
        self.assertFalse(sent.campaign_id)

        result = self.env['whatsapp.campaign'].recover_deleted_campaign_messages(
            reference.id, apply=True,
        )
        recovered = self.env['whatsapp.campaign'].browse(result['recovered_campaign_id'])
        (sent | queued).invalidate_recordset(['campaign_id', 'status', 'next_retry_at'])

        self.assertEqual(recovered.state, 'cancelled')
        self.assertEqual(set(recovered.message_ids.ids), set((sent | queued).ids))
        self.assertEqual(sent.status, 'sent')
        self.assertEqual(queued.status, 'cancelled')
        self.assertFalse(queued.next_retry_at)
        self.assertFalse(reference.message_ids)

    def test_deleted_campaign_recovery_can_resume_exact_existing_queue(self):
        partners = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create([
            {'name': 'Recovered Delivered Recipient', 'phone': '919881936108'},
            {'name': 'Recovered Queued Recipient', 'phone': '919881936109'},
        ])
        reference = self.env['whatsapp.campaign'].create({
            'name': 'Reference Resume Copy',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partners.ids)],
            'message_body': 'Resume recovery content',
        })
        deleted = reference.copy({'name': 'Deleted Active Campaign'})
        delivered, queued = self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': deleted.id,
                'partner_id': partners[0].id,
                'phone_number': partners[0].phone,
                'direction': 'outbound',
                'status': 'delivered',
                'body': 'Resume recovery content',
            },
            {
                'account_id': self.account.id,
                'campaign_id': deleted.id,
                'partner_id': partners[1].id,
                'phone_number': partners[1].phone,
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Resume recovery content',
            },
        ])
        original_campaign_id = deleted.id
        (delivered | queued).write({'campaign_id': False})
        queued.write({
            'status': 'cancelled',
            'error_message': 'Delivery stopped automatically because the original campaign was deleted.',
        })
        deleted.unlink()

        mismatch = self.env['whatsapp.campaign'].recover_deleted_campaign_messages(
            reference.id,
            apply=False,
            expected_message_count=3,
            pending_action='resume',
        )
        self.assertFalse(mismatch['expected_count_matches'])
        with self.assertRaises(UserError):
            self.env['whatsapp.campaign'].recover_deleted_campaign_messages(
                reference.id,
                apply=True,
                expected_message_count=3,
                pending_action='resume',
            )

        result = self.env['whatsapp.campaign'].recover_deleted_campaign_messages(
            reference.id,
            apply=True,
            expected_message_count=2,
            pending_action='resume',
        )
        recovered = self.env['whatsapp.campaign'].browse(result['recovered_campaign_id'])
        (delivered | queued).invalidate_recordset([
            'campaign_id', 'campaign_origin_id', 'campaign_name_snapshot', 'status',
        ])

        self.assertEqual(recovered.state, 'running')
        self.assertEqual(recovered.delivered_count, 1)
        self.assertEqual(queued.status, 'queued')
        self.assertEqual(delivered.campaign_id, recovered)
        self.assertEqual(queued.campaign_id, recovered)
        self.assertEqual(delivered.campaign_origin_id, original_campaign_id)
        self.assertEqual(delivered.campaign_name_snapshot, 'Deleted Active Campaign')
        self.assertEqual(result['pending_resumed'], 1)
        self.assertEqual(result['quarantined_resumed'], 1)

    def test_duplicate_campaign_is_clean_draft_with_configuration(self):
        partner = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create({
            'name': 'Duplicate Recipient',
            'phone': '919881936111',
        })
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Completed Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partner.ids)],
            'message_body': 'Preserved content',
            'schedule_type': 'scheduled',
            'schedule_date': fields.Datetime.add(fields.Datetime.now(), hours=1),
            'state': 'cancelled',
        })
        self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'campaign_id': campaign.id,
            'partner_id': partner.id,
            'phone_number': partner.phone,
            'direction': 'outbound',
            'status': 'sent',
            'body': campaign.message_body,
        })

        duplicate = campaign.copy({'name': 'Duplicated Campaign'})

        self.assertEqual(duplicate.state, 'draft')
        self.assertEqual(duplicate.schedule_type, 'immediate')
        self.assertFalse(duplicate.schedule_date)
        self.assertEqual(duplicate.partner_ids, partner)
        self.assertEqual(duplicate.message_body, 'Preserved content')
        self.assertFalse(duplicate.message_ids)
        self.assertEqual(duplicate.preflight_state, 'not_run')

    def test_cancelled_queue_does_not_suppress_new_campaign_recipients(self):
        queued_partner, sent_partner = self.env['res.partner'].with_context(
            skip_whatsapp_contact_sync=True
        ).create([
            {'name': 'Cancelled Queue Recipient', 'phone': '919881936121'},
            {'name': 'Actually Sent Recipient', 'phone': '919881936122'},
        ])
        old_campaign = self.env['whatsapp.campaign'].create({
            'name': 'Old Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'message_body': 'Old',
            'state': 'running',
        })
        self.env['whatsapp.message'].create([
            {
                'account_id': self.account.id,
                'campaign_id': old_campaign.id,
                'partner_id': queued_partner.id,
                'phone_number': queued_partner.phone,
                'direction': 'outbound',
                'status': 'queued',
                'body': 'Never sent',
            },
            {
                'account_id': self.account.id,
                'campaign_id': old_campaign.id,
                'partner_id': sent_partner.id,
                'phone_number': sent_partner.phone,
                'direction': 'outbound',
                'status': 'sent',
                'sent_date': fields.Datetime.now(),
                'body': 'Sent',
            },
        ])
        old_campaign.action_cancel()
        new_campaign = self.env['whatsapp.campaign'].create({
            'name': 'New Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, (queued_partner | sent_partner).ids)],
            'message_body': 'New',
            'exclude_recently_contacted': True,
            'recent_contact_days': 7,
        })

        new_campaign.action_load_recipients()

        self.assertIn(queued_partner, new_campaign.partner_ids)
        self.assertNotIn(sent_partner, new_campaign.partner_ids)

    def test_campaign_with_outbound_history_cannot_be_queued_again(self):
        partner = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create({
            'name': 'Protected Recipient',
            'phone': '919881936131',
        })
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Protected Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partner.ids)],
            'message_body': 'Hello',
            'exclude_recently_contacted': False,
        })
        self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'campaign_id': campaign.id,
            'partner_id': partner.id,
            'phone_number': partner.phone,
            'direction': 'outbound',
            'status': 'cancelled',
            'body': 'Old queue row',
        })

        with self.assertRaises(UserError):
            campaign.action_send_campaign()

    def test_campaign_header_file_is_uploaded_once_for_all_recipients(self):
        partners = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create([
            {'name': 'Media Recipient One', 'phone': '919881936141'},
            {'name': 'Media Recipient Two', 'phone': '919881936142'},
            {'name': 'Media Recipient Three', 'phone': '919881936143'},
        ])
        template = self.env['whatsapp.template'].create({
            'name': 'Shared Video Header',
            'meta_template_name': 'shared_video_header',
            'account_id': self.account.id,
            'language': 'en_US',
            'language_code': 'en_US',
            'status': 'approved',
            'header_type': 'video',
            'header_media_file': base64.b64encode(b'test-video'),
            'header_media_filename': 'campaign.mp4',
            'body': 'Hello',
        })
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Shared Media Campaign',
            'account_id': self.account.id,
            'campaign_type': 'broadcast',
            'target_type': 'manual',
            'partner_ids': [(6, 0, partners.ids)],
            'template_id': template.id,
            'exclude_recently_contacted': False,
        })

        with patch.object(
            WhatsAppAccount,
            '_upload_media_to_meta',
            return_value='uploaded-video-id',
        ) as upload:
            campaign.action_send_campaign()

        upload.assert_called_once()
        messages = campaign.message_ids.filtered(lambda message: message.direction == 'outbound')
        self.assertEqual(len(messages), 3)
        self.assertTrue(all(message.media_url == 'uploaded-video-id' for message in messages))
        for message in messages:
            payload = json.loads(message.raw_data)
            header = next(component for component in payload['components'] if component['type'] == 'header')
            self.assertEqual(header['parameters'][0]['video'], {'id': 'uploaded-video-id'})
