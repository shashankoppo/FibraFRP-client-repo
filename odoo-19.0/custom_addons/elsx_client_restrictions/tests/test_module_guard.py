# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('-at_install', 'post_install')
class TestModuleGuard(TransactionCase):

    def test_whatsapp_shell_is_removable_but_data_modules_are_protected(self):
        protected = self.env[
            'ir.module.module'
        ]._elsx_protected_module_names()

        self.assertNotIn('elsx_whatsapp_marketing', protected)
        self.assertIn('elsx_whatsapp_core', protected)
        self.assertIn('elsx_whatsapp_gateway', protected)
