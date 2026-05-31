# -*- coding: utf-8 -*-
from odoo import models, api, fields
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
            view = self.env.ref(
                "elsx_client_restrictions.elsx_brand_promotion",
                raise_if_not_found=False,
            )
            target = self.env.ref(
                "web.brand_promotion_message",
                raise_if_not_found=False,
            )
            if not view or not target:
                return
            safe_arch = """
<data>
    <xpath expr="//t[@t-out]" position="replace">
        <span>Powered by <span>ELSxGlobal</span></span>
    </xpath>
</data>
"""
            needs_rescue = (
                view.inherit_id.id != target.id
                or "o_brand_promotion" in (view.arch_db or "")
                or "web.brand_promotion" in (view.arch_db or "")
            )
            if needs_rescue:
                view.sudo().with_context(lang=None, no_save_prev=True).write({
                    "name": "ELSxGlobal Brand Promotion Message",
                    "inherit_id": target.id,
                    "arch_db": safe_arch,
                    "arch_prev": False,
                    "arch_updated": False,
                })
                self.env.registry.clear_cache("templates")
                _logger.info("Repaired stale ELSxGlobal brand promotion view before module operation.")
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
