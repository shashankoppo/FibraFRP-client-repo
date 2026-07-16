# -*- coding: utf-8 -*-
import hashlib
import hmac
import secrets

from odoo import api, models


APPS_SECRET_PARAM = 'elsx_client_restrictions.apps_secret_token'
APPS_PASSWORD_HASH_PARAM = 'elsx_client_restrictions.apps_password_hash'
DEFAULT_APPS_PASSWORD_HASH = 'ef4f50116b7e91c31b2213129dc59fed3b6c833ef35a480b95d54dc483335dba'


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def _elsx_ensure_apps_secret_token(self):
        params = self.sudo()
        if not params.get_param(APPS_SECRET_PARAM):
            params.set_param(APPS_SECRET_PARAM, secrets.token_urlsafe(24))
        if not params.get_param(APPS_PASSWORD_HASH_PARAM):
            params.set_param(APPS_PASSWORD_HASH_PARAM, DEFAULT_APPS_PASSWORD_HASH)
        return True

    @api.model
    def _elsx_verify_apps_password(self, password):
        params = self.sudo()
        expected = params.get_param(APPS_PASSWORD_HASH_PARAM) or DEFAULT_APPS_PASSWORD_HASH
        supplied = hashlib.sha256((password or '').encode('utf-8')).hexdigest()
        return hmac.compare_digest(supplied, expected)
