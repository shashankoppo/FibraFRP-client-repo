# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

BRAND_NAME = "ELSxGlobal"
BRAND_URL = "https://elsxglobal.com"
APP_MODULES_URL = "https://elsxglobal.com/apps/modules"
THEME_STORE_URL = "https://elsxglobal.com/apps/themes"

TEXT_REPLACEMENTS = (
    ("https://apps.odoo.com/apps/themes", THEME_STORE_URL),
    ("https://apps.odoo.com/apps/modules", APP_MODULES_URL),
    ("https://apps.odoo.com", "https://elsxglobal.com/apps"),
    ("https://www.odoo.com", BRAND_URL),
    ("https://odoo.com", BRAND_URL),
    ("http://www.odoo.com", BRAND_URL),
    ("Odoo Community Edition", "ELSxGlobal Community Edition"),
    ("Odoo Enterprise", "ELSxGlobal Enterprise"),
    ("Odoo Community", "ELSxGlobal Community"),
    ("Odoo S.A.", BRAND_NAME),
    ("Odoo SA", BRAND_NAME),
    ("Odoo Mates", "ELSxGlobal Partners"),
    ("Odoo Community Association (OCA)", "ELSxGlobal Community"),
    ("Odoo", BRAND_NAME),
)

MODULE_METADATA_FIELDS = (
    "author",
    "website",
    "summary",
    "description",
    "description_html",
    "shortdesc",
)


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _elsx_apply_ui_rebrand(self):
        """Apply visible UI branding metadata without touching business data."""
        sudo = self.sudo()
        sudo.set_param("web.web_app_name", BRAND_NAME)

        action_values = {
            "base.action_third_party": {"name": "Third-Party Apps", "url": APP_MODULES_URL},
            "base.action_theme_store": {"name": "Theme Store", "url": THEME_STORE_URL},
        }
        for xmlid, values in action_values.items():
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                action.sudo().write(values)

        modules = self.env["ir.module.module"].sudo().search([
            "|", "|", "|",
            ("author", "ilike", "Odoo"),
            ("website", "ilike", "odoo"),
            ("summary", "ilike", "Odoo"),
            ("shortdesc", "ilike", "Odoo"),
        ])
        for module in modules:
            values = {}
            for field_name in MODULE_METADATA_FIELDS:
                if field_name not in module._fields:
                    continue
                current = module[field_name] or ""
                if not isinstance(current, str):
                    continue
                branded = current
                for needle, replacement in TEXT_REPLACEMENTS:
                    branded = branded.replace(needle, replacement)
                if branded != current:
                    values[field_name] = branded
            if values:
                module.write(values)

        generated_assets = self.env["ir.attachment"].sudo().search([
            ("url", "=like", "/web/assets/%")
        ])
        if generated_assets:
            count = len(generated_assets)
            generated_assets.unlink()
            _logger.info("Cleared %s generated assets after ELSxGlobal rebrand.", count)
        self.env.registry.clear_cache()
        return True