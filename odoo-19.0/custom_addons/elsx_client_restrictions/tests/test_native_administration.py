# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestNativeAdministration(TransactionCase):

    def test_administrator_keeps_native_system_access(self):
        admin = self.env.ref("base.user_admin")

        self.assertTrue(admin.has_group("base.group_system"))
        self.assertTrue(admin.has_group("base.group_erp_manager"))

    def test_users_action_uses_native_odoo_form(self):
        action = self.env.ref("base.action_res_users")
        form_view = self.env.ref("base.view_users_form")
        action_form = self.env.ref("base.action_res_users_view2")

        self.assertEqual(action.res_model, "res.users")
        self.assertEqual(action_form.view_id, form_view)

    def test_settings_and_apps_use_native_actions(self):
        settings = self.env.ref("base_setup.action_general_configuration")
        apps = self.env.ref("base.open_module_tree")
        apps_menu = self.env.ref("base.menu_module_tree")

        self.assertEqual(settings.res_model, "res.config.settings")
        self.assertEqual(apps_menu.action, apps)
        self.assertFalse(
            hasattr(
                self.env["ir.module.module"],
                "_elsx_check_apps_password_unlocked",
            )
        )

    def test_legacy_safety_menu_is_removed(self):
        self.assertFalse(
            self.env.ref(
                "elsx_client_restrictions.menu_elsx_module_safety",
                raise_if_not_found=False,
            )
        )
