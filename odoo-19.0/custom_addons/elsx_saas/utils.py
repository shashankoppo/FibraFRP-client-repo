# -*- coding: utf-8 -*-
import hmac
import os


DEFAULT_SAAS_UNLOCK_PASSWORD = 'ELSX-SaaS-2026'
APP_UNLOCK_PARAM = 'elsx_saas.app_unlock_password'
TENANT_ADMIN_PASSWORD_PARAM = 'elsx_saas.tenant_admin_password'
SAAS_ENABLED_PARAM = 'elsx_saas.enabled'


def is_saas_system_enabled(env):
    """Return True only when SaaS automation has been explicitly enabled."""
    value = os.getenv('SAAS_SYSTEM_ENABLED')
    if value is None:
        value = env['ir.config_parameter'].sudo().get_param(SAAS_ENABLED_PARAM, '0')
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def get_saas_app_unlock_password(env):
    """Return the shared password used to unlock app installation."""
    return (
        os.getenv('SAAS_APP_UNLOCK_PASSWORD')
        or env['ir.config_parameter'].sudo().get_param(APP_UNLOCK_PARAM, DEFAULT_SAAS_UNLOCK_PASSWORD)
        or DEFAULT_SAAS_UNLOCK_PASSWORD
    )


def get_saas_tenant_admin_password(env):
    """Return the default admin password assigned to newly provisioned tenants."""
    return (
        os.getenv('SAAS_TENANT_ADMIN_PASSWORD')
        or env['ir.config_parameter'].sudo().get_param(TENANT_ADMIN_PASSWORD_PARAM)
        or get_saas_app_unlock_password(env)
    )


def verify_saas_app_unlock_password(env, password):
    expected = str(get_saas_app_unlock_password(env) or '')
    provided = str(password or '')
    return bool(expected) and hmac.compare_digest(provided, expected)
