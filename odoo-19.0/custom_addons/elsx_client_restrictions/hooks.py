# -*- coding: utf-8 -*-
import secrets


def _normalize_legacy_timezones(env):
    """Repair legacy timezone aliases that PostgreSQL cannot group by."""
    for table, column in (
        ('res_partner', 'tz'),
        ('resource_calendar', 'tz'),
        ('resource_resource', 'tz'),
        ('whatsapp_scheduled_message', 'timezone_id'),
        ('whatsapp_scheduled_campaign', 'timezone_id'),
    ):
        env.cr.execute(
            """
            DO $$
            BEGIN
              IF to_regclass('public.%s') IS NOT NULL THEN
                EXECUTE 'UPDATE %s SET %s = ''Asia/Kolkata'' WHERE %s = ''Asia/Calcutta''';
              END IF;
            END $$;
            """ % (table, table, column, column)
        )


def post_init_hook(env):
    params = env["ir.config_parameter"].sudo()
    if not params.get_param("elsx_client_restrictions.apps_secret_token"):
        params.set_param(
            "elsx_client_restrictions.apps_secret_token",
            secrets.token_urlsafe(24),
        )
    _normalize_legacy_timezones(env)
