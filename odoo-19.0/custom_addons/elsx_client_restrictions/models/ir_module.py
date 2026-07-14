# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import AccessError, UserError
import logging
import time
from odoo.http import request

_logger = logging.getLogger(__name__)


PROTECTED_MODULES = {
    'base',
    'web',
    'mail',
    'contacts',
    'crm',
    'sale',
    'account',
    'hr',
    'hr_attendance',
    'elsx_whatsapp_marketing',
    'elsx_attendance_tracking',
    'elsx_face_attendance',
    'elsx_client_restrictions',
    'elsx_tally_integration',
    'elsx_saas',
    'elsx_security',
}


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _elsx_apps_secret_session_allowed(self):
        if self.env.context.get('elsx_allow_apps_access'):
            return True
        try:
            return float(request.session.get('elsx_apps_access_until') or 0) >= time.time()
        except Exception:
            return False

    def _elsx_domain_contains_apps_filter(self, domain):
        for item in domain or []:
            if not isinstance(item, (list, tuple)):
                continue
            if len(item) >= 3 and item[0] == 'application' and item[1] in ('=', '==') and item[2] is True:
                return True
            if self._elsx_domain_contains_apps_filter(item):
                return True
        return False

    def _elsx_is_apps_request(self, domain=None):
        context = self.env.context
        return bool(
            context.get('search_default_app')
            or context.get('apps_action')
            or context.get('elsx_apps_guard')
            or self._elsx_domain_contains_apps_filter(domain)
        )

    def _elsx_check_apps_secret_read_access(self, domain=None):
        if self.env.su or self.env.context.get('install_mode') or self.env.context.get('update_module'):
            return
        if not self._elsx_is_apps_request(domain):
            return
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only system administrators can access Apps and module management.'))
        if not self._elsx_apps_secret_session_allowed():
            raise AccessError(_(
                'Apps are available only through the controlled ELSxGlobal Apps URL. '
                'Use the secret Apps shortcut as a trusted system administrator.'
            ))

    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        self._elsx_check_apps_secret_read_access(domain)
        return super().web_search_read(domain, specification, offset=offset, limit=limit, order=order, count_limit=count_limit)

    def web_read(self, specification):
        self._elsx_check_apps_secret_read_access()
        return super().web_read(specification)

    def _elsx_protected_module_names(self):
        params = self.env['ir.config_parameter'].sudo()
        configured = params.get_param('elsx.module_guard.protected_modules', default='')
        names = set(PROTECTED_MODULES)
        if configured:
            names |= {name.strip() for name in configured.replace('\n', ',').split(',') if name.strip()}
        return names

    def _elsx_protected_uninstall_candidates(self):
        candidates = self
        try:
            candidates |= self.downstream_dependencies()
        except Exception:
            _logger.exception('Could not compute downstream module dependencies for ELSx module guard.')
        return candidates.filtered(lambda module: module.name in self._elsx_protected_module_names())

    def _elsx_check_protected_uninstall(self):
        if self.env.context.get('elsx_allow_protected_module_uninstall'):
            return
        protected = self._elsx_protected_uninstall_candidates()
        if protected:
            names = ', '.join(sorted(protected.mapped('name')))
            raise UserError(_(
                "Production safety blocked this uninstall.\n\n"
                "The operation would remove protected modules: %s\n\n"
                "Create a verified encrypted backup and use a technical recovery plan before removing protected modules."
            ) % names)

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

    def button_uninstall(self):
        self._elsx_check_protected_uninstall()
        return super(IrModuleModule, self).button_uninstall()

    def button_immediate_uninstall(self):
        self._elsx_check_protected_uninstall()
        return super(IrModuleModule, self).button_immediate_uninstall()

    def module_uninstall(self):
        self._elsx_check_protected_uninstall()
        return super(IrModuleModule, self).module_uninstall()

    def update_list(self):
        """
        Compatibility hook only. Never auto-upgrade modules from this addon.
        """
        return super(IrModuleModule, self).update_list()
