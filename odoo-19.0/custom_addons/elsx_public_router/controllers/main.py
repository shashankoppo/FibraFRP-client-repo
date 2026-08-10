# -*- coding: utf-8 -*-
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from odoo import http
from odoo.http import request
from odoo.service import db as db_service


def _add_query_params(url, **params):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, False, '')})
    return urlunparse(parsed._replace(query=urlencode(query)))


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
