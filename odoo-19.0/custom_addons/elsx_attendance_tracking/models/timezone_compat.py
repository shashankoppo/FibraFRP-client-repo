# -*- coding: utf-8 -*-
from odoo import api, models

LEGACY_TIMEZONE_MAP = {
    'Asia/Calcutta': 'Asia/Kolkata',
}


def canonical_timezone(value):
    return LEGACY_TIMEZONE_MAP.get(value, value)


def _canonicalize_tz_vals(vals):
    if vals and vals.get('tz') in LEGACY_TIMEZONE_MAP:
        vals = dict(vals)
        vals['tz'] = canonical_timezone(vals['tz'])
    return vals


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [_canonicalize_tz_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = _canonicalize_tz_vals(vals)
        return super().write(vals)


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [_canonicalize_tz_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = _canonicalize_tz_vals(vals)
        return super().write(vals)
