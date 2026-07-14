# -*- coding: utf-8 -*-
import secrets

from odoo import api, models


APPS_SECRET_PARAM = 'elsx_client_restrictions.apps_secret_token'


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def _elsx_ensure_apps_secret_token(self):
        params = self.sudo()
        if not params.get_param(APPS_SECRET_PARAM):
            params.set_param(APPS_SECRET_PARAM, secrets.token_urlsafe(24))
        return True