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

STALE_INHERITED_VIEW_XMLIDS = (
    "elsx_rebrand.brand_promotion_message_rebrand",
    "elsx_rebrand.login_footer_rebrand",
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


CE_BRAND_PROMOTION_MESSAGE_ARCH = """<t name="Brand Promotion Message">
    <t t-set="odoo_logo">
        <a target="_blank"
            t-attf-href="http://www.odoo.com?utm_source=db&amp;utm_medium=#{_utm_medium}"
            class="badge text-bg-light">
            <img alt="Odoo"
                src="/web/static/img/odoo_logo_tiny.png"
                width="62" height="20"
                style="width: auto; height: 1em; vertical-align: baseline;"/>
        </a>
    </t>
    <t t-set="final_message">Powered by %s%s</t>
    <t t-out="final_message % (odoo_logo, _message and ('- ' + _message) or '')"/>
</t>"""


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _elsx_apply_ui_rebrand(self):
        """Repair core Odoo CE templates, then apply safe inherited branding overrides."""
        sudo = self.sudo()
        sudo.set_param("web.web_app_name", BRAND_NAME)
        sudo._elsx_remove_optional_branding_cleanup_views()
        sudo._elsx_restore_ce_brand_promotion_views()
        self.env.registry.clear_cache()
        return True

    @api.model
    def _elsx_restore_ce_brand_promotion_views(self):
        view = self.env.ref("web.brand_promotion_message", raise_if_not_found=False)
        if not view:
            return
        arch = view.sudo().arch_db or ""
        if "Powered by %s%s" in arch and "final_message % (odoo_logo" in arch:
            return
        view.sudo().write({"arch_db": CE_BRAND_PROMOTION_MESSAGE_ARCH})
        _logger.info("Restored Odoo CE web.brand_promotion_message template.")

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
        stale_views = View.browse()
        for xmlid in STALE_INHERITED_VIEW_XMLIDS:
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if view:
                stale_views |= view.sudo()
        cleanup_names = [view_name for _, _, view_name, _ in OPTIONAL_CLEANUP_VIEWS]
        stale_views |= View.search([("name", "in", cleanup_names)])
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
            if view.model or view.type != "qweb":
                continue
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
