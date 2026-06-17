# -*- coding: utf-8 -*-
import json
import logging

import requests
from cryptography.fernet import Fernet, InvalidToken

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ElsxFaceProfile(models.Model):
    _name = 'elsx.face.profile'
    _description = 'Face Attendance Profile'
    _order = 'employee_id, create_date desc'

    name = fields.Char(required=True, default=lambda self: _('Face Profile'))
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    active = fields.Boolean(default=True)
    consent_user_id = fields.Many2one('res.users', string='Consent Recorded By', readonly=True)
    consent_date = fields.Datetime(readonly=True)
    engine = fields.Char(readonly=True, default='local-opencv')
    quality_score = fields.Float(readonly=True)
    quality_status = fields.Char(readonly=True)
    sample_count = fields.Integer(readonly=True, default=1)
    embedding_payload = fields.Text(string='Encrypted Embedding', readonly=True)
    last_verified = fields.Datetime(readonly=True)
    verification_count = fields.Integer(readonly=True)
    notes = fields.Text()

    _sql_constraints = [
        ('employee_active_name_uniq', 'unique(employee_id, name)', 'Face profile name must be unique per employee.'),
    ]

    @api.model
    def _face_param(self, key, default=None):
        return self.env['ir.config_parameter'].sudo().get_param(key, default=default)

    @api.model
    def _face_enabled(self):
        return str(self._face_param('elsx_face_attendance.enabled', 'False')).lower() == 'true'

    @api.model
    def _face_mode(self):
        return self._face_param('elsx_face_attendance.mode', 'audit_only') or 'audit_only'

    @api.model
    def _confidence_threshold(self):
        value = self._face_param('elsx_face_attendance.confidence_threshold', '0.78')
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.78

    @api.model
    def _min_quality_score(self):
        value = self._face_param('elsx_face_attendance.min_quality_score', '0.52')
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.52

    @api.model
    def _min_samples(self):
        value = self._face_param('elsx_face_attendance.min_samples', '3')
        try:
            return max(1, min(int(value), 7))
        except (TypeError, ValueError):
            return 3

    @api.model
    def _review_threshold(self):
        value = self._face_param('elsx_face_attendance.review_threshold', '0.88')
        try:
            return max(self._confidence_threshold(), min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.88

    @api.model
    def _require_device_fingerprint(self):
        value = self._face_param('elsx_face_attendance.require_device_fingerprint', 'False')
        return str(value).lower() == 'true'

    @api.model
    def _sidecar_url(self):
        return (self._face_param('elsx_face_attendance.sidecar_url', 'http://face_sidecar:8071') or '').rstrip('/')

    @api.model
    def _encryption_key(self):
        params = self.env['ir.config_parameter'].sudo()
        key = params.get_param('elsx_face_attendance.encryption_key')
        if not key:
            key = Fernet.generate_key().decode('ascii')
            params.set_param('elsx_face_attendance.encryption_key', key)
        return key.encode('ascii')

    @api.model
    def _encrypt_embedding(self, embedding):
        payload = json.dumps(embedding or [], separators=(',', ':')).encode('utf-8')
        return Fernet(self._encryption_key()).encrypt(payload).decode('ascii')

    def _decrypt_embedding(self):
        self.ensure_one()
        if not self.embedding_payload:
            return []
        try:
            raw = Fernet(self._encryption_key()).decrypt(self.embedding_payload.encode('ascii'))
            return json.loads(raw.decode('utf-8'))
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
            _logger.warning('Could not decrypt face embedding for profile %s', self.id)
            return []

    @api.model
    def _call_sidecar(self, endpoint, payload, timeout=12):
        url = self._sidecar_url()
        if not url:
            raise UserError(_('Face sidecar URL is not configured.'))
        try:
            response = requests.post('%s/%s' % (url, endpoint.lstrip('/')), json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise UserError(_('Face sidecar is not reachable: %s') % exc) from exc
        except ValueError as exc:
            raise UserError(_('Face sidecar returned an invalid response.')) from exc
        if not data.get('ok'):
            raise UserError(data.get('error') or _('Face sidecar could not process the image.'))
        return data

    @api.model
    def action_test_sidecar(self):
        url = self._sidecar_url()
        try:
            response = requests.get('%s/health' % url, timeout=8)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise UserError(_('Face sidecar health check failed: %s') % exc) from exc
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Face Sidecar'),
                'message': _('Sidecar is reachable: %s') % data,
                'type': 'success',
            },
        }

    @api.model
    def enroll_from_image(self, employee, image_data, consent_user=None, images=None):
        employee = employee.sudo()
        if not employee:
            raise UserError(_('Employee is required for face enrollment.'))
        images = images or []
        if not image_data and not images:
            raise UserError(_('Camera image is required for face enrollment.'))
        data = self._call_sidecar('enroll', {'image': image_data, 'images': images})
        embedding = data.get('embedding') or []
        if not embedding:
            raise UserError(_('No usable face embedding was returned by the sidecar.'))
        profile = self.sudo().create({
            'name': _('Face Profile %s') % fields.Datetime.now(),
            'employee_id': employee.id,
            'consent_user_id': (consent_user or self.env.user).id,
            'consent_date': fields.Datetime.now(),
            'engine': data.get('engine') or 'local-opencv',
            'quality_score': data.get('quality') or 0.0,
            'quality_status': data.get('quality_status') or '',
            'sample_count': data.get('sample_count') or 1,
            'embedding_payload': self._encrypt_embedding(embedding),
        })
        return profile, data

    @api.model
    def verify_employee_image(self, employee, image_data, images=None):
        employee = employee.sudo()
        images = images or []
        profiles = self.sudo().search([
            ('employee_id', '=', employee.id),
            ('active', '=', True),
            ('embedding_payload', '!=', False),
        ])
        if not profiles:
            return {
                'verified': False,
                'confidence': 0.0,
                'reason': _('No active face profile is enrolled for this employee.'),
                'profile': False,
                'sidecar': {},
            }
        candidates = []
        for profile in profiles:
            embedding = profile._decrypt_embedding()
            if embedding:
                candidates.append({'id': profile.id, 'embedding': embedding})
        if not candidates:
            return {
                'verified': False,
                'confidence': 0.0,
                'reason': _('Enrolled face profiles could not be read.'),
                'profile': False,
                'sidecar': {},
            }
        data = self._call_sidecar('verify', {
            'image': image_data,
            'images': images,
            'candidates': candidates,
            'threshold': self._confidence_threshold(),
        })
        confidence = float(data.get('confidence') or 0.0)
        profile = self.sudo().browse(int(data.get('matched_id') or 0)).exists()
        verified = bool(profile and confidence >= self._confidence_threshold())
        reason = data.get('reason') or (_('Face verified.') if verified else _('Face confidence is below threshold.'))
        if profile and verified:
            profile.write({
                'last_verified': fields.Datetime.now(),
                'verification_count': profile.verification_count + 1,
            })
        return {
            'verified': verified,
            'confidence': confidence,
            'reason': reason,
            'profile': profile,
            'sidecar': data,
        }


