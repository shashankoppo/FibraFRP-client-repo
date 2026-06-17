# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    elsx_face_profile_ids = fields.One2many('elsx.face.profile', 'employee_id', string='Face Profiles')
    elsx_face_profile_count = fields.Integer(compute='_compute_elsx_face_profile_count')
    elsx_face_enrolled = fields.Boolean(compute='_compute_elsx_face_profile_count')

    @api.depends('elsx_face_profile_ids.active')
    def _compute_elsx_face_profile_count(self):
        for employee in self:
            profiles = employee.elsx_face_profile_ids.filtered('active')
            employee.elsx_face_profile_count = len(profiles)
            employee.elsx_face_enrolled = bool(profiles)

    def action_open_elsx_face_profiles(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Face Profiles',
            'res_model': 'elsx.face.profile',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_open_elsx_face_attendance(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/elsx_face_attendance',
            'target': 'self',
        }
