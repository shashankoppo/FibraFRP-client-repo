# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging
import re
import time
from urllib.parse import urlencode
from markupsafe import escape
from werkzeug.exceptions import Forbidden, NotFound
from odoo.addons.web.controllers.database import Database as WebDatabaseController

_logger = logging.getLogger(__name__)


_DATABASE_MANAGER_BRANDING_REPLACEMENTS = (
    ('<title>Odoo</title>', '<title>ELSxGlobal Database Manager</title>'),
    ('href="/web/static/img/favicon.ico"', 'href="/elsx_client_restrictions/static/src/img/elsxglobal_favicon.svg"'),
    (
        '<img src="/web/static/img/logo2.png" class="img-fluid d-block mx-auto"/>',
        '<div class="text-center my-4">'
        '<img src="/elsx_client_restrictions/static/src/img/elsxglobal_favicon.svg" '
        'class="img-fluid d-block mx-auto mb-3" style="height: 72px" alt="ELSxGlobal"/>'
        '<h2 class="h3 mb-1">ELSxGlobal Database Manager</h2>'
        '<p class="text-muted mb-0">Create, backup, restore, and select company databases.</p>'
        '</div>',
    ),
    ('Warning, your Odoo database manager is not protected.', 'Warning, your ELSxGlobal database manager is not protected.'),
    (
        'To enhance your experience, some data may be sent to Odoo online services. See our '
        '<a href="https://www.odoo.com/privacy" target="_blank">Privacy Policy</a>.',
        'Use this form only for controlled ELSxGlobal database creation. Configure live integrations separately after login.',
    ),
    (
        'In order to avoid conflicts between databases, Odoo needs to know if this database was moved or copied.',
        'In order to avoid conflicts between databases, ELSxGlobal needs to know if this database was moved or copied.',
    ),
)


def _apply_elsx_database_manager_branding(content):
    is_bytes = isinstance(content, (bytes, bytearray))
    if is_bytes:
        rendered = bytes(content).decode('utf-8', errors='replace')
    elif isinstance(content, str):
        rendered = content
    else:
        return content

    for old, new in _DATABASE_MANAGER_BRANDING_REPLACEMENTS:
        rendered = rendered.replace(old, new)

    rendered = re.sub(
        r'<title>\s*Odoo\s*</title>',
        '<title>ELSxGlobal Database Manager</title>',
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r'href="/web/static/img/favicon\.ico"',
        'href="/elsx_client_restrictions/static/src/img/elsxglobal_favicon.svg"',
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r'<img\b[^>]*src="/web/static/img/logo2\.png"[^>]*/>',
        '<div class="text-center my-4">'
        '<img src="/elsx_client_restrictions/static/src/img/elsxglobal_favicon.svg" '
        'class="img-fluid d-block mx-auto mb-3" style="height: 72px" alt="ELSxGlobal"/>'
        '<h2 class="h3 mb-1">ELSxGlobal Database Manager</h2>'
        '<p class="text-muted mb-0">Create, backup, restore, and select company databases.</p>'
        '</div>',
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r'To enhance your experience,\s*some data may be sent to Odoo online services\.\s*See our\s*'
        r'<a href="https://www\.odoo\.com/privacy" target="_blank">Privacy Policy</a>\.',
        'Use this form only for controlled ELSxGlobal database creation. Configure live integrations separately after login.',
        rendered,
        flags=re.IGNORECASE,
    )

    return rendered.encode('utf-8') if is_bytes else rendered


class ElsxDatabaseManagerBrandingController(WebDatabaseController):
    """Keep the standard database manager, with visible ELSxGlobal branding only."""

    def _render_template(self, **d):
        content = super()._render_template(**d)
        return _apply_elsx_database_manager_branding(content)

    @http.route('/web/database/selector', type='http', auth='none')
    def selector(self, **kw):
        return super().selector(**kw)

    @http.route('/web/database/manager', type='http', auth='none')
    def manager(self, **kw):
        return super().manager(**kw)

if not getattr(WebDatabaseController._render_template, '_elsx_branded', False):
    _original_database_render_template = WebDatabaseController._render_template

    def _render_template_with_elsx_branding(self, **d):
        content = _original_database_render_template(self, **d)
        return _apply_elsx_database_manager_branding(content)

    _render_template_with_elsx_branding._elsx_branded = True
    WebDatabaseController._render_template = _render_template_with_elsx_branding


