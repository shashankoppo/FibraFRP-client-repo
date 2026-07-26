# -*- coding: utf-8 -*-
import hashlib
import hmac
import time

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.http import request


APPS_PASSWORD_HASH_PARAM = "elsx_client_restrictions.apps_password_hash"
DEFAULT_APPS_PASSWORD_HASH = "pbkdf2_sha256$260000$a0c734c93313ca2e78c53f7e96005d6f$6300917cfaa1b7d5b3c4745057072fd9c4e4b8ee3943c7f18dd513e8ee239926"
APPS_UNLOCK_SESSION_KEY = "elsx_apps_unlocked_until"
APPS_UNLOCK_URL = "/elsx/apps/unlock"


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _elsx_setup_apps_lock(self):
        """Enable the lightweight Apps password lock without touching data."""
        self.sudo().set_param(APPS_PASSWORD_HASH_PARAM, DEFAULT_APPS_PASSWORD_HASH)

        action = self.env["ir.actions.act_url"].sudo().search(
            [("url", "=", APPS_UNLOCK_URL)], limit=1
        )
        values = {
            "name": "Unlock Apps",
            "url": APPS_UNLOCK_URL,
            "target": "self",
        }
        if action:
            action.write(values)
        else:
            action = self.env["ir.actions.act_url"].sudo().create(values)

        apps_menu = self.env.ref("base.menu_module_tree", raise_if_not_found=False)
        if apps_menu:
            apps_menu.sudo().write({
                "active": True,
                "action": "ir.actions.act_url,%s" % action.id,
            })
        return True

    @api.model
    def _elsx_apps_password_matches(self, password):
        password_hash = self.sudo().get_param(APPS_PASSWORD_HASH_PARAM)
        return self._elsx_verify_password_hash(password_hash, password or "")

    @api.model
    def _elsx_verify_password_hash(self, password_hash, password):
        try:
            scheme, iterations, salt, expected = (password_hash or "").split("$", 3)
            iterations = int(iterations)
        except (AttributeError, TypeError, ValueError):
            return False
        if scheme != "pbkdf2_sha256" or iterations < 100000 or not salt or not expected:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(actual, expected)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    @api.model
    def _elsx_has_http_request(self):
        try:
            request.httprequest
        except RuntimeError:
            return False
        return True

    @api.model
    def _elsx_is_apps_read_request(self):
        if not self._elsx_has_http_request():
            return False
        context = self.env.context or {}
        if context.get("search_default_app") or context.get("search_default_extra"):
            return True
        try:
            params = request.params or {}
        except RuntimeError:
            return False
        return params.get("model") == "ir.module.module" and params.get("method") in {
            "web_search_read",
            "search_read",
        }

    @api.model
    def _elsx_require_apps_unlocked(self):
        if not self._elsx_has_http_request():
            return True
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("Only Odoo administrators can access Apps.")
        try:
            unlocked_until = float(request.session.get(APPS_UNLOCK_SESSION_KEY) or 0)
        except (TypeError, ValueError):
            unlocked_until = 0
        if unlocked_until > time.time():
            return True
        request.session.pop(APPS_UNLOCK_SESSION_KEY, None)
        raise AccessError(
            "Apps is password protected. Open Apps from the menu and enter the Apps password."
        )

    @api.model
    def web_search_read(self, *args, **kwargs):
        if self._elsx_is_apps_read_request():
            self._elsx_require_apps_unlocked()
        return super().web_search_read(*args, **kwargs)

    @api.model
    def search_read(self, *args, **kwargs):
        if self._elsx_is_apps_read_request():
            self._elsx_require_apps_unlocked()
        return super().search_read(*args, **kwargs)

    def button_immediate_install(self):
        self._elsx_require_apps_unlocked()
        return super().button_immediate_install()

    def button_immediate_upgrade(self):
        self._elsx_require_apps_unlocked()
        return super().button_immediate_upgrade()

    def button_immediate_uninstall(self):
        self._elsx_require_apps_unlocked()
        return super().button_immediate_uninstall()

    def button_install(self):
        self._elsx_require_apps_unlocked()
        return super().button_install()

    def button_upgrade(self):
        self._elsx_require_apps_unlocked()
        return super().button_upgrade()

    def button_uninstall(self):
        self._elsx_require_apps_unlocked()
        return super().button_uninstall()

    def update_list(self):
        self._elsx_require_apps_unlocked()
        return super().update_list()
