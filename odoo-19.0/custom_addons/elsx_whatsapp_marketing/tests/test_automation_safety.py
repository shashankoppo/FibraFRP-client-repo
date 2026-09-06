from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestWhatsAppAutomationSafety(TransactionCase):

    def _make_account(self):
        return self.env['whatsapp.account'].create({
            'name': 'Safety Test Account',
            'phone_number': '919999999999',
            'phone_number_id': 'phone-id',
            'business_account_id': 'business-id',
            'access_token': 'token',
            'status': 'connected',
            'max_daily_limit': 1000,
        })

    def test_sale_confirmation_does_not_auto_send_by_default(self):
        partner = self.env['res.partner'].create({'name': 'No Auto Sale', 'phone': '919881934781'})
        order = self.env['sale.order'].create({'partner_id': partner.id})

        with patch.object(type(order), '_send_whatsapp_confirmation') as send:
            order.action_confirm()

        send.assert_not_called()

    def test_sale_confirmation_auto_send_requires_setting(self):
        partner = self.env['res.partner'].create({'name': 'Auto Sale', 'phone': '919881934782'})
        order = self.env['sale.order'].create({'partner_id': partner.id})
        self.env['ir.config_parameter'].sudo().set_param('whatsapp.sale.confirmation.auto_send', 'True')

        with patch.object(type(order), '_send_whatsapp_confirmation') as send:
            order.action_confirm()

        send.assert_called_once()

    def test_crm_won_does_not_auto_send_by_default(self):
        lead = self.env['crm.lead'].create({
            'name': 'No Auto CRM',
            'type': 'opportunity',
            'phone': '919881934783',
        })

        with patch.object(type(lead), '_send_whatsapp_congratulation') as send:
            lead.action_set_won_rainbowman()

        send.assert_not_called()

    def test_crm_won_auto_send_requires_setting(self):
        lead = self.env['crm.lead'].create({
            'name': 'Auto CRM',
            'type': 'opportunity',
            'phone': '919881934784',
        })
        self.env['ir.config_parameter'].sudo().set_param('whatsapp.crm.won.auto_send', 'True')

        with patch.object(type(lead), '_send_whatsapp_congratulation') as send:
            lead.action_set_won_rainbowman()

        send.assert_called_once()

    def test_manual_open_chat_reply_does_not_require_marketing_opt_in(self):
        account = self._make_account()
        partner = self.env['res.partner'].create({
            'name': 'Inbound Customer',
            'phone': '919881934785',
            'whatsapp_opt_in': False,
        })
        chat = self.env['whatsapp.chat'].create({
            'account_id': account.id,
            'phone_number': '919881934785',
            'partner_id': partner.id,
        })
        self.env['whatsapp.message'].create({
            'account_id': account.id,
            'phone_number': '919881934785',
            'partner_id': partner.id,
            'chat_id_ref': chat.id,
            'message_type': 'text',
            'body': 'Hello',
            'direction': 'inbound',
            'status': 'read',
        })
        chat.flush_recordset()
        chat.invalidate_recordset()

        message = self.env['whatsapp.message'].create({
            'account_id': account.id,
            'phone_number': '919881934785',
            'partner_id': partner.id,
            'chat_id_ref': chat.id,
            'message_type': 'text',
            'body': 'Hi, how can we help?',
            'direction': 'outbound',
        })

        self.assertTrue(chat.session_open)
        self.assertTrue(message._check_compliance())

    def test_manual_open_chat_reply_still_respects_explicit_opt_out(self):
        account = self._make_account()
        partner = self.env['res.partner'].create({
            'name': 'Opted Out Customer',
            'phone': '919881934786',
            'whatsapp_opt_in': False,
        })
        chat = self.env['whatsapp.chat'].create({
            'account_id': account.id,
            'phone_number': '919881934786',
            'partner_id': partner.id,
        })
        self.env['whatsapp.message'].create({
            'account_id': account.id,
            'phone_number': '919881934786',
            'partner_id': partner.id,
            'chat_id_ref': chat.id,
            'message_type': 'text',
            'body': 'Hello',
            'direction': 'inbound',
            'status': 'read',
        })
        self.env['whatsapp.consent.log'].sudo().create({
            'partner_id': partner.id,
            'account_id': account.id,
            'consent_type': 'all',
            'status': 'opted_out',
            'consent_date': fields.Datetime.now(),
        })
        chat.flush_recordset()
        chat.invalidate_recordset()

        message = self.env['whatsapp.message'].create({
            'account_id': account.id,
            'phone_number': '919881934786',
            'partner_id': partner.id,
            'chat_id_ref': chat.id,
            'message_type': 'text',
            'body': 'Hi, how can we help?',
            'direction': 'outbound',
        })

        with self.assertRaises(ValidationError):
            message._check_compliance()
