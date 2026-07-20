# -*- coding: utf-8 -*-
import logging

from odoo.exceptions import UserError
from odoo.tools.sql import column_exists, table_exists


_logger = logging.getLogger(__name__)

LEGACY_MODULE = 'elsx_whatsapp_marketing'
WHATSAPP_CORE_MODULE = 'elsx_whatsapp_core'
AI_CORE_MODULE = 'elsx_ai_core'

UI_OWNED_MODELS = {
    'ir.actions.act_url',
    'ir.actions.act_window',
    'ir.actions.client',
    'ir.actions.report',
    'ir.asset',
    'ir.ui.menu',
    'ir.ui.view',
}

SHELL_MODEL_NAMES = {
    'whatsapp.send.wizard',
    'whatsapp.import.wizard',
    'whatsapp.new.chat.wizard',
    'whatsapp.invoice.send.wizard',
    'whatsapp.uninstall.readiness.wizard',
    'whatsapp.campaign.wizard',
    'whatsapp.chat.bulk.assign.wizard',
}


def pre_init_hook(env):
    """Fail closed if legacy rows cannot satisfy the existing Meta ID contract."""
    if not table_exists(env.cr, 'whatsapp_message') or not column_exists(
        env.cr, 'whatsapp_message', 'message_id'
    ):
        return
    env.cr.execute(
        """
        SELECT count(*)
          FROM (
                SELECT message_id
                  FROM whatsapp_message
                 WHERE message_id IS NOT NULL AND message_id != ''
              GROUP BY message_id
                HAVING count(*) > 1
               ) AS duplicate_ids
        """
    )
    duplicate_count = env.cr.fetchone()[0]
    if duplicate_count:
        raise UserError(
            'WhatsApp Core bridge blocked: found %s duplicate Meta message ID group(s). '
            'No message rows were changed. Resolve the duplicates on an isolated restored clone, '
            'verify the result, and rerun the controlled database upgrade.' % duplicate_count
        )


def _target_module_for_data(env, data):
    if data.model in UI_OWNED_MODELS or data.model.startswith('ir.actions.'):
        return False
    if data.model.startswith('elsx.ai.'):
        return AI_CORE_MODULE

    if data.model == 'ir.model':
        model = env['ir.model'].sudo().browse(data.res_id).exists()
        if not model:
            return False
        if model.model in SHELL_MODEL_NAMES:
            return False
        return AI_CORE_MODULE if model.model.startswith('elsx.ai.') else WHATSAPP_CORE_MODULE

    if data.model == 'ir.model.fields':
        field = env['ir.model.fields'].sudo().browse(data.res_id).exists()
        if not field:
            return False
        if field.model in SHELL_MODEL_NAMES:
            return False
        return AI_CORE_MODULE if field.model.startswith('elsx.ai.') else WHATSAPP_CORE_MODULE

    if data.model == 'ir.model.fields.selection':
        selection = env['ir.model.fields.selection'].sudo().browse(data.res_id).exists()
        if not selection:
            return False
        if selection.field_id.model in SHELL_MODEL_NAMES:
            return False
        return AI_CORE_MODULE if selection.field_id.model.startswith('elsx.ai.') else WHATSAPP_CORE_MODULE

    if data.model == 'ir.model.constraint':
        constraint = env['ir.model.constraint'].sudo().browse(data.res_id).exists()
        if not constraint:
            return False
        model_name = constraint.model.model if constraint.model else ''
        if model_name in SHELL_MODEL_NAMES:
            return False
        return AI_CORE_MODULE if model_name.startswith('elsx.ai.') else WHATSAPP_CORE_MODULE

    if data.model == 'ir.model.access':
        access = env['ir.model.access'].sudo().browse(data.res_id).exists()
        if access and access.model_id.model in SHELL_MODEL_NAMES:
            return False
        if access and access.model_id.model.startswith('elsx.ai.'):
            return AI_CORE_MODULE

    return WHATSAPP_CORE_MODULE


def sync_legacy_ownership(env):
    """Add durable core ownership without copying or rewriting business rows."""
    Data = env['ir.model.data'].sudo()
    aliases = 0
    for data in Data.search([('module', '=', LEGACY_MODULE)]):
        target_module = _target_module_for_data(env, data)
        if not target_module:
            continue
        target = Data.search(
            [('module', '=', target_module), ('name', '=', data.name)],
            limit=1,
        )
        values = {
            'model': data.model,
            'res_id': data.res_id,
            'noupdate': True,
        }
        if target:
            target.write(values)
        else:
            Data.create({
                'module': target_module,
                'name': data.name,
                **values,
            })
        aliases += 1

    Module = env['ir.module.module'].sudo()
    legacy = Module.search([('name', '=', LEGACY_MODULE)], limit=1)
    core = Module.search([('name', '=', WHATSAPP_CORE_MODULE)], limit=1)
    relations = 0
    if legacy and core:
        Relation = env['ir.model.relation'].sudo()
        for relation in Relation.search([('module', '=', legacy.id)]):
            if Relation.search_count([
                ('name', '=', relation.name),
                ('module', '=', core.id),
            ]):
                continue
            Relation.create({
                'name': relation.name,
                'model': relation.model.id,
                'module': core.id,
            })
            relations += 1

    _logger.info(
        'WhatsApp core ownership bridge synchronized %s XML IDs and %s relation tables without copying records.',
        aliases,
        relations,
    )
    return {'xml_ids': aliases, 'relations': relations}


def sync_shell_schema_aliases(env):
    '''Keep legacy model references valid on both upgraded and fresh databases.'''
    Data = env['ir.model.data'].sudo()
    aliases = 0
    model_data = Data.search([
        ('module', 'in', (WHATSAPP_CORE_MODULE, AI_CORE_MODULE)),
        ('model', '=', 'ir.model'),
    ])
    for data in model_data:
        model = env['ir.model'].sudo().browse(data.res_id).exists()
        if not model or model.model in SHELL_MODEL_NAMES:
            continue
        alias = Data.search([
            ('module', '=', LEGACY_MODULE),
            ('name', '=', data.name),
        ], limit=1)
        values = {
            'model': data.model,
            'res_id': data.res_id,
            'noupdate': True,
        }
        if alias:
            alias.write(values)
        else:
            Data.create({
                'module': LEGACY_MODULE,
                'name': data.name,
                **values,
            })
        aliases += 1
    _logger.info(
        'WhatsApp shell compatibility synchronized %s legacy model aliases.',
        aliases,
    )
    return aliases


def post_init_hook(env):
    sync_shell_schema_aliases(env)
    sync_legacy_ownership(env)
