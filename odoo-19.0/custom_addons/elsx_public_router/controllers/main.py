# -*- coding: utf-8 -*-
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.http import request
from odoo.service import db as db_service

DEFAULT_PUBLIC_DB = (os.environ.get('ODOO_DEFAULT_PUBLIC_DB') or os.environ.get('LIVE_DB_NAME') or '').strip()
PUBLIC_DB_MAP = os.environ.get('ODOO_PUBLIC_DB_MAP') or os.environ.get('ODOO_DEFAULT_PUBLIC_DB_MAP') or ''


def _add_query_params(url, **params):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, False, '')})
    return urlunparse(parsed._replace(query=urlencode(query)))


def _current_url_without_empty_query():
    if request.httprequest.query_string:
        return request.httprequest.full_path
    return request.httprequest.path or '/'


def _normalise_host(host):
    host = (host or '').strip().lower().partition(':')[0]
    return host[4:] if host.startswith('www.') else host


def _request_host():
    return _normalise_host(request.httprequest.environ.get('HTTP_HOST') or request.httprequest.host)


def _parse_public_db_map():
    mapping = {}
    for item in PUBLIC_DB_MAP.replace(';', ',').split(','):
        item = item.strip()
        if not item:
            continue
        separator = '=' if '=' in item else ':' if ':' in item else None
        if not separator:
            continue
        host, db_name = [part.strip() for part in item.split(separator, 1)]
        host = _normalise_host(host)
        if host and db_name:
            mapping[host] = db_name
    return mapping


def _mapped_db_for_host():
    host = _request_host()
    if not host:
        return False

    mapping = _parse_public_db_map()
    if host in mapping:
        return mapping[host]

    for pattern, db_name in mapping.items():
        if pattern.startswith('*.') and host.endswith(pattern[1:]):
            return db_name
        if pattern.startswith('.') and host.endswith(pattern):
            return db_name
    return False


def _single_available_db():
    dbs = http.db_list(force=True, host=request.httprequest.environ.get('HTTP_HOST'))
    return dbs[0] if len(dbs) == 1 else False


def _is_allowed_db(db_name):
    return bool(db_name and db_service.exp_db_exist(db_name) and http.db_filter([db_name]))


def _select_public_db(db=False):
    candidates = (
        db,
        request.params.get('db'),
        _mapped_db_for_host(),
        DEFAULT_PUBLIC_DB,
        _single_available_db(),
    )
    for candidate in candidates:
        db_name = (candidate or '').strip()
        if _is_allowed_db(db_name):
            return db_name
    return False


def _pin_default_public_db(db=False):
    if request.db or request.session.db:
        return False

    db_name = _select_public_db(db=db)
    if not db_name:
        return False

    request.session.db = db_name
    return True


class ElsxPublicHome(Home):
    @http.route()
    def index(self, s_action=None, db=None, **kw):
        if _pin_default_public_db(db=db):
            return request.redirect(_current_url_without_empty_query(), 302)
        return super().index(s_action=s_action, db=db, **kw)

    @http.route()
    def web_client(self, s_action=None, **kw):
        if _pin_default_public_db(db=kw.get('db')):
            return request.redirect(_current_url_without_empty_query(), 302)
        return super().web_client(s_action=s_action, **kw)

    @http.route()
    def web_login(self, redirect=None, **kw):
        if _pin_default_public_db(db=kw.get('db')):
            return request.redirect(_current_url_without_empty_query(), 302)
        return super().web_login(redirect=redirect, **kw)


class ElsxPublicRouter(http.Controller):
    @http.route('/elsx_attendance/kiosk/<string:token>', type='http', auth='none', sitemap=False)
    def attendance_kiosk(self, token, db=False, from_trial_mode=False, **kwargs):
        if db and db_service.exp_db_exist(db):
            request.session.db = db
        target = _add_query_params(
            '/hr_attendance/%s' % token,
            db=db,
            from_trial_mode=from_trial_mode,
        )
        return request.redirect(target)
