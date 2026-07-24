# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging

from odoo import api, models


_logger = logging.getLogger(__name__)

APPS_PASSWORD_HASH_PARAM = "elsx_client_restrictions.apps_password_hash"
DEFAULT_APPS_PASSWORD_HASH = (
    "ef4f50116b7e91c31b2213129dc59fed3b6c833ef35a480b95d54dc483335dba"
)

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


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _elsx_prepare_apps_gate(self):
        """Apply upgrade repairs without touching client business records."""
        params = self.sudo()
        if not params.get_param(APPS_PASSWORD_HASH_PARAM):
            params.set_param(APPS_PASSWORD_HASH_PARAM, DEFAULT_APPS_PASSWORD_HASH)

        params.search(
            [("key", "=", "elsx_client_restrictions.apps_secret_token")]
        ).unlink()

        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        erp_group = self.env.ref("base.group_erp_manager", raise_if_not_found=False)
        legacy_apps_group = self.env.ref(
            "elsx_client_restrictions.group_secret_apps_access",
            raise_if_not_found=False,
        )
        if legacy_apps_group and system_group:
            for user in legacy_apps_group.sudo().user_ids:
                if system_group not in user.group_ids:
                    user.sudo().write({"group_ids": [(4, system_group.id)]})

        settings_menu = self.env.ref(
            "base.menu_administration",
            raise_if_not_found=False,
        )
        if settings_menu:
            group_ids = [
                group.id for group in (system_group, erp_group) if group
            ]
            settings_menu.sudo().write(
                {
                    "active": True,
                    "action": False,
                    "group_ids": [(6, 0, group_ids)],
                }
            )

        ai_view = self.env.ref(
            "elsx_ai_ocr.res_config_settings_view_form",
            raise_if_not_found=False,
        )
        base_view = self.env.ref(
            "base.res_config_settings_view_form",
            raise_if_not_found=False,
        )
        if ai_view and base_view:
            arch = ai_view.arch_db or ""
            if (
                "//div[hasclass('settings')]" in arch
                or "<h2>ELSX AI Engines</h2>" in arch
            ):
                ai_view.sudo().with_context(
                    lang=None,
                    no_save_prev=True,
                ).write(
                    {
                        "inherit_id": base_view.id,
                        "arch_db": AI_OCR_SETTINGS_ARCH,
                        "arch_prev": False,
                        "arch_updated": False,
                        "active": True,
                    }
                )

        old_branding_views = self.env["ir.ui.view"].sudo()
        for xmlid in (
            "elsx_client_restrictions.elsx_web_layout_branding",
            "elsx_client_restrictions.elsx_login_layout_branding",
            "elsx_client_restrictions.elsx_brand_promotion",
            "elsx_client_restrictions.elsx_webclient_bootstrap_branding",
            "elsx_client_restrictions.elsx_webclient_offline_branding",
        ):
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if view:
                old_branding_views |= view.sudo()
        if old_branding_views:
            old_branding_views.unlink()

        generated_assets = self.env["ir.attachment"].sudo().search(
            [("url", "=like", "/web/assets/%")]
        )
        if generated_assets:
            generated_assets.unlink()
            _logger.info(
                "Cleared %s generated asset attachment(s) after admin cleanup.",
                len(generated_assets),
            )

        self.env.registry.clear_cache()
        return True

    @api.model
    def _elsx_verify_apps_password(self, password):
        expected = (
            self.sudo().get_param(APPS_PASSWORD_HASH_PARAM)
            or DEFAULT_APPS_PASSWORD_HASH
        )
        supplied = hashlib.sha256((password or "").encode("utf-8")).hexdigest()
        return hmac.compare_digest(supplied, expected)
