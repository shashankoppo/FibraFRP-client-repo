# -*- coding: utf-8 -*-
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.http import request
from odoo.service import db as db_service

DEFAULT_PUBLIC_DB = os.environ.get('ODOO_DEFAULT_PUBLIC_DB') or os.environ.get('LIVE_DB_NAME') or 'FiberaFRP_DB'


def _add_query_params(url, **params):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, False, '')})
    return urlunparse(parsed._replace(query=urlencode(query)))


def _current_url_without_empty_query():
    if request.httprequest.query_string:
        return request.httprequest.full_path
    return request.httprequest.path or '/'


def _pin_default_public_db(db=False):
    if request.db or request.session.db:
        return False

    db_name = (db or request.params.get('db') or DEFAULT_PUBLIC_DB or '').strip()
    if not db_name:
        return False

    if db_service.exp_db_exist(db_name):
        request.session.db = db_name
        return True
    return False


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
