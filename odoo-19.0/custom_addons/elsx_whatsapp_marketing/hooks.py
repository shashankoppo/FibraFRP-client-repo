# -*- coding: utf-8 -*-
from odoo.tools.sql import column_exists, table_exists


def _ensure_xmlid_for_existing_record(env, *, table, model, module, xmlid_name, lookup_field, lookup_value):
    if not table_exists(env.cr, table):
        return
    env.cr.execute(
        f"""
        SELECT id
          FROM {table}
         WHERE {lookup_field} = %s
         ORDER BY id
         LIMIT 1
        """,
        [lookup_value],
    )
    row = env.cr.fetchone()
    if not row:
        return
    env.cr.execute(
        """
        INSERT INTO ir_model_data (
            module, name, model, res_id, noupdate, create_date, write_date
        )
        VALUES (%s, %s, %s, %s, true, now() at time zone 'UTC', now() at time zone 'UTC')
        ON CONFLICT (module, name)
        DO UPDATE SET
            model = EXCLUDED.model,
            res_id = EXCLUDED.res_id,
            noupdate = true,
            write_date = now() at time zone 'UTC'
        """,
        [module, xmlid_name, model, row[0]],
    )


def _link_existing_ai_defaults(env):
    """Link legacy default AI rows to their XML IDs before noupdate XML loads."""
    module = 'elsx_whatsapp_marketing'
    for xmlid_name, code in [
        ('elsx_ai_prompt_whatsapp_reply', 'whatsapp_reply_default'),
        ('elsx_ai_prompt_campaign', 'whatsapp_campaign_default'),
        ('elsx_ai_prompt_template', 'whatsapp_template_default'),
        ('elsx_ai_prompt_flow_review', 'whatsapp_flow_review_default'),
    ]:
        _ensure_xmlid_for_existing_record(
            env,
            table='elsx_ai_prompt',
            model='elsx.ai.prompt',
            module=module,
            xmlid_name=xmlid_name,
            lookup_field='code',
            lookup_value=code,
        )


def pre_init_hook(env):
    """Make legacy rows compatible with current unique defaults before install."""
    _link_existing_ai_defaults(env)
    if not table_exists(env.cr, 'whatsapp_message') or not column_exists(env.cr, 'whatsapp_message', 'message_id'):
        return
    env.cr.execute("""
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY account_id, message_id
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
