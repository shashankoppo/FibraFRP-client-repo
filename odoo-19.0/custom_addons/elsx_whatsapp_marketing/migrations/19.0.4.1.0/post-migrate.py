# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api
from odoo.addons.elsx_whatsapp_marketing.hooks import _set_runtime_state


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _set_runtime_state(env, True)
