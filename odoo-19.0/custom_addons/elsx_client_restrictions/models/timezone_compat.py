# -*- coding: utf-8 -*-
from odoo import api, models

LEGACY_TIMEZONE_MAP = {
    'Asia/Calcutta': 'Asia/Kolkata',
}


def canonical_timezone(value):
    return LEGACY_TIMEZONE_MAP.get(value, value)


def canonicalize_timezone_vals(vals):
    if vals and vals.get('tz') in LEGACY_TIMEZONE_MAP:
        vals = dict(vals)
        vals['tz'] = canonical_timezone(vals['tz'])
    return vals


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [canonicalize_timezone_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = canonicalize_timezone_vals(vals)
        return super().write(vals)
