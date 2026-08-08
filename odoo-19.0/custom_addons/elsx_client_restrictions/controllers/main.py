# -*- coding: utf-8 -*-
import html
import time

from odoo import http
from odoo.http import request


APPS_UNLOCK_SESSION_KEY = "elsx_apps_unlocked_until"
APPS_UNLOCK_SECONDS = 30 * 60


class ElsxAppsLockController(http.Controller):

    def _clear_unlock(self):
        try:
            if APPS_UNLOCK_SESSION_KEY in request.session:
                del request.session[APPS_UNLOCK_SESSION_KEY]
        except Exception:
            pass

    def _render_unlock_form(self, error=None):
        error_html = ""
        if error:
            error_html = """
                <div class="alert alert-danger" role="alert">%s</div>
            """ % html.escape(error)
        html_doc = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Unlock Apps</title>
    <style>
        :root { color-scheme: light; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f6f7fb;
            color: #1f2933;
            display: grid;
            place-items: center;
        }
        main {
            width: min(420px, calc(100vw - 32px));
            background: white;
            border: 1px solid #d8dee8;
            border-radius: 8px;
            box-shadow: 0 18px 50px rgba(15, 23, 42, .12);
            padding: 28px;
        }
        h1 { margin: 0 0 8px; font-size: 24px; font-weight: 650; }
        p { margin: 0 0 22px; color: #5f6b7a; line-height: 1.45; }
        label { display: block; margin-bottom: 8px; font-weight: 600; }
        input[type="password"] {
            box-sizing: border-box;
            width: 100%;
            height: 42px;
            border: 1px solid #c8d0dc;
            border-radius: 6px;
            padding: 0 12px;
            font-size: 16px;
        }
        input[type="password"]:focus {
            border-color: #714b67;
            outline: 2px solid rgba(113, 75, 103, .18);
        }
        .actions { display: flex; gap: 10px; align-items: center; margin-top: 20px; }
        button, a {
            border-radius: 6px;
            padding: 9px 14px;
            font-size: 15px;
            text-decoration: none;
        }
        button { border: 0; background: #714b67; color: white; cursor: pointer; font-weight: 600; }
        a { color: #526172; }
        .alert {
            border-radius: 6px;
            padding: 10px 12px;
            margin-bottom: 16px;
            background: #fdecec;
            color: #8f1d1d;
            border: 1px solid #f5b7b7;
        }
        small { display: block; margin-top: 16px; color: #7a8594; }
    </style>
</head>
<body>
    <main>
        <h1>Unlock Apps</h1>
        <p>Apps management is protected. Log in as an administrator, then enter the developer password to continue.</p>
        __ERROR_HTML__
        <form method="post" action="/elsx/apps/unlock" autocomplete="off">
            <label for="apps_password">Apps password</label>
            <input id="apps_password" name="apps_password" type="password" autofocus required>
            <div class="actions">
                <button type="submit">Unlock Apps</button>
                <a href="/odoo">Back to ELSxGlobal</a>
            </div>
        </form>
        <small>Access stays unlocked for 30 minutes after a correct password.</small>
    </main>
</body>
</html>
        """
        return request.make_response(
            html_doc.replace("__ERROR_HTML__", error_html),
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route("/elsx/apps/unlock", type="http", auth="public", methods=["GET"], csrf=False)
    def unlock_apps_form(self, **post):
        self._clear_unlock()
        return self._render_unlock_form()

    @http.route("/elsx/apps/unlock", type="http", auth="public", methods=["POST"], csrf=False)
    def unlock_apps_submit(self, **post):
        self._clear_unlock()
        if not request.env.user.has_group("base.group_system"):
            return self._render_unlock_form("Only system administrators can unlock Apps.")

        password = post.get("apps_password") or ""
        if not request.env["ir.config_parameter"].sudo()._elsx_apps_password_matches(password):
            return self._render_unlock_form("Incorrect Apps password.")

        try:
            request.session[APPS_UNLOCK_SESSION_KEY] = time.time() + APPS_UNLOCK_SECONDS
        except Exception:
            return self._render_unlock_form("Could not create an Apps unlock session. Please refresh and try again.")
        action = request.env.ref("base.open_module_tree", raise_if_not_found=False)
        menu = request.env.ref("base.menu_module_tree", raise_if_not_found=False)
        if action and menu:
            return request.redirect("/odoo/action-base.open_module_tree?menu_id=%s" % menu.id)
        if action:
            return request.redirect("/odoo/action-base.open_module_tree")
        return request.redirect("/odoo/apps")
