# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged

from odoo.addons.elsx_whatsapp_gateway.controllers.whatsapp_webhook import (
    WhatsAppWebhook,
    _whatsapp_runtime_state,
)
from odoo.addons.elsx_whatsapp_marketing.hooks import (
    DISABLED_RUNTIME_CRON_XMLIDS,
    ENABLED_RUNTIME_CRON_XMLIDS,
    _set_runtime_state,
)


@tagged('-at_install', 'post_install')
class TestWhatsAppLifecycle(TransactionCase):

    def test_runtime_switch_changes_only_parameter_and_crons(self):
        tracked_models = (
            'whatsapp.account',
            'whatsapp.contact',
            'whatsapp.chat',
            'whatsapp.message',
            'whatsapp.template',
            'whatsapp.campaign',
            'whatsapp.bot.flow',
        )
        before = {
            model: self.env[model].sudo().search_count([])
            for model in tracked_models
        }

        _set_runtime_state(self.env, False)

        self.assertFalse(self.env['whatsapp.runtime.guard'].is_enabled())
        for name in ENABLED_RUNTIME_CRON_XMLIDS + DISABLED_RUNTIME_CRON_XMLIDS:
            cron = self.env.ref(
                f'elsx_whatsapp_marketing.{name}',
                raise_if_not_found=False,
            )
            if cron:
                self.assertFalse(cron.active)

        _set_runtime_state(self.env, True)

        self.assertTrue(self.env['whatsapp.runtime.guard'].is_enabled())
        for name in ENABLED_RUNTIME_CRON_XMLIDS:
            cron = self.env.ref(
                f'elsx_whatsapp_marketing.{name}',
                raise_if_not_found=False,
            )
            if cron:
                self.assertTrue(cron.active)
        for name in DISABLED_RUNTIME_CRON_XMLIDS:
            cron = self.env.ref(
                f'elsx_whatsapp_marketing.{name}',
                raise_if_not_found=False,
            )
            if cron:
                self.assertFalse(cron.active)

        self.assertEqual({
            model: self.env[model].sudo().search_count([])
            for model in tracked_models
        }, before)

    def test_inactive_gateway_dispatch_creates_no_records(self):
        _set_runtime_state(self.env, False)
        before = self.env['whatsapp.webhook.log'].sudo().search_count([])

        WhatsAppWebhook()._dispatch_change(
            self.env,
            False,
            'messages',
            {'messages': [{'id': 'inactive-test'}]},
            '{}',
        )

        self.assertEqual(
            self.env['whatsapp.webhook.log'].sudo().search_count([]),
            before,
        )
        self.assertEqual(
            _whatsapp_runtime_state(self.env)['reason'],
            'runtime_paused',
        )
