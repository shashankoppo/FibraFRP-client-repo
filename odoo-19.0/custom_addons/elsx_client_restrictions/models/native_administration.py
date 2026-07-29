# -*- coding: utf-8 -*-
import logging

from odoo import Command, api, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

AI_OCR_SETTINGS_ARCH = """
<data>
    <xpath expr="//form" position="inside">
        <app data-string="ELSX AI OCR" string="ELSX AI OCR" name="elsx_ai_ocr" groups="base.group_system">
            <block title="Vision Engine" id="elsx_ai_ocr_settings">
                <setting id="elsx_active_llm_engine_setting" help="Select the abstracted AI backend used for OCR and document extraction.">
                    <field name="elsx_active_llm_engine"/>
                </setting>
                <setting id="elsx_openai_api_key_setting" help="Optional API key for Vision extraction. Leave empty when using a non-OpenAI engine.">
                    <field name="elsx_openai_api_key" password="True"/>
                </setting>
            </block>
        </app>
    </xpath>
</data>
"""

LEGACY_PARAMETER_KEYS = (
    "elsx_client_restrictions.apps_password_hash",
    "elsx_client_restrictions.apps_secret_token",
)

LEGACY_MODELS_IN_UNLINK_ORDER = (
    "ir.model.access",
    "ir.rule",
    "ir.actions.act_window.view",
    "ir.ui.menu",
    "ir.ui.view",
    "ir.actions.act_url",
    "ir.actions.act_window",
    "res.groups",
)


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _elsx_restore_native_administration(self):
        """Restore official Odoo CE metadata without changing business data."""
        self._restore_administrator_groups()
        self._restore_settings()
        self._restore_apps()
        self._restore_users()
        self._restore_companies()
        self._repair_ai_settings_view()
        self._remove_legacy_restriction_records()
        self.sudo().search([("key", "in", LEGACY_PARAMETER_KEYS)]).unlink()
        if not self._native_administration_is_ready():
            raise UserError(
                "Native Odoo administration metadata did not pass verification."
            )

        generated_assets = self.env["ir.attachment"].sudo().search(
            [("url", "=like", "/web/assets/%")]
        )
        if generated_assets:
            generated_assets.unlink()
            _logger.info(
                "Cleared %s generated assets after native admin restoration.",
                len(generated_assets),
            )
        self.env.registry.clear_cache()
        return True

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _native_administration_is_ready(self):
        admin = self._ref("base.user_admin")
        settings_action = self._ref(
            "base_setup.action_general_configuration"
        )
        settings_menu = self._ref("base_setup.menu_config")
        users_action = self._ref("base.action_res_users")
        users_menu = self._ref("base.menu_action_res_users")
        users_form = self._ref("base.view_users_form")
        action_form = self._ref("base.action_res_users_view2")
        apps_action = self._ref("base.open_module_tree")
        apps_menu = self._ref("base.menu_module_tree")
        legacy_count = self.env["ir.model.data"].sudo().search_count([
            ("module", "=", "elsx_client_restrictions"),
            ("model", "in", LEGACY_MODELS_IN_UNLINK_ORDER),
        ])

        return bool(
            admin
            and admin.has_group("base.group_system")
            and admin.has_group("base.group_erp_manager")
            and settings_action
            and settings_action.res_model == "res.config.settings"
            and settings_menu
            and settings_menu.action == settings_action
            and users_action
            and users_action.res_model == "res.users"
            and users_menu
            and users_menu.action == users_action
            and users_form
            and action_form
            and action_form.view_id == users_form
            and apps_action
            and apps_menu
            and apps_menu.action == apps_action
            and not legacy_count
        )

    def _restore_administrator_groups(self):
        admin = self._ref("base.user_admin")
        system_group = self._ref("base.group_system")
        erp_group = self._ref("base.group_erp_manager")
        legacy_group = self._ref(
            "elsx_client_restrictions.group_secret_apps_access"
        )

        if legacy_group and system_group:
            for user in legacy_group.sudo().user_ids:
                user.sudo().write(
                    {"group_ids": [Command.link(system_group.id)]}
                )
        if admin:
            commands = [
                Command.link(group.id)
                for group in (system_group, erp_group)
                if group
            ]
            if commands:
                admin.sudo().write({"group_ids": commands})

    def _restore_settings(self):
        root = self._ref("base.menu_administration")
        menu = self._ref("base_setup.menu_config")
        action = self._ref("base_setup.action_general_configuration")
        view = self._ref("base.res_config_settings_view_form")
        system_group = self._ref("base.group_system")
        erp_group = self._ref("base.group_erp_manager")

        if view:
            view.sudo().write({"active": True})
        if action:
            action.sudo().write({
                "name": "Settings",
                "path": "settings",
                "res_model": "res.config.settings",
                "view_mode": "form",
                "context": "{'module' : 'general_settings', 'bin_size': False}",
                "domain": False,
                "target": "current",
            })
        if root:
            root.sudo().write({
                "active": True,
                "action": False,
                "group_ids": [Command.set([
                    group.id
                    for group in (system_group, erp_group)
                    if group
                ])],
            })
        if root and menu and action:
            menu.sudo().write({
                "active": True,
                "parent_id": root.id,
                "action": "ir.actions.act_window,%s" % action.id,
                "group_ids": [Command.set(
                    [system_group.id] if system_group else []
                )],
            })

    def _restore_apps(self):
        root = self._ref("base.menu_management")
        menu = self._ref("base.menu_apps")
        module_menu = self._ref("base.menu_module_tree")
        action = self._ref("base.open_module_tree")
        search_view = self._ref("base.view_module_filter")
        third_party_menu = self._ref("base.menu_third_party")
        theme_store_menu = self._ref("base.menu_theme_store")
        third_party_action = self._ref("base.action_third_party")
        theme_store_action = self._ref("base.action_theme_store")
        system_group = self._ref("base.group_system")

        if action:
            values = {
                "name": "Apps",
                "path": "apps",
                "res_model": "ir.module.module",
                "view_mode": "kanban,list,form",
                "context": "{'search_default_app':1}",
                "domain": False,
                "target": "current",
            }
            if search_view:
                values["search_view_id"] = search_view.id
            action.sudo().write(values)
        if root:
            root.sudo().write({
                "active": True,
                "action": False,
                "group_ids": [Command.set(
                    [system_group.id] if system_group else []
                )],
            })
        if root and menu:
            menu.sudo().write({
                "active": True,
                "parent_id": root.id,
                "action": False,
                "group_ids": [Command.clear()],
            })
        if menu and module_menu and action:
            module_menu.sudo().write({
                "active": True,
                "parent_id": menu.id,
                "action": "ir.actions.act_window,%s" % action.id,
                "group_ids": [Command.clear()],
            })

        if menu and third_party_menu and third_party_action:
            third_party_menu.sudo().write({
                "active": True,
                "parent_id": menu.id,
                "action": "ir.actions.act_url,%s" % third_party_action.id,
                "group_ids": [Command.clear()],
            })
        if menu and theme_store_menu and theme_store_action:
            theme_store_menu.sudo().write({
                "active": True,
                "parent_id": menu.id,
                "action": "ir.actions.act_url,%s" % theme_store_action.id,
                "group_ids": [Command.clear()],
            })

    def _restore_users(self):
        root = self._ref("base.menu_administration")
        parent = self._ref("base.menu_users")
        menu = self._ref("base.menu_action_res_users")
        action = self._ref("base.action_res_users")
        tree = self._ref("base.view_users_tree")
        form = self._ref("base.view_users_form")
        search = self._ref("base.view_users_search")
        action_tree = self._ref("base.action_res_users_view1")
        action_form = self._ref("base.action_res_users_view2")

        for view in (tree, form, search):
            if view:
                view.sudo().write({"active": True})
        if action:
            values = {
                "name": "Users",
                "res_model": "res.users",
                "path": "users",
                "view_mode": "list,kanban,form",
                "context": (
                    "{'search_default_filter_no_share': 1, "
                    "'is_action_res_users': True}"
                ),
                "domain": False,
                "target": "current",
            }
            if tree:
                values["view_id"] = tree.id
            if search:
                values["search_view_id"] = search.id
            action.sudo().write(values)
        if action_tree and action and tree:
            action_tree.sudo().write({
                "sequence": 10,
                "view_mode": "list",
                "view_id": tree.id,
                "act_window_id": action.id,
            })
        if action_form and action and form:
            action_form.sudo().write({
                "sequence": 20,
                "view_mode": "form",
                "view_id": form.id,
                "act_window_id": action.id,
            })
        if root and parent:
            parent.sudo().write({
                "active": True,
                "parent_id": root.id,
                "action": False,
                "group_ids": [Command.clear()],
            })
        if parent and menu and action:
            menu.sudo().write({
                "active": True,
                "parent_id": parent.id,
                "action": "ir.actions.act_window,%s" % action.id,
                "group_ids": [Command.clear()],
            })

    def _restore_companies(self):
        parent = self._ref("base.menu_users")
        menu = self._ref("base.menu_action_res_company_form")
        action = self._ref("base.action_res_company_form")

        if action:
            action.sudo().write({
                "name": "Companies",
                "res_model": "res.company",
                "path": "companies",
                "view_mode": "list,kanban,form",
                "domain": "[('parent_id', '=', False)]",
                "target": "current",
            })
        if parent and menu and action:
            menu.sudo().write({
                "active": True,
                "parent_id": parent.id,
                "action": "ir.actions.act_window,%s" % action.id,
                "group_ids": [Command.clear()],
            })

    def _repair_ai_settings_view(self):
        ai_view = self._ref("elsx_ai_ocr.res_config_settings_view_form")
        base_view = self._ref("base.res_config_settings_view_form")
        if not ai_view or not base_view:
            return
        arch = ai_view.arch_db or ""
        if (
            "//div[hasclass('settings')]" in arch
            or "<h2>ELSX AI Engines</h2>" in arch
        ):
            ai_view.sudo().with_context(
                lang=None,
                no_save_prev=True,
            ).write({
                "inherit_id": base_view.id,
                "arch_db": AI_OCR_SETTINGS_ARCH,
                "arch_prev": False,
                "arch_updated": False,
                "active": True,
            })

    def _remove_legacy_restriction_records(self):
        for model_name in LEGACY_MODELS_IN_UNLINK_ORDER:
            data = self.env["ir.model.data"].sudo().search([
                ("module", "=", "elsx_client_restrictions"),
                ("model", "=", model_name),
            ])
            if not data:
                continue
            records = self.env[model_name].sudo().browse(
                data.mapped("res_id")
            ).exists()
            if records:
                records.unlink()
            data.exists().unlink()
