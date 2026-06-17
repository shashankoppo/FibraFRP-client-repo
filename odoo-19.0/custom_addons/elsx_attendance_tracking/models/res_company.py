# -*- coding: utf-8 -*-
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from odoo import api, models
from odoo.http import request
from odoo.tools.urls import urljoin as url_join


def _elsx_current_request_base_url(env):
    """Prefer the current tenant host over a copied database's web.base.url."""
    try:
        httprequest = request.httprequest
    except RuntimeError:
        httprequest = None
    if httprequest:
        return httprequest.host_url.rstrip('/')
    return env['res.company'].get_base_url().rstrip('/')


def _elsx_add_query_params(url, **params):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, False, '')})
    return urlunparse(parsed._replace(query=urlencode(query)))


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.depends('attendance_kiosk_key')
    def _compute_attendance_kiosk_url(self):
        base_url = _elsx_current_request_base_url(self.env)
        db_name = self.env.cr.dbname
        for company in self:
            url = url_join(base_url, '/elsx_attendance/kiosk/%s' % company.attendance_kiosk_key)
            company.attendance_kiosk_url = _elsx_add_query_params(url, db=db_name)
