"""Synthetic queue regression, not a production throughput certification."""
import json
import logging
import time
from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase
from ..models.whatsapp_account import WhatsAppAccount
from ..models.whatsapp_send_attempt import WhatsAppSendAttempt

_logger = logging.getLogger(__name__)


class TestWhatsAppQueueLoad(TransactionCase):
    def test_hundred_recipient_campaign_against_mock_meta(self):
        account = self.env['whatsapp.account'].create({
            'name': 'Synthetic Load', 'phone_number': '919999990001',
            'phone_number_id': 'load-phone', 'business_account_id': 'load-waba',
            'access_token': 'mock-only', 'status': 'connected', 'max_daily_limit': 1000,
        })
        partners = self.env['res.partner'].with_context(skip_whatsapp_contact_sync=True).create([
            {'name': 'Synthetic %s' % index, 'phone': '919999%06d' % index, 'whatsapp_opt_in': True}
            for index in range(100)
        ])
        template = self.env['whatsapp.template'].create({
            'name': 'synthetic_load', 'meta_template_name': 'synthetic_load', 'body': 'Hello',
            'account_id': account.id, 'category': 'marketing', 'status': 'approved',
        })
        campaign = self.env['whatsapp.campaign'].create({
            'name': 'Synthetic Campaign', 'account_id': account.id, 'template_id': template.id,
            'campaign_type': 'broadcast', 'target_type': 'manual', 'partner_ids': [(6, 0, partners.ids)],
            'exclude_recently_contacted': False, 'batch_size': 100,
        })
        campaign.action_send_campaign()
        before = campaign.message_ids.ids
        campaign.action_pause()
        with patch('requests.post') as stopped_send:
            campaign._cron_process_global_queue()
            stopped_send.assert_not_called()
        self.assertEqual(campaign.message_ids.ids, before)
        self.assertTrue(all(message.status in ('draft', 'queued') for message in campaign.message_ids))
        campaign.action_resume()
        accepted = []

        def accept(url, **kwargs):
            self.assertTrue(url.startswith('https://graph.facebook.com/'))
            accepted.append(kwargs['json']['to'])
            time.sleep(0.002)
            payload = {'messages': [{'id': 'wamid.synthetic.%s' % len(accepted)}]}
            return Mock(status_code=200, text=json.dumps(payload), json=lambda: payload)

        # The ledger is tested separately; keep durable test writes out of a rollback-only fixture.
        with patch('requests.post', side_effect=accept), \
             patch.object(WhatsAppAccount, '_consume_rate_limit_token', return_value=True), \
             patch.object(WhatsAppSendAttempt, '_reserve', return_value=(True, 'pending', False)), \
             patch.object(WhatsAppSendAttempt, '_finish'):
            started = time.monotonic()
            campaign._cron_process_global_queue()
            elapsed = time.monotonic() - started
            query_start = time.monotonic()
            self.env['whatsapp.chat'].search_read([('account_id', '=', account.id)], ['phone_number'], limit=20)
            inbox_query_ms = (time.monotonic() - query_start) * 1000
        self.assertEqual(len(accepted), 100)
        self.assertEqual(len(set(accepted)), 100)
        self.assertTrue(all(message.status == 'sent' for message in campaign.message_ids))
        _logger.info('[WA-MOCK-LOAD] recipients=100 duration_s=%.3f accepted_per_s=%.2f inbox_query_ms=%.2f mock_latency_ms=2 ledger=mocked',
                     elapsed, 100 / elapsed, inbox_query_ms)
