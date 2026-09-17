from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    agents = env['whatsapp.team.member'].search([]).user_id | env['whatsapp.chat'].search([]).assigned_user_id
    agents.write({'group_ids': [(4, env.ref('elsx_whatsapp_marketing.group_whatsapp_user').id)]})
    for chat in env['whatsapp.chat'].search([('assigned_user_id', '!=', False)]):
        if chat.assigned_user_id not in chat.account_id.team_member_ids.user_id:
            env['whatsapp.team.member'].create({
                'account_id': chat.account_id.id, 'user_id': chat.assigned_user_id.id, 'role': 'agent',
            })
    # Socket settings stay stored for rollback; the browser now always uses ERP Bus.
