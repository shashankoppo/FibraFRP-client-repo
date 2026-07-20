# -*- coding: utf-8 -*-
from odoo.addons.elsx_whatsapp_core.hooks import (
    sync_legacy_ownership,
    sync_shell_schema_aliases,
)


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
