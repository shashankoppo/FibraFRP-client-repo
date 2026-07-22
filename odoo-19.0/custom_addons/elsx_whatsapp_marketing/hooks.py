# -*- coding: utf-8 -*-
from odoo.addons.elsx_whatsapp_core.hooks import (
    sync_legacy_ownership,
    sync_shell_schema_aliases,
)


ENABLED_RUNTIME_CRON_XMLIDS = (
    'ir_cron_process_whatsapp_drip_campaigns',
    'ir_cron_process_whatsapp_queue',
    'ir_cron_resume_delayed_bot_flows',
    'ir_cron_process_scheduled_messages',
    'ir_cron_cleanup_webhook_logs',
    'ir_cron_retry_failed_messages',
    'ir_cron_cleanup_api_logs',
    'ir_cron_evaluate_ab_tests',
    'ir_cron_process_scheduled_campaigns',
    'ir_cron_reset_daily_counters',
    'ir_cron_send_overdue_invoice_reminders',
)

DISABLED_RUNTIME_CRON_XMLIDS = (
    'ir_cron_cleanup_whatsapp_messages',
)


def _set_runtime_state(env, enabled):
    """Switch WhatsApp processing without touching any business records."""
    env['ir.config_parameter'].sudo().set_param(
        'whatsapp.runtime.enabled',
        'True' if enabled else 'False',
    )

    enabled_xmlids = set(ENABLED_RUNTIME_CRON_XMLIDS) if enabled else set()
    for name in ENABLED_RUNTIME_CRON_XMLIDS + DISABLED_RUNTIME_CRON_XMLIDS:
        cron = env.ref(
            f'elsx_whatsapp_marketing.{name}',
            raise_if_not_found=False,
        )
        if cron:
            cron.sudo().write({'active': name in enabled_xmlids})


def _sync_cron_records(env):
    '''Keep repaired cron targets correct even when XML records are noupdate.'''
    cron = env.ref(
        'elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue',
        raise_if_not_found=False,
    )
    campaign_model = env.ref(
        'elsx_whatsapp_core.model_whatsapp_campaign',
        raise_if_not_found=False,
    )
    if cron and campaign_model:
        cron.sudo().write({
            'model_id': campaign_model.id,
            'code': 'model._cron_process_global_queue()',
        })


def post_init_hook(env):
    '''Seed compatibility content and establish durable core ownership.'''
    env['whatsapp.sample.template'].sudo()._seed_sample_templates()
    env['whatsapp.form'].sudo()._seed_fiberafrp_production_forms()
    env['whatsapp.bot.flow'].sudo()._seed_fiberafrp_assistant_flow()
    env['whatsapp.bot.flow'].sudo()._seed_fiberafrp_advanced_business_flows()
    _sync_cron_records(env)
    sync_shell_schema_aliases(env)
    sync_legacy_ownership(env)
    _set_runtime_state(env, True)


def uninstall_hook(env):
    """Pause every runtime path before Odoo removes the application shell."""
    _set_runtime_state(env, False)
