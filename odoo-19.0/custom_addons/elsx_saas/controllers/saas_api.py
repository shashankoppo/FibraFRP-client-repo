# -*- coding: utf-8 -*-
"""
ELSx SaaS API Services - Public endpoints for tenant API access
"""
import logging
import json
from datetime import datetime, timedelta

from odoo import http, _
from odoo.http import request
from odoo.addons.base.models.res_partner import _tz_get

_logger = logging.getLogger(__name__)


class SaaSAPIController(http.Controller):
    """Public REST API for SaaS tenant integration"""

    def _verify_token(self):
        """Verify API token from request header"""
        auth_header = request.httprequest.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return None, 'Missing or invalid Authorization header'

        token_key = auth_header.split(' ', 1)[1]
        request_ip = self._get_client_ip()

        try:
            token = request.env['elsx.saas.api.token'].verify_and_log(
                token_key,
                request_ip,
                request.httprequest.method,
                request.httprequest.path,
            )
            return token, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _get_client_ip():
        """Get client IP from request"""
        if request.httprequest.headers.get('X-Forwarded-For'):
            return request.httprequest.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.httprequest.remote_addr

    @http.route('/api/saas/v1/health', type='json', auth='public', methods=['GET'])
    def health_check(self):
        """Health check endpoint - no auth required"""
        try:
            return {
                'status': 'ok',
                'timestamp': datetime.now().isoformat(),
                'version': 'v1',
            }
        except Exception as e:
            _logger.error('Health check failed: %s' % str(e))
            return {'status': 'error', 'message': str(e)}

    @http.route('/api/saas/v1/tenant/info', type='json', auth='public', methods=['GET'])
    def tenant_info(self):
        """Get tenant information"""
        token, error = self._verify_token()
        if not token:
            return {'error': error}, 401

        try:
            tenant = token.tenant_id
            return {
                'tenant_id': tenant.id,
                'name': tenant.name,
                'database': tenant.db_name,
                'plan': tenant.plan,
                'health_status': tenant.health_status,
                'active': tenant.state == 'active',
                'max_users': tenant.max_users,
                'storage_quota_gb': tenant.storage_quota_gb,
                'enabled_modules': {
                    'crm': tenant.enable_crm,
                    'accounting': tenant.enable_accounting,
                    'whatsapp': tenant.enable_whatsapp,
                    'attendance': tenant.enable_attendance,
                    'tally': tenant.enable_tally,
                    'face_attendance': tenant.enable_face_attendance,
                },
            }
        except Exception as e:
            _logger.error('Tenant info failed: %s' % str(e))
            return {'error': str(e)}, 500

    @http.route('/api/saas/v1/tenant/usage', type='json', auth='public', methods=['GET'])
    def tenant_usage(self):
        """Get tenant usage metrics"""
        token, error = self._verify_token()
        if not token:
            return {'error': error}, 401

        try:
            tenant = token.tenant_id
            usage = request.env['elsx.saas.tenant.usage'].search(
                [('tenant_id', '=', tenant.id)],
                limit=1,
                order='usage_date desc'
            )

            if not usage:
                return {
                    'tenant_id': tenant.id,
                    'message': 'No usage data available yet',
                    'active_users': 0,
                    'used_storage_gb': 0,
                }

            return {
                'tenant_id': tenant.id,
                'usage_date': usage.usage_date.isoformat(),
                'active_users': usage.active_users,
                'total_users': usage.total_users,
                'user_limit_percentage': usage.user_limit_percentage,
                'used_storage_gb': usage.used_storage_gb,
                'storage_limit_percentage': usage.storage_limit_percentage,
                'api_requests': usage.api_requests_count,
                'backup_status': usage.backup_status,
            }
        except Exception as e:
            _logger.error('Usage fetch failed: %s' % str(e))
            return {'error': str(e)}, 500

    @http.route('/api/saas/v1/tenant/health', type='json', auth='public', methods=['GET'])
    def tenant_health(self):
        """Get latest health check"""
        token, error = self._verify_token()
        if not token:
            return {'error': error}, 401

        try:
            tenant = token.tenant_id
            health = request.env['elsx.saas.health.check'].search(
                [('tenant_id', '=', tenant.id)],
                limit=1,
                order='check_date desc'
            )

            if not health:
                return {
                    'tenant_id': tenant.id,
                    'message': 'No health check data available yet',
                    'status': 'unknown',
                }

            return {
                'tenant_id': tenant.id,
                'check_date': health.check_date.isoformat(),
                'status': health.overall_status,
                'reachable': health.is_reachable,
                'response_time_ms': health.response_time_ms,
                'database_ok': health.db_reachable,
                'storage': health.filestore_status,
                'modules_ok': health.critical_modules_active,
                'has_alerts': health.has_alerts,
                'alert_message': health.alert_message,
            }
        except Exception as e:
            _logger.error('Health fetch failed: %s' % str(e))
            return {'error': str(e)}, 500

    @http.route('/api/saas/v1/tenant/metrics', type='json', auth='public', methods=['GET'])
    def tenant_metrics(self):
        """Get tenant performance metrics"""
        token, error = self._verify_token()
        if not token:
            return {'error': error}, 401

        try:
            tenant = token.tenant_id

            # Get last 7 days of usage
            usage_list = request.env['elsx.saas.tenant.usage'].search(
                [('tenant_id', '=', tenant.id)],
                limit=7,
                order='usage_date desc'
            )

            metrics = []
            for usage in usage_list:
                metrics.append({
                    'date': usage.usage_date.isoformat(),
                    'active_users': usage.active_users,
                    'storage_gb': usage.used_storage_gb,
                    'api_requests': usage.api_requests_count,
                    'crm_records': usage.crm_records_created,
                    'invoices': usage.invoices_generated,
                })

            return {
                'tenant_id': tenant.id,
                'metrics': metrics,
            }
        except Exception as e:
            _logger.error('Metrics fetch failed: %s' % str(e))
            return {'error': str(e)}, 500

    @http.route('/api/saas/v1/webhook/test', type='json', auth='public', methods=['POST'])
    def webhook_test(self):
        """Test webhook delivery"""
        token, error = self._verify_token()
        if not token:
            return {'error': error}, 401

        try:
            data = json.loads(request.httprequest.data)
            webhook_url = data.get('webhook_url')

            if not webhook_url:
                return {'error': 'webhook_url required'}, 400

            # Create test webhook event
            event = request.env['elsx.saas.webhook.event'].create({
                'tenant_id': token.tenant_id.id,
                'event_type': 'custom',
                'payload': {'test': True, 'timestamp': datetime.now().isoformat()},
                'webhook_url': webhook_url,
            })

            return {
                'event_id': event.id,
                'status': event.delivery_status,
                'message': 'Webhook test event created',
            }
        except Exception as e:
            _logger.error('Webhook test failed: %s' % str(e))
            return {'error': str(e)}, 500
