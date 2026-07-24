# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestAppsPasswordGate(TransactionCase):

    def test_only_native_apps_context_is_guarded(self):
        modules = self.env["ir.module.module"]

        self.assertFalse(modules._elsx_is_apps_request())
        self.assertTrue(
            modules.with_context(search_default_app=1)._elsx_is_apps_request()
        )
        self.assertTrue(
            modules.with_context(elsx_apps_guard=True)._elsx_is_apps_request()
        )

    def test_protected_module_blocklist_is_removed(self):
        modules = self.env["ir.module.module"]

        self.assertFalse(
            hasattr(modules, "_elsx_protected_module_names"),
            "Normal Odoo dependency rules must control module uninstalls.",
        )