class ElsxFaceVerificationLog(models.Model):
    _name = 'elsx.face.verification.log'
    _description = 'Face Attendance Verification Log'
    _order = 'create_date desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    profile_id = fields.Many2one('elsx.face.profile', ondelete='set null')
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null')
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('audit', 'Audit / Allowed'),
        ('failed', 'Failed'),
        ('blocked', 'Blocked'),
        ('error', 'Error'),
    ], default='audit', required=True, index=True)
    policy_mode = fields.Selection([
        ('audit_only', 'Audit Only'),
        ('face_preferred', 'Face Preferred'),
        ('face_required', 'Face Required'),
        ('face_gps_ip_required', 'Face + GPS/IP Required'),
        ('high_assurance', 'High Assurance Verification'),
    ], readonly=True)
    confidence = fields.Float(readonly=True)
    quality_score = fields.Float(readonly=True)
    quality_status = fields.Char(readonly=True)
    sample_count = fields.Integer(readonly=True)
    liveness_status = fields.Char(readonly=True)
    challenge_id = fields.Char(readonly=True)
    challenge_status = fields.Char(readonly=True)
    device_fingerprint_hash = fields.Char(readonly=True)
    risk_score = fields.Float(readonly=True)
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], readonly=True)
    decision = fields.Selection([
        ('allow', 'Allow'),
        ('audit', 'Audit'),
        ('review', 'Needs Review'),
        ('block', 'Block'),
    ], readonly=True)
    review_required = fields.Boolean(readonly=True)
    ip_address = fields.Char(readonly=True)
    latitude = fields.Float(readonly=True)
    longitude = fields.Float(readonly=True)
    reason = fields.Char(readonly=True)
    evidence_summary = fields.Text(readonly=True)
    raw_response = fields.Text(readonly=True)
