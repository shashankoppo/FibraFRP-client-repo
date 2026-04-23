# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ElsxOnboardingPlan(models.Model):
    _name = 'elsx.onboarding.plan'
    _description = 'Employee Onboarding Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Plan Name', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, tracking=True)
    hr_responsible_id = fields.Many2one('res.users', string='HR Responsible', default=lambda self: self.env.user)
    start_date = fields.Date(string='Start Date', default=fields.Date.today)

    state = fields.Selection([
        ('draft', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('done', 'Completed'),
    ], string='Status', default='draft', tracking=True)

    task_ids = fields.One2many('elsx.onboarding.task', 'plan_id', string='Onboarding Tasks')

    progress = fields.Integer(string='Progress (%)', compute='_compute_progress', store=True)

    @api.depends('task_ids.state')
    def _compute_progress(self):
        for plan in self:
            total = len(plan.task_ids)
            if total == 0:
                plan.progress = 0
            else:
                done = len(plan.task_ids.filtered(lambda t: t.state == 'done'))
                plan.progress = int((done / total) * 100)

    def action_start_onboarding(self):
        self.state = 'in_progress'
        # Auto-send all document signing requests linked to tasks
        for task in self.task_ids.filtered(lambda t: t.task_type == 'sign_document' and t.sign_request_id):
            if task.sign_request_id.state == 'draft':
                task.sign_request_id.action_send_request()

    def action_mark_complete(self):
        if all(t.state == 'done' for t in self.task_ids):
            self.state = 'done'
            self.message_post(body=f"🎉 {self.employee_id.name} has completed all onboarding tasks!")
        else:
            pending = self.task_ids.filtered(lambda t: t.state != 'done')
            raise models.ValidationError(f"Still {len(pending)} task(s) pending: {', '.join(pending.mapped('name'))}")
