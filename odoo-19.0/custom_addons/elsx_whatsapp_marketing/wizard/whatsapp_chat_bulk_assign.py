# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WhatsAppChatBulkAssignWizard(models.TransientModel):
    _name = 'whatsapp.chat.bulk.assign.wizard'
    _description = 'Bulk Assign WhatsApp Conversations'

    chat_ids = fields.Many2many('whatsapp.chat', required=True)
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assign To',
        required=True,
        domain=[('share', '=', False)],
    )
    transfer_reason = fields.Selection([
        ('manual', 'Manual Transfer'),
        ('availability', 'Agent Unavailable'),
        ('expertise', 'Expertise Required'),
        ('workload', 'Workload Balancing'),
        ('escalation', 'Escalation'),
    ], default='manual', required=True)
    transfer_notes = fields.Text()
    reopen_conversations = fields.Boolean(default=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'whatsapp.chat':
            values['chat_ids'] = [(6, 0, self.env.context.get('active_ids', []))]
        return values

    def action_apply(self):
        self.ensure_one()
        if not self.chat_ids:
            raise UserError(_('Select at least one conversation.'))
        Assignment = self.env['whatsapp.conversation.assignment'].sudo()
        for chat in self.chat_ids:
            Assignment.create({
                'chat_id': chat.id,
                'assigned_user_id': self.assigned_user_id.id,
                'assigned_by': self.env.user.id,
                'previous_user_id': chat.assigned_user_id.id,
                'transfer_reason': self.transfer_reason,
                'transfer_notes': self.transfer_notes,
            })
        values = {'assigned_user_id': self.assigned_user_id.id}
        if self.reopen_conversations:
            values.update({'state': 'open', 'is_archived': False})
        self.chat_ids.write(values)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conversations Assigned'),
                'message': _('%s conversations were assigned.') % len(self.chat_ids),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
