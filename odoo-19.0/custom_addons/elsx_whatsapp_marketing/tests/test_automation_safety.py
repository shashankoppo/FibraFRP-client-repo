from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestWhatsAppAutomationSafety(TransactionCase):

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
