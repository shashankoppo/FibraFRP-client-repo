from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase


class TestRateLimitAndPersonalization(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['whatsapp.account'].create({
            'name': 'Campaign Account',
            'phone_number': '15550000001',
            'phone_number_id': '123456780',
            'business_account_id': '987654320',
            'access_token': 'test-token',
        })

    def test_rate_limit_contention_does_not_abort_message_transaction(self):
        cursor_type = type(self.env.cr)
        original_execute = cursor_type.execute

        def execute_with_serialization_failure(cursor, query, params=None, log_exceptions=True):
            query_text = getattr(query, 'code', query)
            if 'WITH locked_account AS' in str(query_text):
                return original_execute(cursor, 'SELECT 1 / 0', log_exceptions=False)
            return original_execute(cursor, query, params, log_exceptions=log_exceptions)

        with patch.object(cursor_type, 'execute', execute_with_serialization_failure):
            self.assertFalse(self.account._consume_rate_limit_token())
            self.env.cr.execute('SELECT 1')
            self.assertEqual(self.env.cr.fetchone()[0], 1)

    def test_campaign_name_placeholder_uses_linked_odoo_contact(self):
        partner = self.env['res.partner'].create({'name': 'Manoj Pal'})
        campaign = self.env['whatsapp.campaign'].new({
            'name': 'Personalization Test',
            'account_id': self.account.id,
        })

        rendered = campaign._render_body_for_partner('Hi {{name}}, welcome.', partner)

        self.assertEqual(rendered, 'Hi Manoj Pal, welcome.')

    def test_new_campaign_uses_one_minute_default_pacing(self):
        campaign = self.env['whatsapp.campaign'].new({
            'name': 'Fast default pacing',
            'account_id': self.account.id,
        })

        self.assertEqual(campaign.batch_interval, 1)

    def test_campaign_queue_wake_creates_an_immediate_trigger(self):
        cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue')
        Trigger = self.env['ir.cron.trigger']
        existing_ids = Trigger.search([('cron_id', '=', cron.id)]).ids
        before = fields.Datetime.now()

        self.env['whatsapp.campaign']._wake_campaign_queue_cron()

        trigger = Trigger.search([
            ('cron_id', '=', cron.id),
            ('id', 'not in', existing_ids),
        ], order='id desc', limit=1)
        self.assertTrue(trigger)
        self.assertLessEqual(trigger.call_at, before + timedelta(seconds=5))
