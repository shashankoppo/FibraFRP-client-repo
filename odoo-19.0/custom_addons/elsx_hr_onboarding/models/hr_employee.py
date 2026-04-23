# -*- coding: utf-8 -*-
from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    onboarding_plan_ids = fields.One2many(
        'elsx.onboarding.plan', 'employee_id',
        string='Onboarding Plans'
    )
    onboarding_progress = fields.Integer(
        related='onboarding_plan_ids.progress',
        string='Onboarding Progress'
    )
    onboarding_state = fields.Selection(
        related='onboarding_plan_ids.state',
        string='Onboarding Status'
    )
