# -*- coding: utf-8 -*-


def _normalize_legacy_timezones(env):
    """Repair legacy timezone aliases without changing business records."""
    for table, column in (
        ("res_partner", "tz"),
        ("resource_calendar", "tz"),
        ("resource_resource", "tz"),
        ("whatsapp_scheduled_message", "timezone_id"),
        ("whatsapp_scheduled_campaign", "timezone_id"),
    ):
        env.cr.execute(
            """
            DO $$
            BEGIN
              IF to_regclass('public.%s') IS NOT NULL THEN
                EXECUTE 'UPDATE %s SET %s = ''Asia/Kolkata'' WHERE %s = ''Asia/Calcutta''';
              END IF;
            END $$;
            """
            % (table, table, column, column)
        )


def post_init_hook(env):
    params = env["ir.config_parameter"].sudo()
    params._elsx_restore_native_administration()
    _normalize_legacy_timezones(env)
