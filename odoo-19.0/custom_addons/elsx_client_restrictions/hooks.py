# -*- coding: utf-8 -*-
import secrets


def post_init_hook(env):
    params = env["ir.config_parameter"].sudo()
    if not params.get_param("elsx_client_restrictions.apps_secret_token"):
        params.set_param(
            "elsx_client_restrictions.apps_secret_token",
            secrets.token_urlsafe(24),
        )
