# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging
import re
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
    Secret admin-only shortcut for the Apps action.

    The Apps menu itself is hidden from the normal Odoo navigation. This
    controller keeps controlled access available for administrators who know
    the configured token URL.
    """

    def _get_apps_token(self):
        return request.env["ir.config_parameter"].sudo().get_param(
            "elsx_client_restrictions.apps_secret_token",
            "",
        )

    def _validate_secret_access(self, token):
        if not request.env.user.has_group("base.group_system"):
            _logger.warning(
                "Blocked Apps secret URL for non-system user: %s",
                request.env.user.login,
            )
            raise Forbidden()

        configured_token = self._get_apps_token()
        if not configured_token or token != configured_token:
            _logger.warning(
                "Blocked Apps secret URL with invalid token for user: %s",
                request.env.user.login,
            )
            raise NotFound()

    @http.route("/elsx-secret/apps", type="http", auth="user", website=False)
    @http.route("/action-39", type="http", auth="user", website=False)
    def blocked_apps_access(self, **kwargs):
        """Return a 404 for old or incomplete Apps shortcuts."""
        raise NotFound()

    @http.route("/elsx-secret/apps/<string:token>", type="http", auth="user", website=False)
    @http.route("/action-39/<string:token>", type="http", auth="user", website=False)
    def secret_apps_access(self, token, **kwargs):
        """Open Apps only for system administrators with the configured token."""
        self._validate_secret_access(token)
        action = request.env.ref("base.open_module_tree", raise_if_not_found=False)
        if not action:
            raise NotFound()
        _logger.info("Apps secret URL used by administrator: %s", request.env.user.login)
        return request.redirect("/odoo/action-%s" % action.id)
