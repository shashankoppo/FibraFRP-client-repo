# -*- coding: utf-8 -*-
from odoo.tools.sql import column_exists, table_exists


def pre_init_hook(env):
    """Make legacy duplicate webhook rows compatible with the new unique Meta ID index."""
    if not table_exists(env.cr, 'whatsapp_message') or not column_exists(env.cr, 'whatsapp_message', 'message_id'):
        return
    env.cr.execute("""
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY message_id
                    ORDER BY create_date NULLS LAST, id
                ) AS rn
            FROM whatsapp_message
            WHERE message_id IS NOT NULL AND message_id != ''
        )
        UPDATE whatsapp_message AS msg
           SET message_id = NULL,
               error_message = CONCAT_WS(
                   E'\n',
                   NULLIF(msg.error_message, ''),
                   'Duplicate Meta message id cleared during module upgrade; oldest copy kept the original id.'
               )
          FROM ranked
         WHERE msg.id = ranked.id
           AND ranked.rn > 1
    """)


def _sync_cron_records(env):
    """Keep repaired cron targets correct even when XML records are noupdate."""
    cron = env.ref('elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue', raise_if_not_found=False)
    campaign_model = env.ref('elsx_whatsapp_marketing.model_whatsapp_campaign', raise_if_not_found=False)
    if cron and campaign_model:
        cron.sudo().write({
            'model_id': campaign_model.id,
            'code': 'model._cron_process_global_queue()',
        })


def post_init_hook(env):
    """The server passes an Environment object to post-init hooks."""
    env['whatsapp.sample.template'].sudo()._seed_sample_templates()
    env['whatsapp.form'].sudo()._seed_fiberafrp_production_forms()
    env['whatsapp.bot.flow'].sudo()._seed_fiberafrp_assistant_flow()
    env['whatsapp.bot.flow'].sudo()._seed_fiberafrp_advanced_business_flows()
    _sync_cron_records(env)
