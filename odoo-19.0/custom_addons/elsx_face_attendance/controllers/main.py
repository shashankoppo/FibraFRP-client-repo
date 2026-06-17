# -*- coding: utf-8 -*-
import hashlib
import json
import logging
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons.hr_attendance.controllers.main import HrAttendance as BaseHrAttendance

_logger = logging.getLogger(__name__)


def _client_ip():
    headers = request.httprequest.headers
    for key in ('CF-Connecting-IP', 'True-Client-IP', 'X-Real-IP', 'X-Forwarded-For'):
        value = headers.get(key)
        if value:
            return value.split(',')[0].strip()
    return request.httprequest.remote_addr


def _hash_evidence(value):
    if not value:
        return ''
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _add_query_params(url, **params):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, False, '')})
    return urlunparse(parsed._replace(query=urlencode(query)))


def _risk_level(score):
    if score >= 75:
        return 'critical'
    if score >= 50:
        return 'high'
    if score >= 25:
        return 'medium'
    return 'low'


class ElsxFaceAttendanceController(http.Controller):

    def _company_from_token(self, token):
        return request.env['res.company'].sudo().search([('attendance_kiosk_key', '=', token)], limit=1)

    def _employee_for_user(self):
        employee = request.env.user.employee_id
        if not employee:
            employee = request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)], limit=1)
        return employee

    def _can_manage_face_attendance(self):
        user = request.env.user
        return (
            user.has_group('hr_attendance.group_hr_attendance_manager')
            or user.has_group('hr_attendance.group_hr_attendance_officer')
            or user.has_group('base.group_system')
        )

    def _face_policy_payload(self, FaceProfile):
        mode = FaceProfile._face_mode()
        return {
            'mode': mode,
            'high_assurance': mode == 'high_assurance',
            'threshold': FaceProfile._confidence_threshold(),
            'min_quality': FaceProfile._min_quality_score(),
            'min_samples': FaceProfile._min_samples(),
            'review_threshold': FaceProfile._review_threshold(),
            'require_device_fingerprint': FaceProfile._require_device_fingerprint() or mode == 'high_assurance',
        }

    def _issue_challenge(self, FaceProfile, enrollment=False):
        challenge_id = secrets.token_urlsafe(18)
        high = FaceProfile._face_mode() == 'high_assurance'
        prompts = [
            _('Look straight at the camera'),
            _('Turn your face slightly left'),
            _('Turn your face slightly right'),
            _('Blink once, then hold still'),
            _('Re-center and hold steady'),
        ] if high else [
            _('Hold steady for sample 1'),
            _('Hold steady for sample 2'),
            _('Hold steady for sample 3'),
        ]
        required = max(FaceProfile._min_samples(), 5 if enrollment else 3)
        sample_count = min(7 if enrollment else 5, max(required, len(prompts)))
        request.session['elsx_face_challenge'] = {
            'id': challenge_id,
            'created_at': time.time(),
            'sample_count': sample_count,
        }
        return {
            'ok': True,
            'challenge_id': challenge_id,
            'prompts': [str(item) for item in prompts],
            'sample_count': sample_count,
        }

    def _validate_challenge(self, challenge_id=False, challenge_status=False):
        challenge = request.session.get('elsx_face_challenge') or {}
        if not challenge_id or challenge.get('id') != challenge_id:
            return 'missing'
        created_at = float(challenge.get('created_at') or 0.0)
        if not created_at or time.time() - created_at > 180:
            return 'expired'
        return 'passed' if challenge_status == 'passed' else (challenge_status or 'incomplete')

    def _assess_verification(
        self,
        FaceProfile,
        mode,
        verification,
        gps_present=False,
        device_fingerprint=False,
        challenge_status=False,
    ):
        sidecar = verification.get('sidecar') or {}
        confidence = float(verification.get('confidence') or 0.0)
        quality = float(sidecar.get('quality') or 0.0)
        sample_count = int(sidecar.get('sample_count') or 0)
        liveness_status = sidecar.get('liveness_status') or 'not_checked'
        warnings = sidecar.get('warnings') or []
        face_ok = bool(verification.get('verified'))
        min_quality = FaceProfile._min_quality_score()
        min_samples = FaceProfile._min_samples()
        review_threshold = FaceProfile._review_threshold()
        require_device = FaceProfile._require_device_fingerprint() or mode == 'high_assurance'
        require_liveness = (
            mode == 'high_assurance'
            or str(
                request.env['ir.config_parameter'].sudo().get_param(
                    'elsx_face_attendance.require_liveness',
                    'False',
                )
            ).lower() == 'true'
        )

        risks = []
        blocked = []
        score = 0.0
        if not face_ok:
            score += 45
            risks.append(_('face match failed'))
        elif confidence < review_threshold:
            score += max(4.0, (review_threshold - confidence) * 85.0)
            risks.append(_('confidence below manual review threshold'))
        if require_liveness and liveness_status != 'passed':
            score += 22
            risks.append(_('liveness/passive motion did not pass'))
        if quality < min_quality:
            score += 18
            risks.append(_('capture quality below policy minimum'))
        if sample_count < min_samples:
            score += 14
            risks.append(_('not enough verification samples'))
        if mode in ('face_gps_ip_required', 'high_assurance') and not gps_present:
            score += 16
            risks.append(_('GPS evidence missing'))
        if require_device and not device_fingerprint:
            score += 10
            risks.append(_('device evidence missing'))
        if mode == 'high_assurance' and challenge_status != 'passed':
            score += 16
            risks.append(_('operator challenge did not complete'))
        if warnings:
            score += min(12, len(warnings) * 4)

        if mode in ('face_required', 'face_gps_ip_required', 'high_assurance') and not face_ok:
            blocked.append(verification.get('reason') or _('Face verification is required.'))
        if require_liveness and liveness_status != 'passed':
            blocked.append(_('Face liveness verification is required by policy.'))
        if mode in ('face_gps_ip_required', 'high_assurance') and not gps_present:
            blocked.append(_('This policy requires browser location permission.'))
        if mode == 'high_assurance':
            if quality < min_quality:
                blocked.append(_('Face capture quality is below the high-assurance minimum.'))
            if sample_count < min_samples:
                blocked.append(_('High-assurance verification needs more face samples.'))
            if challenge_status != 'passed':
                blocked.append(_('High-assurance challenge was not completed.'))
            if require_device and not device_fingerprint:
                blocked.append(_('High-assurance verification requires device evidence.'))

        score = min(100.0, max(0.0, score))
        level = _risk_level(score)
        review_required = bool(score >= 25 or (face_ok and confidence < review_threshold) or warnings)
        decision = 'block' if blocked else 'review' if review_required else 'allow' if face_ok else 'audit'
        evidence = [
            _('confidence %.1f%%') % (confidence * 100.0),
            _('quality %.1f%%') % (quality * 100.0),
            _('samples %s') % sample_count,
            _('liveness %s') % liveness_status,
            _('gps %s') % (_('present') if gps_present else _('missing')),
            _('device %s') % (_('present') if device_fingerprint else _('missing')),
            _('challenge %s') % (challenge_status or _('not sent')),
            _('risk %s %.0f') % (level, score),
        ]
        if risks:
            evidence.append(_('flags: %s') % ', '.join([str(item) for item in risks[:5]]))
        return {
            'blocked_reason': blocked[0] if blocked else False,
            'risk_score': score,
            'risk_level': level,
            'decision': decision,
            'review_required': review_required,
            'evidence_summary': ' | '.join([str(item) for item in evidence]),
            'quality': quality,
            'quality_status': sidecar.get('quality_status') or '',
            'sample_count': sample_count,
            'liveness_status': liveness_status,
            'warnings': warnings,
        }

    @http.route('/elsx_face_attendance/challenge', type='jsonrpc', auth='public')
    def face_attendance_challenge(self, token=False, enrollment=False):
        if token:
            if not self._company_from_token(token):
                return {'ok': False, 'error': _('Attendance kiosk token is invalid.')}
        elif not request.session.uid:
            return {'ok': False, 'error': _('Please sign in before starting face verification.')}
        FaceProfile = request.env['elsx.face.profile'].sudo()
        return self._issue_challenge(FaceProfile, enrollment=bool(enrollment))

    @http.route('/elsx_face_attendance/scan', type='jsonrpc', auth='public')
    def face_attendance_scan(self, token=False, image=False):
        if token:
            if not self._company_from_token(token):
                return {'ok': False, 'error': _('Attendance kiosk token is invalid.')}
        elif not request.session.uid:
            return {'ok': False, 'error': _('Please sign in before scanning face attendance.')}
        if not image:
            return {'ok': False, 'error': _('Camera image is required for room/person scan.')}
        FaceProfile = request.env['elsx.face.profile'].sudo()
        try:
            data = FaceProfile._call_sidecar('scan', {'image': image}, timeout=8)
        except UserError as exc:
            return {'ok': False, 'error': exc.args[0]}
        except Exception as exc:
            _logger.exception('Face scan failed')
            return {'ok': False, 'error': _('Face scan failed: %s') % exc}
        return {
            'ok': True,
            'engine': data.get('engine'),
            'face_count': data.get('face_count') or 0,
            'quality': data.get('quality') or 0.0,
            'quality_status': data.get('quality_status') or '',
            'scan_status': data.get('scan_status') or '',
            'warnings': data.get('warnings') or [],
            'metrics': data.get('metrics') or {},
            'face_box': data.get('face_box') or [],
            'alignment': data.get('alignment') or {},
        }

    @http.route('/elsx_face_attendance', type='http', auth='user')
    def face_attendance_page(self, **kwargs):
        return request.render('elsx_face_attendance.face_attendance_page', {
            'employee': self._employee_for_user(),
            'can_manage': self._can_manage_face_attendance(),
        })

    @http.route('/elsx_face_attendance/kiosk/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def face_attendance_kiosk_page(self, token, from_trial_mode=False, **kwargs):
        company = self._company_from_token(token)
        if not company:
            return request.not_found()
        back_url = '/hr_attendance/%s' % token
        db_name = request.params.get('db') or request.env.cr.dbname
        back_url = _add_query_params(back_url, db=db_name, from_trial_mode=from_trial_mode)
        return request.render('elsx_face_attendance.face_attendance_kiosk_page', {
            'token': token,
            'company': company,
            'back_url': back_url,
        })

    @http.route('/elsx_face_attendance/status', type='jsonrpc', auth='user')
    def face_attendance_status(self):
        FaceProfile = request.env['elsx.face.profile'].sudo()
        employee = self._employee_for_user()
        enabled = FaceProfile._face_enabled()
        policy = self._face_policy_payload(FaceProfile)
        return {
            'ok': True,
            'enabled': enabled,
            **policy,
            'employee_id': employee.id if employee else False,
            'employee_name': employee.name if employee else '',
            'attendance_state': employee.sudo().attendance_state if employee else 'checked_out',
            'face_enrolled': bool(employee and employee.sudo().elsx_face_enrolled),
            'can_manage': self._can_manage_face_attendance(),
        }

    @http.route('/elsx_face_attendance/kiosk/status', type='jsonrpc', auth='public')
    def face_attendance_kiosk_status(self, token=False):
        company = self._company_from_token(token)
        if not company:
            return {'ok': False, 'error': _('Attendance kiosk token is invalid.')}
        FaceProfile = request.env['elsx.face.profile'].sudo()
        enrolled_count = FaceProfile.search_count([
            ('employee_id.company_id', '=', company.id),
            ('active', '=', True),
            ('embedding_payload', '!=', False),
        ])
        return {
            'ok': True,
            'enabled': FaceProfile._face_enabled(),
            **self._face_policy_payload(FaceProfile),
            'company_id': company.id,
            'company_name': company.name,
            'enrolled_count': enrolled_count,
        }

    @http.route('/elsx_face_attendance/enroll', type='jsonrpc', auth='user')
    def face_attendance_enroll(self, employee_id=False, image=False, images=False):
        if not self._can_manage_face_attendance():
            return {'ok': False, 'error': _('Only attendance managers can enroll employee faces.')}
        employee = request.env['hr.employee'].sudo().browse(int(employee_id or 0)).exists()
        if not employee:
            current_employee = self._employee_for_user()
            employee = current_employee.sudo() if current_employee else False
        if not employee:
            return {'ok': False, 'error': _('No employee is linked to this user.')}
        try:
            profile, data = request.env['elsx.face.profile'].sudo().enroll_from_image(
                employee,
                image,
                consent_user=request.env.user,
                images=images or [],
            )
        except UserError as exc:
            return {'ok': False, 'error': exc.args[0]}
        except Exception as exc:
            _logger.exception('Face enrollment failed')
            return {'ok': False, 'error': _('Face enrollment failed: %s') % exc}
        return {
            'ok': True,
            'profile_id': profile.id,
            'quality': profile.quality_score,
            'quality_status': profile.quality_status,
            'sample_count': profile.sample_count,
            'message': _('Face profile enrolled for %s.') % employee.name,
            'sidecar': {
                'face_count': data.get('face_count'),
                'engine': data.get('engine'),
                'liveness_status': data.get('liveness_status'),
                'warnings': data.get('warnings') or [],
            },
        }

    @http.route('/elsx_face_attendance/check', type='jsonrpc', auth='user')
    def face_attendance_check(
        self,
        image=False,
        images=False,
        latitude=False,
        longitude=False,
        device_fingerprint=False,
        challenge_id=False,
        challenge_status=False,
    ):
        FaceProfile = request.env['elsx.face.profile'].sudo()
        Log = request.env['elsx.face.verification.log'].sudo()
        employee = self._employee_for_user()
        if not employee:
            return {'ok': False, 'error': _('No employee is linked to this user.')}
        if not FaceProfile._face_enabled():
            return {'ok': False, 'error': _('Face attendance is installed but not enabled by an administrator.')}
        mode = FaceProfile._face_mode()
        ip_address = _client_ip()
        verification = {
            'verified': False,
            'confidence': 0.0,
            'reason': _('Face verification was not completed.'),
            'profile': False,
            'sidecar': {},
        }
        try:
            verification = FaceProfile.verify_employee_image(employee, image, images=images or [])
        except UserError as exc:
            verification['reason'] = exc.args[0]
            verification['sidecar'] = {'error': exc.args[0]}
        except Exception as exc:
            _logger.exception('Face verification failed')
            verification['reason'] = _('Face verification failed: %s') % exc
            verification['sidecar'] = {'error': str(exc)}

        face_ok = bool(verification.get('verified'))
        gps_present = latitude not in (False, None, '') and longitude not in (False, None, '')
        challenge_status = self._validate_challenge(challenge_id, challenge_status)
        assessment = self._assess_verification(
            FaceProfile,
            mode,
            verification,
            gps_present=gps_present,
            device_fingerprint=device_fingerprint,
            challenge_status=challenge_status,
        )
        blocked_reason = assessment['blocked_reason']
        liveness_status = assessment['liveness_status']

        status = 'success' if face_ok else 'audit'
        if blocked_reason:
            status = 'blocked'

        log = Log.create({
            'employee_id': employee.id,
            'profile_id': verification.get('profile').id if verification.get('profile') else False,
            'status': status,
            'policy_mode': mode,
            'confidence': verification.get('confidence') or 0.0,
            'quality_score': assessment['quality'],
            'quality_status': assessment['quality_status'],
            'sample_count': assessment['sample_count'],
            'liveness_status': liveness_status,
            'challenge_id': challenge_id,
            'challenge_status': challenge_status,
            'device_fingerprint_hash': _hash_evidence(device_fingerprint),
            'risk_score': assessment['risk_score'],
            'risk_level': assessment['risk_level'],
            'decision': assessment['decision'],
            'review_required': assessment['review_required'],
            'ip_address': ip_address,
            'latitude': float(latitude or 0.0) if gps_present else 0.0,
            'longitude': float(longitude or 0.0) if gps_present else 0.0,
            'reason': blocked_reason or verification.get('reason'),
            'evidence_summary': assessment['evidence_summary'],
            'raw_response': json.dumps(verification.get('sidecar') or {}, default=str),
        })
        if blocked_reason:
            return {
                'ok': False,
                'blocked': True,
                'error': blocked_reason,
                'confidence': verification.get('confidence') or 0.0,
                'liveness_status': liveness_status,
                'quality': assessment['quality'],
                'quality_status': assessment['quality_status'],
                'sample_count': assessment['sample_count'],
                'risk_score': assessment['risk_score'],
                'risk_level': assessment['risk_level'],
                'decision': assessment['decision'],
                'review_required': assessment['review_required'],
                'evidence_summary': assessment['evidence_summary'],
                'warnings': assessment['warnings'],
                'log_id': log.id,
            }

        geo = {
            'mode': 'systray',
            'ip_address': ip_address,
            'browser': (request.httprequest.user_agent.browser or request.httprequest.user_agent.string or 'Unknown')[:128],
            'location': _('Face Attendance'),
        }
        if gps_present:
            geo.update({
                'latitude': float(latitude),
                'longitude': float(longitude),
            })
        try:
            attendance = employee.sudo()._attendance_action_change(geo)
            attendance.sudo().write({
                'elsx_face_verified': face_ok,
                'elsx_face_confidence': verification.get('confidence') or 0.0,
                'elsx_face_verification_id': log.id,
                'elsx_face_policy_mode': mode,
                'elsx_face_liveness_status': liveness_status,
                'elsx_face_risk_level': assessment['risk_level'],
                'elsx_face_risk_score': assessment['risk_score'],
                'elsx_face_review_required': assessment['review_required'],
                'elsx_face_decision': assessment['decision'],
                'elsx_face_failure_reason': False if face_ok else verification.get('reason'),
            })
            log.write({'attendance_id': attendance.id})
        except Exception as exc:
            log.write({'status': 'error', 'reason': str(exc)})
            _logger.exception('Face attendance check-in/out failed')
            return {'ok': False, 'error': _('Attendance could not be updated: %s') % exc, 'log_id': log.id}

        return {
            'ok': True,
            'attendance_id': attendance.id,
            'attendance_state': employee.sudo().attendance_state,
            'verified': face_ok,
            'confidence': verification.get('confidence') or 0.0,
            'liveness_status': liveness_status,
            'quality': assessment['quality'],
            'quality_status': assessment['quality_status'],
            'sample_count': assessment['sample_count'],
            'risk_score': assessment['risk_score'],
            'risk_level': assessment['risk_level'],
            'decision': assessment['decision'],
            'review_required': assessment['review_required'],
            'evidence_summary': assessment['evidence_summary'],
            'warnings': assessment['warnings'],
            'message': _('Attendance updated for %s.') % employee.name,
            'log_id': log.id,
        }

    @http.route('/elsx_face_attendance/kiosk/check', type='jsonrpc', auth='public')
    def face_attendance_kiosk_check(
        self,
        token=False,
        image=False,
        images=False,
        latitude=False,
        longitude=False,
        device_fingerprint=False,
        challenge_id=False,
        challenge_status=False,
    ):
        company = self._company_from_token(token)
        if not company:
            return {'ok': False, 'error': _('Attendance kiosk token is invalid.')}
        FaceProfile = request.env['elsx.face.profile'].sudo()
        Log = request.env['elsx.face.verification.log'].sudo()
        if not FaceProfile._face_enabled():
            return {'ok': False, 'error': _('Face attendance is installed but not enabled by an administrator.')}
        images = images or []
        if not image and not images:
            return {'ok': False, 'error': _('Camera image is required for Face ID attendance.')}

        profiles = FaceProfile.search([
            ('employee_id.company_id', '=', company.id),
            ('active', '=', True),
            ('embedding_payload', '!=', False),
        ])
        candidates = []
        for profile in profiles:
            embedding = profile._decrypt_embedding()
            if embedding:
                candidates.append({'id': profile.id, 'embedding': embedding})
        if not candidates:
            return {'ok': False, 'error': _('No enrolled face profiles are available for this company.')}

        mode = FaceProfile._face_mode()
        gps_present = latitude not in (False, None, '') and longitude not in (False, None, '')
        try:
            sidecar = FaceProfile._call_sidecar('verify', {
                'image': image,
                'images': images,
                'candidates': candidates,
                'threshold': FaceProfile._confidence_threshold(),
            })
        except UserError as exc:
            return {'ok': False, 'error': exc.args[0]}
        except Exception as exc:
            _logger.exception('Public kiosk face verification failed')
            return {'ok': False, 'error': _('Face verification failed: %s') % exc}

        confidence = float(sidecar.get('confidence') or 0.0)
        profile = FaceProfile.browse(int(sidecar.get('matched_id') or 0)).exists()
        face_ok = bool(profile and confidence >= FaceProfile._confidence_threshold())
        employee = profile.employee_id if profile else False
        verification = {
            'verified': face_ok,
            'confidence': confidence,
            'reason': sidecar.get('reason') or _('Face could not be matched to an enrolled employee.'),
            'profile': profile,
            'sidecar': sidecar,
        }
        challenge_status = self._validate_challenge(challenge_id, challenge_status)
        assessment = self._assess_verification(
            FaceProfile,
            mode,
            verification,
            gps_present=gps_present,
            device_fingerprint=device_fingerprint,
            challenge_status=challenge_status,
        )
        blocked_reason = assessment['blocked_reason']
        if not employee:
            blocked_reason = sidecar.get('reason') or _('Face could not be matched to an enrolled employee.')
        liveness_status = assessment['liveness_status']

        log = False
        if employee:
            log = Log.create({
                'employee_id': employee.id,
                'profile_id': profile.id if profile else False,
                'status': 'blocked' if blocked_reason else 'success',
                'policy_mode': mode,
                'confidence': confidence,
                'quality_score': assessment['quality'],
                'quality_status': assessment['quality_status'],
                'sample_count': assessment['sample_count'],
                'liveness_status': liveness_status,
                'challenge_id': challenge_id,
                'challenge_status': challenge_status,
                'device_fingerprint_hash': _hash_evidence(device_fingerprint),
                'risk_score': assessment['risk_score'],
                'risk_level': assessment['risk_level'],
                'decision': assessment['decision'],
                'review_required': assessment['review_required'],
                'ip_address': _client_ip(),
                'latitude': float(latitude or 0.0) if gps_present else 0.0,
                'longitude': float(longitude or 0.0) if gps_present else 0.0,
                'reason': blocked_reason or sidecar.get('reason'),
                'evidence_summary': assessment['evidence_summary'],
                'raw_response': json.dumps(sidecar or {}, default=str),
            })
        if blocked_reason:
            return {
                'ok': False,
                'blocked': True,
                'error': blocked_reason,
                'confidence': confidence,
                'liveness_status': liveness_status,
                'quality': assessment['quality'],
                'quality_status': assessment['quality_status'],
                'sample_count': assessment['sample_count'],
                'risk_score': assessment['risk_score'],
                'risk_level': assessment['risk_level'],
                'decision': assessment['decision'],
                'review_required': assessment['review_required'],
                'evidence_summary': assessment['evidence_summary'],
                'warnings': assessment['warnings'],
                'log_id': log.id if log else False,
            }

        if profile:
            profile.write({
                'last_verified': fields.Datetime.now(),
                'verification_count': profile.verification_count + 1,
            })

        geo = BaseHrAttendance._get_geoip_response(
            'kiosk',
            latitude=latitude,
            longitude=longitude,
            device_tracking_enabled=company.attendance_device_tracking,
        )
        try:
            attendance = employee.sudo()._attendance_action_change(geo)
            attendance.sudo().write({
                'elsx_face_verified': True,
                'elsx_face_confidence': confidence,
                'elsx_face_verification_id': log.id if log else False,
                'elsx_face_policy_mode': mode,
                'elsx_face_liveness_status': liveness_status,
                'elsx_face_risk_level': assessment['risk_level'],
                'elsx_face_risk_score': assessment['risk_score'],
                'elsx_face_review_required': assessment['review_required'],
                'elsx_face_decision': assessment['decision'],
                'elsx_face_failure_reason': False,
            })
            if log:
                log.write({'attendance_id': attendance.id})
        except Exception as exc:
            if log:
                log.write({'status': 'error', 'reason': str(exc)})
            _logger.exception('Public kiosk face attendance check-in/out failed')
            return {'ok': False, 'error': _('Attendance could not be updated: %s') % exc, 'log_id': log.id if log else False}

        return {
            'ok': True,
            'attendance_id': attendance.id,
            'attendance_state': employee.sudo().attendance_state,
            'employee_id': employee.id,
            'employee_name': employee.name,
            'verified': True,
            'confidence': confidence,
            'liveness_status': liveness_status,
            'quality': assessment['quality'],
            'quality_status': assessment['quality_status'],
            'sample_count': assessment['sample_count'],
            'risk_score': assessment['risk_score'],
            'risk_level': assessment['risk_level'],
            'decision': assessment['decision'],
            'review_required': assessment['review_required'],
            'evidence_summary': assessment['evidence_summary'],
            'warnings': assessment['warnings'],
            'message': _('Attendance updated.'),
            'log_id': log.id if log else False,
        }
