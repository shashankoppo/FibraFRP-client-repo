# -*- coding: utf-8 -*-
import logging
import re

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

POWERED_BY_REPLACEMENTS = (
    ("Powered by ELSxGlobal", ""),
    ("Powered by Odoo", ""),
    ("Website made with Odoo", ""),
    ("Website made with ELSxGlobal", ""),
    ("Create a free website", ""),
    ("Never heard of Odoo? It\u2019s an all-in-one business software loved by 12+ million users. It will considerably improve your experience at work and increase your productivity.", ""),
    ("Have a look at the Odoo Tour to discover the tool.", ""),
    ("Enjoy Odoo!", ""),
    ("Welcome to Odoo", "Welcome"),
    ("connect to Odoo", "connect"),
    ("connect on Odoo", "connect"),
    ("Your Odoo domain is:", "Your domain is:"),
)

MODULE_METADATA_FIELDS = (
    "author",
    "website",
    "summary",
    "description",
    "description_html",
    "shortdesc",
)

SYSTEM_VIEW_XMLIDS = (
    ("web", "brand_promotion_message"),
    ("web", "brand_promotion"),
    ("portal", "portal_record_sidebar"),
    ("website", "brand_promotion"),
    ("website", "layout"),
    ("website", "website_info"),
    ("website", "show_website_info"),
)

SYSTEM_TEMPLATE_MODULES = ("auth_signup", "portal", "web", "website", "mail", "digest", "mass_mailing", "mass_mailing_sale", "website_profile", "lunch")

SYSTEM_VIEW_CLEANUP_MODULES = (
    "web",
    "website",
    "portal",
    "sale",
    "mail",
    "digest",
    "mass_mailing",
    "mass_mailing_sale",
    "website_profile",
    "lunch",
    "payment",
    "point_of_sale",
)

OPTIONAL_CLEANUP_VIEWS = (
    (
        "portal",
        "portal_record_sidebar",
        "ELSxGlobal Portal Powered Branding Cleanup",
        """<data>
            <xpath expr="//div[hasclass('text-muted') and .//a[contains(@href, 'odoo.com')]]" position="replace">
                <t/>
            </xpath>
        </data>""",
    ),
    (
        "sale",
        "sale_order_portal_content",
        "ELSxGlobal Sale Portal Software Branding Cleanup",
        """<data>
            <xpath expr="//button[@id='portal_connect_software_modal_btn']/.." position="replace">
                <t/>
            </xpath>
            <xpath expr="//div[@id='sale_portal_connect_software_modal']" position="replace">
                <t/>
            </xpath>
        </data>""",
    ),
)


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _elsx_apply_ui_rebrand(self):
        """Apply visible UI branding metadata without touching business data."""
        sudo = self.sudo()
        sudo.set_param("web.web_app_name", BRAND_NAME)
        self._elsx_remove_optional_branding_cleanup_views()
        self._elsx_cleanup_visible_branding_views()
        self._elsx_cleanup_system_branding_views()
        self._elsx_cleanup_visible_branding_email_templates()

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
                branded = self._elsx_clean_text(current)
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

    @api.model
    def _elsx_clean_text(self, value):
        if not isinstance(value, str) or not value:
            return value
        cleaned = value
        cleaned = re.sub(r"Powered by\s*<a\b[^>]*>.*?</a>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<div[^>]*class=['\"][^'\"]*text-muted[^'\"]*['\"][^>]*>\s*Powered by\s*<a\b[^>]*>.*?</a>\s*</div>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<a\b[^>]*odoo\.com[^>]*>Powered by\s*<span>.*?</span></a>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<t\s+t-out=['\"]final_message[^'\"]*['\"]\s*/>", "<t/>", cleaned, flags=re.IGNORECASE | re.DOTALL)
        for needle, replacement in POWERED_BY_REPLACEMENTS + TEXT_REPLACEMENTS:
            cleaned = cleaned.replace(needle, replacement)
        cleaned = cleaned.replace('<t t-set="final_message">Powered by %s%s</t>', '<t t-set="final_message"></t>')
        return cleaned

    @api.model
    def _elsx_remove_optional_branding_cleanup_views(self):
        """Remove older fragile inherited cleanup views before direct arch cleanup."""
        View = self.env["ir.ui.view"].sudo()
        cleanup_names = [view_name for _, _, view_name, _ in OPTIONAL_CLEANUP_VIEWS]
        stale_views = View.search([("name", "in", cleanup_names)])
        if stale_views:
            stale_views.unlink()

    @api.model
    def _elsx_cleanup_visible_branding_views(self):
        """Neutralize installed platform promo views while leaving customer content alone."""
        View = self.env["ir.ui.view"].sudo()
        Data = self.env["ir.model.data"].sudo()
        for module, name in SYSTEM_VIEW_XMLIDS:
            view_data = Data.search([
                ("module", "=", module),
                ("name", "=", name),
                ("model", "=", "ir.ui.view"),
            ], limit=1)
            if not view_data:
                continue
            view = View.browse(view_data.res_id).exists()
            if not view:
                continue
            arch = view.arch_db or ""
            if not isinstance(arch, str):
                continue
            cleaned = self._elsx_clean_text(arch)
            cleaned = cleaned.replace('<meta name="generator" content="Odoo"/>', "")
            cleaned = cleaned.replace('<meta name="generator" content="ELSxGlobal"/>', "")
            if cleaned != arch:
                view.write({"arch_db": cleaned})

    @api.model
    def _elsx_cleanup_system_branding_views(self):
        """Clean visible platform branding from installed system QWeb views."""
        View = self.env["ir.ui.view"].sudo()
        Data = self.env["ir.model.data"].sudo()
        view_ids = Data.search([
            ("model", "=", "ir.ui.view"),
            ("module", "in", SYSTEM_VIEW_CLEANUP_MODULES),
        ]).mapped("res_id")
        if not view_ids:
            return
        for view in View.browse(view_ids).exists():
            arch = view.arch_db or ""
            if not isinstance(arch, str):
                continue
            if not any(token in arch for token in ("Odoo", "odoo.com", "Powered by", "Website made with")):
                continue
            cleaned = self._elsx_clean_text(arch)
            cleaned = cleaned.replace('<meta name="generator" content="Odoo"/>', "")
            cleaned = cleaned.replace('<meta name="generator" content="ELSxGlobal"/>', "")
            if cleaned != arch:
                view.write({"arch_db": cleaned})

    @api.model
    def _elsx_cleanup_visible_branding_email_templates(self):
        """Remove platform promo wording from system email templates only."""
        if "mail.template" not in getattr(self.env.registry, "models", {}):
            return
        Template = self.env["mail.template"].sudo()
        Data = self.env["ir.model.data"].sudo()
        template_ids = Data.search([
            ("model", "=", "mail.template"),
            ("module", "in", SYSTEM_TEMPLATE_MODULES),
        ]).mapped("res_id")
        if not template_ids:
            return
        for template in Template.browse(template_ids).exists():
            values = {}
            for field_name in ("subject", "body_html", "description"):
                if field_name not in template._fields:
                    continue
                current = template[field_name] or ""
                cleaned = self._elsx_clean_text(current)
                if cleaned != current:
                    values[field_name] = cleaned
            if values:
                template.write(values)
