# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _elsx_rescue_brand_promotion_view(self):
        """Repair the old branding override before installing modules.

        Older databases may still contain an inherited view that replaced the
        full ``web.brand_promotion`` wrapper. Website/website_sale need the
        original inner t-call to remain present, so installing those modules can
        fail before this addon is upgraded. Keep the visible ELSxGlobal text,
        but move the override to the child message template.
        """
        try:
            current_view = self.env.ref(
                "elsx_client_restrictions.elsx_brand_promotion",
                raise_if_not_found=False,
            )
            target = self.env.ref(
                "web.brand_promotion_message",
                raise_if_not_found=False,
            )
            parent = self.env.ref("web.brand_promotion", raise_if_not_found=False)
            if not target:
                return
            safe_arch = """
<data>
    <xpath expr="//t[@t-out]" position="replace">
        <span>Powered by <span>ELSxGlobal</span></span>
    </xpath>
</data>
"""
            views = self.env["ir.ui.view"]
            if current_view:
                views |= current_view
            if parent:
                for view in self.env["ir.ui.view"].sudo().search([("inherit_id", "=", parent.id)]):
                    xmlid = next(iter(view.get_external_id().values()), "")
                    arch = view.arch_db or ""
                    is_elsx_view = (
                        xmlid.startswith("elsx_client_restrictions.")
                        or "elsx" in (view.name or "").lower()
                        or "elsxglobal" in arch.lower()
                        or "o_brand_promotion" in arch
                    )
                    is_core_view = xmlid.startswith("web.") or xmlid.startswith("website.")
                    if is_elsx_view and not is_core_view:
                        views |= view

            repaired = 0
            for view in views:
                arch = view.arch_db or ""
                needs_rescue = (
                    view.inherit_id.id != target.id
                    or "o_brand_promotion" in arch
                    or "web.brand_promotion" in arch
                )
                if not needs_rescue:
                    continue
                view.sudo().with_context(lang=None, no_save_prev=True).write({
                    "name": "ELSxGlobal Brand Promotion Message",
                    "inherit_id": target.id,
                    "arch_db": safe_arch,
                    "arch_prev": False,
                    "arch_updated": False,
                })
                repaired += 1
            if repaired:
                self.env.registry.clear_cache()
                _logger.info(
                    "Repaired %s stale ELSxGlobal brand promotion view(s) before module operation.",
                    repaired,
                )
        except Exception:
            _logger.exception("Could not repair stale ELSxGlobal brand promotion view before module operation.")

    def button_immediate_install(self):
        """
        Compatibility hook only. Odoo handles dependency installation.
        """
        self._elsx_rescue_brand_promotion_view()
        return super(IrModuleModule, self).button_immediate_install()

    def button_immediate_upgrade(self):
        """
        Compatibility hook only. Odoo handles module upgrades.
        """
        self._elsx_rescue_brand_promotion_view()
        return super(IrModuleModule, self).button_immediate_upgrade()

    def update_list(self):
        """
        Compatibility hook only. Never auto-upgrade modules from this addon.
        """
        return super(IrModuleModule, self).update_list()