class SystemAccessShortcutController(http.Controller):
    """
    Secret admin-only shortcuts for Apps and Settings actions.

    Apps access is additionally guarded by a password gate. Standard Odoo
    login and system-admin permissions still protect module management.
    """

    APPS_UNLOCK_SESSION_KEY = "elsx_apps_unlocked_until"
    APPS_UNLOCK_TTL_SECONDS = 8 * 60 * 60

    def _get_apps_token(self):
        return request.env["ir.config_parameter"].sudo().get_param(
            "elsx_client_restrictions.apps_secret_token",
            "",
        )

    def _ensure_system_user(self):
        if not request.env.user.has_group("base.group_system"):
            _logger.warning(
                "Blocked Apps/Settings shortcut for non-system user: %s",
                request.env.user.login,
            )
            raise Forbidden()

    def _validate_secret_access(self, token):
        self._ensure_system_user()
        configured_token = self._get_apps_token()
        if not configured_token or token != configured_token:
            _logger.warning(
                "Blocked Apps secret URL with invalid token for user: %s",
                request.env.user.login,
            )
            raise NotFound()

    def _is_apps_unlocked(self):
        try:
            unlocked_until = int(request.session.get(self.APPS_UNLOCK_SESSION_KEY, 0) or 0)
        except Exception:
            return False
        return unlocked_until > int(time.time())

    def _set_apps_unlocked(self):
        request.session[self.APPS_UNLOCK_SESSION_KEY] = int(time.time()) + self.APPS_UNLOCK_TTL_SECONDS
        request.session.modified = True

    def _safe_next_url(self, next_url):
        if next_url and next_url.startswith('/') and not next_url.startswith('//'):
            return next_url
        return None

    def _repair_access_metadata(self):
        menu_model = request.env['ir.ui.menu'].sudo()
        repair = getattr(menu_model, '_elsx_repair_startup_metadata', None)
        if repair:
            repair()

    def _get_backend_action_url(self, action_xmlid, menu_xmlid=None, extra_query=None):
        action = request.env.ref(action_xmlid, raise_if_not_found=False)
        if not action:
            raise NotFound()
        menu = request.env.ref(menu_xmlid, raise_if_not_found=False) if menu_xmlid else False
        query = {
            'cids': request.env.company.id,
        }
        if menu:
            query.update({
                'menu_id': menu.id,
                'active_id': menu.id,
            })
        if extra_query:
            query.update(extra_query)
        return '/odoo/action-%s?%s' % (action.id, urlencode(query))

    def _redirect_to_backend_action(self, action_xmlid, menu_xmlid=None, extra_query=None):
        return request.redirect(self._get_backend_action_url(action_xmlid, menu_xmlid, extra_query=extra_query))

    def _render_apps_password_form(self, next_url, error=None):
        csrf_token = request.csrf_token()
        escaped_next = escape(next_url)
        error_html = ''
        if error:
            error_html = '<div class="alert alert-danger">%s</div>' % escape(error)
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
      <input type="hidden" name="next" value="{escaped_next}">
      <label for="apps_password">Password</label>
      <input id="apps_password" type="password" name="password" autocomplete="current-password" autofocus required>
      <button type="submit">Unlock Apps</button>
    </form>
  </main>
</body>
</html>"""
        html = html.replace('{error_html}', str(error_html))
        html = html.replace('{csrf_token}', str(escape(csrf_token)))
        html = html.replace('{escaped_next}', str(escaped_next))
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store'),
        ])

    @http.route('/elsx/apps/unlock', type='http', auth='user', website=False, methods=['GET', 'POST'])
    def apps_password_unlock(self, **kwargs):
        self._ensure_system_user()
        self._repair_access_metadata()
        default_next = self._get_backend_action_url('base.open_module_tree', 'base.menu_management', {'search_default_app': 1})
        next_url = self._safe_next_url(kwargs.get('next')) or default_next

        if self._is_apps_unlocked():
            return request.redirect(next_url)

        if request.httprequest.method == 'POST':
            password = kwargs.get('password', '')
            if request.env['ir.config_parameter'].sudo()._elsx_verify_apps_password(password):
                self._set_apps_unlocked()
                _logger.info('Apps password gate unlocked by administrator: %s', request.env.user.login)
                return request.redirect(next_url)
            return self._render_apps_password_form(next_url, error='Invalid Apps password.')

        return self._render_apps_password_form(next_url)

    @http.route('/elsx-secret/apps', type='http', auth='user', website=False)
    @http.route('/action-39', type='http', auth='user', website=False)
    def blocked_apps_access(self, **kwargs):
        """Open the password gate for old or incomplete Apps shortcuts."""
        self._ensure_system_user()
        return request.redirect('/elsx/apps/unlock')

    @http.route('/elsx-secret/apps/<string:token>', type='http', auth='user', website=False)
    @http.route('/action-39/<string:token>', type='http', auth='user', website=False)
    def secret_apps_access(self, token, **kwargs):
        """Open Apps only for system administrators with token and password."""
        self._validate_secret_access(token)
        self._repair_access_metadata()
        if not self._is_apps_unlocked():
            return request.redirect('/elsx/apps/unlock?%s' % urlencode({'next': request.httprequest.path}))
        _logger.info('Apps secret URL used by administrator: %s', request.env.user.login)
        return self._redirect_to_backend_action('base.open_module_tree', 'base.menu_management', {'search_default_app': 1})

    @http.route('/elsx-secret/settings', type='http', auth='user', website=False)
    def blocked_settings_access(self, **kwargs):
        """Return a 404 for old or incomplete Settings shortcuts."""
        raise NotFound()

    @http.route('/elsx-secret/settings/<string:token>', type='http', auth='user', website=False)
    def secret_settings_access(self, token, **kwargs):
        """Open Settings only for system administrators with the configured token."""
        self._validate_secret_access(token)
        self._repair_access_metadata()
        _logger.info('Settings secret URL used by administrator: %s', request.env.user.login)
        return self._redirect_to_backend_action('base_setup.action_general_configuration', 'base.menu_administration')
