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


def post_init_hook(env):
    """Odoo 19 passes an Environment object to post-init hooks."""
    env['whatsapp.sample.template'].sudo()._seed_sample_templates()
