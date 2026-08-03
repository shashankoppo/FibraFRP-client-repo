# -*- coding: utf-8 -*-

LEGACY_WEBHOOK_BASE_URLS = {
    'http://fibera.elsxglobal.com',
    'https://fibera.elsxglobal.com',
}
FIBERAFRP_WEBHOOK_BASE_URL = 'https://fiberafrp.com'


def _clean_base_url(value):
    return (value or '').strip().rstrip('/')


def _get_param(cr, key):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [key])
    row = cr.fetchone()
    return row[0] if row else None


def _set_param(cr, key, value):
    cr.execute("SELECT id FROM ir_config_parameter WHERE key = %s", [key])
    row = cr.fetchone()
    if row:
        cr.execute(
            "UPDATE ir_config_parameter SET value = %s, write_date = now() WHERE id = %s",
            [value, row[0]],
        )
    else:
        cr.execute(
            "INSERT INTO ir_config_parameter (key, value, create_date, write_date) VALUES (%s, %s, now(), now())",
            [key, value],
        )


def migrate(cr, version):
    public_key = 'whatsapp.public.webhook.base.url'
    public_base_url = _clean_base_url(_get_param(cr, public_key))
    if not public_base_url or public_base_url in LEGACY_WEBHOOK_BASE_URLS:
        _set_param(cr, public_key, FIBERAFRP_WEBHOOK_BASE_URL)

    web_base_key = 'web.base.url'
    web_base_url = _clean_base_url(_get_param(cr, web_base_key))
    if web_base_url in LEGACY_WEBHOOK_BASE_URLS:
        _set_param(cr, web_base_key, FIBERAFRP_WEBHOOK_BASE_URL)