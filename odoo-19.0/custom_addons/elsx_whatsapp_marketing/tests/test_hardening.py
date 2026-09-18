from datetime import timedelta
import hashlib
import hmac
import os
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user

from ..controllers.whatsapp_webhook import WhatsAppWebhook
from ..models.whatsapp_account import WhatsAppAccount
from ..models.whatsapp_message import WhatsAppMessage


class TestWhatsAppHardening(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['whatsapp.account'].create({
            'name': 'Hardening Account', 'phone_number': '919999990001',
            'phone_number_id': 'hardening-phone', 'business_account_id': 'hardening-waba',
            'access_token': 'test-token', 'app_secret': 'test-secret', 'status': 'connected',
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Customer', 'phone': '919999990002'})
        cls.chat = cls.env['whatsapp.chat'].create({
            'account_id': cls.account.id, 'partner_id': cls.partner.id, 'phone_number': cls.partner.phone,
        })

    def message(self, **values):
        message_values = dict({
            'account_id': self.account.id, 'partner_id': self.partner.id,
            'chat_id_ref': self.chat.id, 'phone_number': self.partner.phone,
            'direction': 'outbound', 'message_type': 'text', 'body': 'Service response',
        }, **values)
        if message_values['direction'] == 'outbound':
            message_values.setdefault('is_agent_inbox_send', True)
        return self.env['whatsapp.message'].create(message_values)

    def consent(self, status, minutes=0, category='all', account=None):
        return self.env['whatsapp.consent.log'].create({
            'account_id': (account or self.account).id, 'partner_id': self.partner.id,
            'consent_type': category, 'status': status, 'source': 'manual',
            'consent_date': fields.Datetime.now() + timedelta(minutes=minutes),
        })

    def test_delayed_replay_does_not_reopen_service_window(self):
        self.message(direction='inbound', meta_received_at=fields.Datetime.now() - timedelta(hours=25))
        self.assertFalse(self.chat.session_open)
        with self.assertRaises(ValidationError):
            self.message()._check_compliance()

    def test_legacy_inbound_without_meta_timestamp_keeps_service_reply(self):
        self.message(direction='inbound')
        self.assertTrue(self.chat.session_open)
        self.assertTrue(self.message()._check_compliance())
        self.assertFalse(self.partner.whatsapp_opt_in)

    def test_manual_inbox_template_allows_unknown_consent(self):
        template = self.env['whatsapp.template'].create({
            'name': 'marketing_test', 'account_id': self.account.id, 'category': 'marketing',
            'body': 'Promotion', 'status': 'approved',
        })
        self.assertTrue(self.message(message_type='template', template_id=template.id)._check_compliance())

    def test_unlinked_inbox_template_does_not_require_a_partner(self):
        chat = self.env['whatsapp.chat'].create({
            'account_id': self.account.id,
            'phone_number': '919999990003',
        })
        template = self.env['whatsapp.template'].create({
            'name': 'unlinked_inbox_template', 'account_id': self.account.id,
            'category': 'marketing', 'body': 'Hello', 'status': 'approved',
        })
        message = self.env['whatsapp.message'].create({
            'account_id': self.account.id,
            'chat_id_ref': chat.id,
            'phone_number': chat.phone_number,
            'message_type': 'template',
            'template_id': template.id,
            'direction': 'outbound',
            'is_agent_inbox_send': True,
        })
        self.assertTrue(message._check_compliance())

    def test_automated_template_requires_consent(self):
        template = self.env['whatsapp.template'].create({
            'name': 'automated_marketing_test', 'account_id': self.account.id, 'category': 'marketing',
            'body': 'Promotion', 'status': 'approved',
        })
        with self.assertRaises(ValidationError):
            self.message(message_type='template', template_id=template.id, is_automated=True)._check_compliance()

    def test_manual_inbox_template_respects_explicit_opt_out(self):
        self.consent('opted_out', category='marketing')
        template = self.env['whatsapp.template'].create({
            'name': 'manual_opt_out_template', 'account_id': self.account.id, 'category': 'marketing',
            'body': 'Promotion', 'status': 'approved',
        })
        with self.assertRaises(ValidationError):
            self.message(message_type='template', template_id=template.id)._check_compliance()

    def test_rate_limited_manual_reply_wakes_direct_queue(self):
        template = self.env['whatsapp.template'].create({
            'name': 'rate_limited_manual_reply', 'account_id': self.account.id,
            'category': 'marketing', 'body': 'Promotion', 'status': 'approved',
        })
        with patch.object(WhatsAppAccount, '_consume_rate_limit_token', return_value=False), \
             patch.object(WhatsAppMessage, '_schedule_direct_queue_cron') as wake_queue:
            message = self.account.send_message(
                self.partner.phone,
                partner_id=self.partner.id,
                message_type='template',
                template_record=template,
                existing_message=self.message(
                    message_type='template', template_id=template.id,
                ),
            )
        self.assertEqual(message.status, 'queued')
        wake_queue.assert_called_once()

    def test_non_inbox_send_stays_consent_gated_even_when_a_chat_exists(self):
        template = self.env['whatsapp.template'].create({
            'name': 'non_inbox_marketing_template', 'account_id': self.account.id,
            'category': 'marketing', 'body': 'Promotion', 'status': 'approved',
        })
        with patch('requests.post') as send:
            with self.assertRaises(ValidationError):
                self.account.send_message(
                    self.partner.phone,
                    partner_id=self.partner.id,
                    message_type='template',
                    template_record=template,
                )
        send.assert_not_called()

    def test_policy_can_explicitly_allow_unknown_consent(self):
        self.env['whatsapp.compliance.policy'].create({
            'name': 'Legacy permitted sends',
            'account_id': self.account.id,
            'require_opt_in': False,
        })
        template = self.env['whatsapp.template'].create({
            'name': 'legacy_permitted_template', 'account_id': self.account.id,
            'category': 'marketing', 'body': 'Promotion', 'status': 'approved',
        })

        self.assertTrue(
            self.message(message_type='template', template_id=template.id)._check_compliance()
        )

    def test_policy_does_not_override_explicit_opt_out(self):
        self.env['whatsapp.compliance.policy'].create({
            'name': 'Legacy permitted sends',
            'account_id': self.account.id,
            'require_opt_in': False,
        })
        self.consent('opted_out', category='marketing')
        template = self.env['whatsapp.template'].create({
            'name': 'legacy_opt_out_template', 'account_id': self.account.id,
            'category': 'marketing', 'body': 'Promotion', 'status': 'approved',
        })

        with self.assertRaises(ValidationError):
            self.message(message_type='template', template_id=template.id)._check_compliance()

    def test_explicit_reconsent_supersedes_old_withdrawal(self):
        self.consent('opted_out', minutes=-10)
        self.consent('opted_in', minutes=-1)
        self.assertEqual(self.env['whatsapp.consent.log']._effective_status(self.partner, self.account, 'marketing'), 'opted_in')
        self.assertFalse(self.partner.whatsapp_opt_in)
        self.assertEqual(self.env['whatsapp.consent.log'].search_count([('partner_id', '=', self.partner.id)]), 2)

    def test_equal_time_conflicting_consent_blocks(self):
        first = self.consent('opted_out')
        second = self.consent('opted_in')
        second.consent_date = first.consent_date
        self.assertEqual(self.env['whatsapp.consent.log']._effective_status(self.partner, self.account, 'marketing'), 'opted_out')

    def test_marketing_withdrawal_does_not_block_service_reply(self):
        self.message(direction='inbound')
        self.consent('opted_out', category='marketing')
        self.assertTrue(self.message()._check_compliance())

    def test_all_communications_withdrawal_blocks_replies(self):
        self.message(direction='inbound')
        self.consent('opted_out')
        with self.assertRaises(ValidationError):
            self.message()._check_compliance()

    def test_account_method_cannot_bypass_consent(self):
        template = self.env['whatsapp.template'].create({
            'name': 'promotion', 'account_id': self.account.id,
            'category': 'marketing', 'body': 'Promotion', 'status': 'approved',
        })
        with patch('requests.post') as send:
            with self.assertRaises(ValidationError):
                self.account.send_message(self.partner.phone, partner_id=self.partner.id,
                                          message_type='template', template_record=template, skip_compliance=True)
        send.assert_not_called()

    def test_consent_cannot_be_borrowed_from_another_phone(self):
        self.partner.whatsapp_opt_in = True
        with self.assertRaises(ValidationError):
            self.message(phone_number='919999990099', message_type='template')._check_compliance()

    def test_hmac_required_even_when_legacy_bypass_was_enabled(self):
        self.account.skip_webhook_hmac = True
        controller = WhatsAppWebhook()
        body = b'{"object":"whatsapp_business_account"}'
        signature = 'sha256=' + hmac.new(b'test-secret', body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {'ODOO_ENVIRONMENT': 'production'}):
            self.assertFalse(controller._verify_meta_signature(self.account, body, '')[0])
            self.assertFalse(controller._verify_meta_signature(self.account, body, signature + 'x')[0])
            self.assertTrue(controller._verify_meta_signature(self.account, body, signature)[0])

    def test_normal_internal_user_has_no_whatsapp_access(self):
        user = new_test_user(self.env, login='wa_unprivileged', groups='base.group_user')
        self.assertFalse(user.has_group('elsx_whatsapp_marketing.group_whatsapp_user'))
        with self.assertRaises(AccessError):
            self.account.with_user(user).read(['access_token'])

    def test_agent_is_limited_to_assigned_accounts_and_no_credentials(self):
        user = new_test_user(self.env, login='wa_agent', groups='elsx_whatsapp_marketing.group_whatsapp_user')
        self.env['whatsapp.team.member'].create({'account_id': self.account.id, 'user_id': user.id})
        self.assertTrue(self.chat.with_user(user).has_access('read'))
        other = self.account.copy({'phone_number_id': 'other-phone'})
        self.assertFalse(other.with_user(user).has_access('read'))
        with self.assertRaises(AccessError):
            self.account.with_user(user).read(['access_token'])

    def test_agent_cannot_forge_customer_service_window(self):
        user = new_test_user(self.env, login='wa_evidence_agent', groups='elsx_whatsapp_marketing.group_whatsapp_user')
        self.env['whatsapp.team.member'].create({'account_id': self.account.id, 'user_id': user.id})
        with self.assertRaises(AccessError):
            self.env['whatsapp.message'].with_user(user).create({
                'account_id': self.account.id, 'phone_number': self.partner.phone, 'direction': 'inbound',
            })
        inbound = self.message(direction='inbound')
        with self.assertRaises(AccessError):
            inbound.with_user(user).write({'meta_received_at': fields.Datetime.now()})

    def test_old_stop_replay_does_not_override_later_reconsent(self):
        self.consent('opted_in', minutes=-1)
        self.env['whatsapp.consent.log']._opt_out_partner(
            self.partner, self.account, consent_date=fields.Datetime.now() - timedelta(days=1))
        self.assertEqual(self.env['whatsapp.consent.log']._effective_status(self.partner, self.account, 'marketing'), 'opted_in')

    def test_same_wamid_on_two_accounts_updates_only_matching_account(self):
        other = self.account.copy({'phone_number_id': 'other-phone'})
        first = self.message(message_id='wamid.account.scoped', status='sent')
        second = self.message(account_id=other.id, chat_id_ref=False, message_id=first.message_id, status='sent')
        WhatsAppWebhook()._process_status_update_once(self.env, self.account, {'id': first.message_id, 'status': 'read'})
        self.assertEqual(first.status, 'read')
        self.assertEqual(second.status, 'sent')

    def test_message_cannot_link_another_accounts_chat(self):
        other = self.account.copy({'phone_number_id': 'other-relationship-phone'})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.message(account_id=other.id, chat_id_ref=self.chat.id)

    def test_failed_webhook_dispatch_is_not_marked_processed(self):
        log = self.env['whatsapp.webhook.log'].create({
            'account_id': self.account.id, 'event_type': 'waba_webhook',
            'raw_payload': '{"object":"whatsapp_business_account","entry":[{"changes":[{"field":"messages","value":{}}]}]}',
        })
        with patch.object(WhatsAppWebhook, '_dispatch_change', side_effect=ValueError('handler failed')):
            with self.assertRaises(ValueError):
                log._process_received_payload()
        self.assertEqual(log.status, 'received')

    def test_dispatch_evidence_prevents_duplicate_claim_and_acceptance_downgrade(self):
        message = self.message()
        evidence = self.env['whatsapp.send.attempt']
        self.assertTrue(evidence._reserve(message)[0])
        self.assertFalse(evidence._reserve(message)[0])
        evidence._finish(message, 'accepted', 'wamid.durable.accepted')
        evidence._finish(message, 'rejected', detail='late failure')
        claimed, state, wamid = evidence._reserve(message)
        self.assertFalse(claimed)
        self.assertEqual(state, 'accepted')
        self.assertEqual(wamid, 'wamid.durable.accepted')

    def test_rejected_dispatch_without_acceptance_can_be_reclaimed(self):
        message = self.message()
        evidence = self.env['whatsapp.send.attempt']
        evidence._reserve(message)
        evidence._finish(message, 'rejected')
        self.assertTrue(evidence._reserve(message)[0])

    def test_diagnostics_reports_queue_and_delivery_timing(self):
        sent_at = fields.Datetime.now() - timedelta(seconds=15)
        self.message(status='sent', sent_date=sent_at, latency_ms=120.0)
        self.message(
            status='delivered',
            sent_date=sent_at,
            delivered_date=fields.Datetime.now(),
            latency_ms=180.0,
        )

        snapshot = self.env['whatsapp.diagnostic.snapshot']._collect_snapshot()

        self.assertIn('queued_direct_messages', snapshot['queues'])
        self.assertIn('oldest_campaign_queue_age_seconds', snapshot['queues'])
        self.assertGreaterEqual(snapshot['latency']['api_accepted_last_24h'], 2)
        self.assertGreaterEqual(snapshot['latency']['queue_to_meta_p95_seconds'], 0.0)
        self.assertGreaterEqual(snapshot['latency']['meta_to_delivery_p95_seconds'], 0.0)
