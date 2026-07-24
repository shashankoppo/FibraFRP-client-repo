# -*- coding: utf-8 -*-
import logging
import time
from urllib.parse import urlencode

from markupsafe import escape
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class AppsPasswordController(http.Controller):
    """Password gate for the native Apps action."""

    APPS_UNLOCK_SESSION_KEY = "elsx_apps_unlocked_until"
    APPS_UNLOCK_TTL_SECONDS = 30 * 60

    def _ensure_system_user(self):
        if not request.env.user.has_group("base.group_system"):
            _logger.warning(
                "Blocked Apps access for non-system user: %s",
                request.env.user.login,
            )
            raise Forbidden()

    def _set_apps_unlocked(self):
        request.session[self.APPS_UNLOCK_SESSION_KEY] = (
            int(time.time()) + self.APPS_UNLOCK_TTL_SECONDS
        )

    def _clear_apps_unlock(self):
        request.session.pop(self.APPS_UNLOCK_SESSION_KEY, None)

    def _safe_next_url(self, next_url):
        if (
            next_url
            and next_url.startswith("/odoo")
            and not next_url.startswith("//")
        ):
            return next_url
        return None

    def _get_apps_url(self):
        action = request.env.ref("base.open_module_tree")
        menu = request.env.ref("base.menu_management")
        query = urlencode(
            {
                "cids": request.env.company.id,
                "menu_id": menu.id,
                "active_id": menu.id,
                "search_default_app": 1,
            }
        )
        return "/odoo/action-%s?%s" % (action.id, query)

    def _render_password_form(self, next_url, error=None):
        error_html = ""
        if error:
            error_html = '<div class="alert">%s</div>' % escape(error)
        html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Apps Password</title>
  <style>
    :root { color-scheme: light; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: Arial, sans-serif; background: #f5f7fb; color: #172033; }
    main { width: min(420px, calc(100vw - 32px)); background: #fff; border: 1px solid #dfe5ef; border-radius: 8px; box-shadow: 0 18px 50px rgba(23, 32, 51, .12); padding: 28px; }
    h1 { font-size: 22px; line-height: 1.2; margin: 0 0 8px; }
    p { margin: 0 0 22px; color: #5f6b7a; font-size: 14px; line-height: 1.5; }
    label { display: block; margin-bottom: 8px; font-size: 13px; font-weight: 700; }
    input[type="password"] { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; font-size: 16px; }
    button { width: 100%; margin-top: 18px; border: 0; border-radius: 6px; padding: 12px 14px; background: #155eef; color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; }
    .alert { border-radius: 6px; padding: 10px 12px; margin-bottom: 16px; font-size: 14px; background: #fff1f2; border: 1px solid #fecdd3; color: #be123c; }
  </style>
</head>
<body>
  <main>
    <h1>Apps Password Required</h1>
    <p>Enter the Apps password to open and manage modules.</p>
    {error_html}
    <form method="post" action="/elsx/apps/unlock">
      <input type="hidden" name="csrf_token" value="{csrf_token}">
      <input type="hidden" name="next" value="{next_url}">
      <label for="apps_password">Password</label>
      <input id="apps_password" type="password" name="password" autocomplete="current-password" autofocus required>
      <button type="submit">Unlock Apps</button>
    </form>
  </main>
</body>
</html>"""
        html = html.replace("{error_html}", str(error_html))
        html = html.replace("{csrf_token}", str(escape(request.csrf_token())))
        html = html.replace("{next_url}", str(escape(next_url)))
        return request.make_response(
            html,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store"),
            ],
        )

    @http.route(
        "/elsx/apps/unlock",
        type="http",
        auth="user",
        website=False,
        methods=["GET", "POST"],
    )
    def apps_password_unlock(self, **kwargs):
        self._ensure_system_user()
        next_url = self._safe_next_url(kwargs.get("next")) or self._get_apps_url()

        if request.httprequest.method == "POST":
            password = kwargs.get("password", "")
            verifier = request.env["ir.config_parameter"].sudo()
            if verifier._elsx_verify_apps_password(password):
                self._set_apps_unlocked()
                _logger.info(
                    "Apps password gate unlocked by administrator: %s",
                    request.env.user.login,
                )
                return request.redirect(next_url)
            self._clear_apps_unlock()
            return self._render_password_form(
                next_url,
                error="Invalid Apps password.",
            )

        # A fresh menu entry always starts a new challenge.
        self._clear_apps_unlock()
        return self._render_password_form(next_url)

    @http.route(
        [
            "/elsx-secret/apps",
            "/action-39",
            "/elsx-secret/apps/<string:legacy_token>",
            "/action-39/<string:legacy_token>",
        ],
        type="http",
        auth="user",
        website=False,
    )
    def legacy_apps_shortcut(self, legacy_token=None, **kwargs):
        self._ensure_system_user()
        return request.redirect("/elsx/apps/unlock")
