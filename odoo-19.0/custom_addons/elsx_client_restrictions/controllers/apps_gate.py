from html import escape

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.action import Action
from odoo.addons.web.controllers.dataset import DataSet

from ..apps_gate import (SESSION_KEY, claim_attempt, is_unlocked, password_matches,
                         protected_model, require_unlocked, unlock_ticket)


def gate_action():
    return {"type": "ir.actions.act_url", "url": "/elsx/apps/unlock", "target": "self"}


class AppsAction(Action):
    @http.route()
    def load(self, action_id, context=None):
        result = super().load(action_id, context=context)
        if result and (protected_model(result.get("res_model"))
                       or result.get("tag") in ("apps", "apps.action_install_kiosk")) and not is_unlocked():
            return gate_action()
        return result

    @http.route()
    def run(self, action_id, context=None):
        action = request.env["ir.actions.server"].browse(action_id)
        if protected_model(action.model_id.model):
            require_unlocked()
        return super().run(action_id, context=context)


class AppsDataSet(DataSet):
    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        if protected_model(model):
            require_unlocked()
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        if protected_model(model):
            require_unlocked()
        return super().call_button(model, method, args, kwargs, path=path)


class AppsUnlock(http.Controller):
    @http.route("/elsx/apps/unlock", type="http", auth="user", methods=["GET", "POST"], csrf=True)
    def unlock(self, password=None, **kwargs):
        if not request.env.user.has_group("base.group_system"):
            raise Forbidden()
        error = ""
        status = 200
        if request.httprequest.method == "POST":
            request.session.pop(SESSION_KEY, None)
            if not claim_attempt(request.env.registry, request.session.uid):
                error, status = "Too many attempts. Try again in five minutes.", 429
            elif password_matches(password):
                request.session[SESSION_KEY] = unlock_ticket(request.session.uid, request.db)
                return request.redirect("/odoo/apps")
            else:
                error, status = "Incorrect Apps password.", 403
        # A new entry into the gate always starts locked, including administrator/superuser sessions.
        request.session.pop(SESSION_KEY, None)
        html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Unlock Apps</title>
<style>body{font:16px system-ui,sans-serif;color:#212529;background:#f8f9fa;margin:0;letter-spacing:0}
main{max-width:360px;margin:12vh auto;padding:24px}h1{font-size:24px}label,input,button{display:block}
input{box-sizing:border-box;width:100%%;padding:10px;margin:8px 0 20px;border:1px solid #767676;border-radius:4px}
button{background:#714b67;color:white;border:0;border-radius:4px;padding:10px 18px;font:inherit;cursor:pointer}
.error{color:#b42318}a{display:inline-block;color:#495057;margin-top:20px}</style></head><body><main>
<h1>Unlock Apps</h1><p class="error" role="alert">%s</p><form method="post" action="/elsx/apps/unlock">
<input type="hidden" name="csrf_token" value="%s"><label for="password">Apps password</label>
<input id="password" name="password" type="password" autocomplete="off" maxlength="256" required autofocus>
<button type="submit">Unlock Apps</button></form><a href="/odoo">Back to ERP</a></main></body></html>""" % (
            escape(error), escape(request.csrf_token()))
        return request.make_response(html, status=status, headers=[
            ("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store"),
            ("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
        ])

    @http.route("/elsx/apps/lock", type="http", auth="user", methods=["POST"], csrf=True)
    def lock(self, **kwargs):
        request.session.pop(SESSION_KEY, None)
        return request.redirect("/elsx/apps/unlock")
