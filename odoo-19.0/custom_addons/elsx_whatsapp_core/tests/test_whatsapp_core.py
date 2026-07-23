# -*- coding: utf-8 -*-
import hashlib
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('-at_install', 'post_install')
class TestWhatsAppCoreContracts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['whatsapp.account'].sudo().create({
            'name': 'Contract Test Account',
            'phone_number': '+15550000000',
            'phone_number_id': 'contract-test-phone-id',
            'business_account_id': 'contract-test-business-id',
            'access_token': 'test-token-never-used',
            'default_country_code': '1',
        })
        cls.partner = cls.env['res.partner'].sudo().create({
            'name': 'Preview Recipient',
            'phone': '+15551234567',
            'whatsapp_opt_in': True,
        })
        cls.template = cls.env['whatsapp.template'].sudo().create({
            'name': 'contract_preview',
            'account_id': cls.account.id,
            'status': 'approved',
            'header_type': 'text',
            'header_text': 'Order update',
            'body': 'Hello from the structured preview.',
            'footer': 'Test footer',
            'has_buttons': True,
            'button_type': 'quick_reply',
            'button_text_1': 'View order',
        })

    def test_template_preview_payload_is_structured(self):
        payload = self.template.get_preview_payload(partner_id=self.partner.id)

        self.assertEqual(payload['version'], 1)
        self.assertEqual(payload['header']['type'], 'text')
        self.assertEqual(payload['header']['text'], 'Order update')
        self.assertEqual(payload['body'], 'Hello from the structured preview.')
        self.assertEqual(payload['footer'], 'Test footer')
        self.assertEqual(payload['buttons'][0]['type'], 'quick_reply')
        self.assertIn('warnings', payload)

        unmapped = self.env['whatsapp.template'].sudo().create({
            'name': 'contract_unmapped_preview',
            'account_id': self.account.id,
            'body': 'Hello {{1}}',
        })
        before = self.env['whatsapp.template.variable'].sudo().search_count([])
        unmapped_payload = unmapped.get_preview_payload(partner_id=self.partner.id)
        self.assertEqual(
            self.env['whatsapp.template.variable'].sudo().search_count([]),
            before,
        )
        self.assertIn(
            'unmapped_variable',
            {warning['code'] for warning in unmapped_payload['warnings']},
        )

    def test_campaign_review_is_read_only(self):
        campaign = self.env['whatsapp.campaign'].sudo().create({
            'name': 'Read-only contract review',
            'account_id': self.account.id,
            'target_type': 'manual',
            'partner_ids': [(6, 0, self.partner.ids)],
            'template_id': self.template.id,
        })
        tracked_models = (
            'whatsapp.message',
            'whatsapp.contact',
            'whatsapp.template.variable',
            'res.partner',
        )
        before = {
            model_name: self.env[model_name].sudo().search_count([])
            for model_name in tracked_models
        }

        review = campaign.get_launch_review()

        self.assertEqual({
            model_name: self.env[model_name].sudo().search_count([])
            for model_name in tracked_models
        }, before)
        self.assertEqual(review['version'], 1)
        self.assertEqual(review['counts']['eligible'], 1)
        self.assertEqual(review['counts']['invalid_numbers'], 0)
        self.assertTrue(review['samples'])

    def test_runtime_pause_blocks_dispatch_contract(self):
        params = self.env['ir.config_parameter'].sudo()
        previous = params.get_param('whatsapp.runtime.enabled', default='True')
        params.set_param('whatsapp.runtime.enabled', 'False')
        try:
            with self.assertRaises(UserError):
                self.env['whatsapp.runtime.guard'].assert_enabled()
        finally:
            params.set_param('whatsapp.runtime.enabled', previous)

    def test_workspace_role_override(self):
        self.env.user.whatsapp_workspace_role = 'marketer'
        self.assertEqual(self.env.user.get_whatsapp_workspace_role(), 'marketer')

    def test_reporting_views_are_queryable(self):
        self.env.cr.execute("SELECT id FROM whatsapp_analytics LIMIT 1")
        self.env.cr.execute("SELECT id FROM whatsapp_team_performance LIMIT 1")

    def test_uninstall_authorization_expires(self):
        token = 'single-use-test-token'
        readiness = self.env['elsx.whatsapp.uninstall.readiness'].sudo().create({
            'name': 'Token expiry contract',
            'database_name': self.env.cr.dbname,
            'requested_by_id': self.env.user.id,
            'state': 'authorized',
            'authorization_token_hash': hashlib.sha256(token.encode()).hexdigest(),
            'authorization_expires_at': fields.Datetime.now() + timedelta(minutes=15),
        })
        self.assertEqual(
            self.env['elsx.whatsapp.uninstall.readiness'].validate_authorization_token(token),
            readiness,
        )

        readiness.authorization_expires_at = fields.Datetime.now() - timedelta(seconds=1)
        with self.assertRaises(UserError):
            self.env['elsx.whatsapp.uninstall.readiness'].validate_authorization_token(token)

    def test_persistent_metadata_has_core_owner(self):
        xml_id_gaps, relation_gaps = self.env[
            'elsx.whatsapp.uninstall.readiness'
        ]._ownership_gaps()
        self.assertEqual(xml_id_gaps, 0)
        self.assertEqual(relation_gaps, 0)
