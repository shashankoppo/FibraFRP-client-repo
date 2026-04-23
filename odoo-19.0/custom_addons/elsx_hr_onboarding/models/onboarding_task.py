# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ElsxOnboardingTask(models.Model):
    _name = 'elsx.onboarding.task'
    _description = 'Onboarding Checklist Task'
    _order = 'sequence, id'

    name = fields.Char(string='Task Name', required=True)
    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one('elsx.onboarding.plan', string='Onboarding Plan', ondelete='cascade')
    employee_id = fields.Many2one(related='plan_id.employee_id', store=True)

    task_type = fields.Selection([
        ('checklist', 'Manual Checklist'),
        ('sign_document', 'Sign a Document'),
        ('read_document', 'Read & Acknowledge'),
        ('it_setup', 'IT Setup Task'),
    ], string='Task Type', default='checklist', required=True)

    state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ], default='pending', string='Status', tracking=True)

    # For sign_document type — links directly to our elsx_sign module
    sign_request_id = fields.Many2one('elsx.sign.request', string='Signing Request')
    sign_status = fields.Selection(related='sign_request_id.state', string='Signing Status')

    description = fields.Html(string='Instructions')
    deadline = fields.Date(string='Deadline')
    responsible_id = fields.Many2one('res.users', string='Assigned To')

    def action_mark_done(self):
        for task in self:
            # If it's a document task, ensure it's actually been signed
            if task.task_type == 'sign_document' and task.sign_request_id:
                if task.sign_request_id.state != 'signed':
                    raise models.ValidationError(
                        f"Cannot mark '{task.name}' as done. The document has not been signed yet."
                    )
            task.state = 'done'
            task.plan_id._compute_progress()

    def action_create_sign_request(self):
        """Wizard-like shortcut to create an elsx.sign.request linked to this task."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Signing Request',
            'res_model': 'elsx.sign.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.plan_id.employee_id.address_home_id.id,
                'default_employee_id': self.plan_id.employee_id.id,
            }
        }
