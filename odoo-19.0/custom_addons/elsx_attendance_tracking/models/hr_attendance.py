# -*- coding: utf-8 -*-
from odoo import _, api, models

from .res_company import _elsx_add_query_params
from .timezone_compat import canonical_timezone


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    @api.model
    def web_read_group(self, *args, **kwargs):
        safe_tz = canonical_timezone(self.env.context.get('tz'))
        if safe_tz != self.env.context.get('tz'):
            return super(HrAttendance, self.with_context(tz=safe_tz)).web_read_group(*args, **kwargs)
        return super().web_read_group(*args, **kwargs)

    @api.model
    def get_kiosk_url(self):
        return self.env.company.attendance_kiosk_url

    def action_try_kiosk(self):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_user"):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _("You don't have the rights to execute that action."),
                    'type': 'info',
                },
            }
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': _elsx_add_query_params(
                self.env.company.attendance_kiosk_url,
                from_trial_mode='True',
            ),
        }
