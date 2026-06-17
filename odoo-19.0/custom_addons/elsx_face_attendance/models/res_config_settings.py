# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    elsx_face_attendance_enabled = fields.Boolean(
        string='Enable Face Attendance',
        config_parameter='elsx_face_attendance.enabled',
        default=False,
    )
    elsx_face_attendance_mode = fields.Selection([
        ('audit_only', 'Audit Only'),
        ('face_preferred', 'Face Preferred'),
        ('face_required', 'Face Required'),
        ('face_gps_ip_required', 'Face + GPS/IP Required'),
        ('high_assurance', 'High Assurance Verification'),
    ], string='Face Attendance Policy', default='audit_only', config_parameter='elsx_face_attendance.mode')
    elsx_face_attendance_sidecar_url = fields.Char(
        string='Face Sidecar URL',
        default='http://face_sidecar:8071',
        config_parameter='elsx_face_attendance.sidecar_url',
    )
    elsx_face_attendance_confidence_threshold = fields.Float(
        string='Confidence Threshold',
        default=0.78,
        config_parameter='elsx_face_attendance.confidence_threshold',
    )
    elsx_face_attendance_require_liveness = fields.Boolean(
        string='Require Liveness Result',
        default=False,
        config_parameter='elsx_face_attendance.require_liveness',
    )
    elsx_face_attendance_min_quality_score = fields.Float(
        string='Minimum Face Quality',
        default=0.52,
        config_parameter='elsx_face_attendance.min_quality_score',
    )
    elsx_face_attendance_min_samples = fields.Integer(
        string='Minimum Verification Samples',
        default=3,
        config_parameter='elsx_face_attendance.min_samples',
    )
    elsx_face_attendance_review_threshold = fields.Float(
        string='Manual Review Threshold',
        default=0.88,
        config_parameter='elsx_face_attendance.review_threshold',
    )
    elsx_face_attendance_require_device_fingerprint = fields.Boolean(
        string='Require Device Evidence',
        default=False,
        config_parameter='elsx_face_attendance.require_device_fingerprint',
    )
    elsx_face_attendance_debug_retention = fields.Boolean(
        string='Temporary Debug Image Retention',
        default=False,
        config_parameter='elsx_face_attendance.debug_retention',
    )

    def action_test_face_sidecar(self):
        return self.env['elsx.face.profile'].action_test_sidecar()
