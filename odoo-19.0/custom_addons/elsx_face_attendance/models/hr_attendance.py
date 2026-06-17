# -*- coding: utf-8 -*-
from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    elsx_face_verified = fields.Boolean(string='Face Verified', readonly=True)
    elsx_face_confidence = fields.Float(string='Face Confidence', readonly=True)
    elsx_face_verification_id = fields.Many2one(
        'elsx.face.verification.log',
        string='Face Verification',
        readonly=True,
        ondelete='set null',
    )
    elsx_face_policy_mode = fields.Selection([
        ('audit_only', 'Audit Only'),
        ('face_preferred', 'Face Preferred'),
        ('face_required', 'Face Required'),
        ('face_gps_ip_required', 'Face + GPS/IP Required'),
        ('high_assurance', 'High Assurance Verification'),
    ], string='Face Policy', readonly=True)
    elsx_face_liveness_status = fields.Char(string='Face Liveness', readonly=True)
    elsx_face_risk_level = fields.Char(string='Face Risk Level', readonly=True)
    elsx_face_risk_score = fields.Float(string='Face Risk Score', readonly=True)
    elsx_face_review_required = fields.Boolean(string='Face Review Required', readonly=True)
    elsx_face_decision = fields.Char(string='Face Decision', readonly=True)
    elsx_face_failure_reason = fields.Char(string='Face Verification Note', readonly=True)
