# -*- coding: utf-8 -*-
import time

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.http import request


APPS_UNLOCK_SESSION_KEY = "elsx_apps_unlocked_until"


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _elsx_is_apps_request(self):
        """Identify calls originating from Odoo's native Apps action."""
        context = self.env.context
        return bool(
            context.get("search_default_app")
            or context.get("apps_action")
            or context.get("elsx_apps_guard")
        )

    def _elsx_check_apps_password_unlocked(self):
        if not self._elsx_is_apps_request():
            return
        if self.env.context.get("elsx_apps_password_unlocked"):
            return
        try:
            session = request.session
        except Exception:
            # CLI upgrades and registry operations do not have an HTTP session.
            return
        try:
            unlocked_until = int(session.get(APPS_UNLOCK_SESSION_KEY, 0) or 0)
        except Exception:
            unlocked_until = 0
        if unlocked_until <= int(time.time()):
            raise UserError(
                _(
                    "Apps password required. Open the Apps menu and unlock it "
                    "before managing modules."
                )
            )

    def search_read(
        self,
        domain=None,
        fields=None,
        offset=0,
        limit=None,
        order=None,
        **read_kwargs,
    ):
        self._elsx_check_apps_password_unlocked()
        return super().search_read(
            domain=domain,
            fields=fields,
            offset=offset,
            limit=limit,
            order=order,
            **read_kwargs,
        )

    @api.model
    @api.readonly
    def web_search_read(
        self,
        domain,
        specification,
        offset=0,
        limit=None,
        order=None,
        count_limit=None,
    ):
        self._elsx_check_apps_password_unlocked()
        return super().web_search_read(
            domain,
            specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )

    def button_install(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_install()

    def button_immediate_install(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_immediate_install()

    def button_upgrade(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_upgrade()

    def button_immediate_upgrade(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_immediate_upgrade()

    def button_uninstall_wizard(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_uninstall_wizard()

    def button_uninstall(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_uninstall()

    def button_immediate_uninstall(self):
        self._elsx_check_apps_password_unlocked()
        return super().button_immediate_uninstall()

    def module_uninstall(self):
        self._elsx_check_apps_password_unlocked()
        return super().module_uninstall()

    def update_list(self):
        self._elsx_check_apps_password_unlocked()
        return super().update_list()
