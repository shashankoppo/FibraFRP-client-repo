# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ELSXSaasTenantUsage(models.Model):
    _name = 'elsx.saas.tenant.usage'
    _description = 'ELSx SaaS Tenant Usage Metrics'
    _order = 'usage_date desc, tenant_id'

    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade')
    usage_date = fields.Date(default=fields.Date.today)

    # User metrics
    active_users = fields.Integer('Active Users', help='Number of users who logged in on this date')
    total_users = fields.Integer('Total Users Provisioned')
    user_limit = fields.Integer(related='tenant_id.max_users', readonly=True)
    user_limit_percentage = fields.Float(compute='_compute_user_percentage')

    # Storage metrics
    used_storage_gb = fields.Float('Used Storage (GB)')
    allocated_storage_gb = fields.Integer(related='tenant_id.storage_quota_gb', readonly=True)
    storage_limit_percentage = fields.Float(compute='_compute_storage_percentage')

    # Feature usage
    crm_records_created = fields.Integer('CRM Records Created')
    invoices_generated = fields.Integer('Invoices Generated')
    attendance_entries = fields.Integer('Attendance Entries')
    whatsapp_messages_sent = fields.Integer('WhatsApp Messages Sent')

    # Performance metrics
    api_requests_count = fields.Integer('API Requests')
    error_requests_count = fields.Integer('Error Requests')
    slow_requests_count = fields.Integer('Slow Requests (>2s)')
    avg_response_time_ms = fields.Float('Avg Response Time (ms)')

    # System health
    database_size_mb = fields.Float('Database Size (MB)')
    backup_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('failed', 'Failed'),
    ], default='unknown')
    last_backup_time = fields.Datetime()

    notes = fields.Text()

    _sql_constraints = [
        ('unique_usage_date', 'unique(tenant_id, usage_date)', 'Usage metrics are recorded once per tenant per day.'),
    ]

    @api.depends('active_users', 'user_limit')
    def _compute_user_percentage(self):
        for record in self:
            if record.user_limit and record.active_users:
                record.user_limit_percentage = (record.active_users / record.user_limit) * 100
            else:
                record.user_limit_percentage = 0

    @api.depends('used_storage_gb', 'allocated_storage_gb')
    def _compute_storage_percentage(self):
        for record in self:
            if record.allocated_storage_gb and record.used_storage_gb:
                record.storage_limit_percentage = (record.used_storage_gb / record.allocated_storage_gb) * 100
            else:
                record.storage_limit_percentage = 0


class ELSXSaasHealthCheck(models.Model):
    _name = 'elsx.saas.health.check'
    _description = 'ELSx SaaS Tenant Health Check Log'
    _order = 'check_date desc'

    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade')
    check_date = fields.Datetime(default=fields.Datetime.now)

    # Availability checks
    http_status = fields.Integer('HTTP Status Code')
    is_reachable = fields.Boolean()
    response_time_ms = fields.Float('Response Time (ms)')

    # Database checks
    db_reachable = fields.Boolean('Database Reachable')
    db_connection_time_ms = fields.Float('DB Connection Time (ms)')

    # Storage checks
    filestore_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('ok', 'OK'),
        ('warning', 'Low Space'),
        ('critical', 'Critical'),
    ], default='unknown')

    # Module checks
    critical_modules_active = fields.Boolean('All Critical Modules Active')
    failed_modules = fields.Char('Failed Modules (comma-separated)')

    # Overall status
    overall_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('ok', 'Healthy'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ], default='unknown')

    # Alerts and notifications
    has_alerts = fields.Boolean()
    alert_message = fields.Text()

    # Check details
    check_result = fields.Text('Detailed Check Result')
    error_details = fields.Text('Error Details (if any)')

    @api.model
    def record_health_check(self, tenant_id, status_dict):
        """Record a health check result."""
        vals = {
            'tenant_id': tenant_id,
            'check_date': fields.Datetime.now(),
            'http_status': status_dict.get('http_status'),
            'is_reachable': status_dict.get('is_reachable', False),
            'response_time_ms': status_dict.get('response_time_ms'),
            'db_reachable': status_dict.get('db_reachable', False),
            'db_connection_time_ms': status_dict.get('db_connection_time_ms'),
            'filestore_status': status_dict.get('filestore_status', 'unknown'),
            'critical_modules_active': status_dict.get('critical_modules_active', False),
            'failed_modules': status_dict.get('failed_modules', ''),
            'overall_status': status_dict.get('overall_status', 'unknown'),
            'has_alerts': status_dict.get('has_alerts', False),
            'alert_message': status_dict.get('alert_message', ''),
            'check_result': status_dict.get('check_result', ''),
            'error_details': status_dict.get('error_details', ''),
        }

        check = self.create(vals)

        # Update tenant health status
        tenant = self.env['elsx.saas.tenant'].browse(tenant_id)
        tenant.write({
            'health_status': status_dict.get('overall_status', 'unknown'),
            'last_health_check': fields.Datetime.now(),
        })

        return check


class ELSXSaasWebhookEvent(models.Model):
    _name = 'elsx.saas.webhook.event'
    _description = 'ELSx SaaS Webhook Event Log'
    _order = 'create_date desc'

    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade')

    event_type = fields.Selection([
        ('tenant_created', 'Tenant Created'),
        ('tenant_activated', 'Tenant Activated'),
        ('tenant_suspended', 'Tenant Suspended'),
        ('tenant_deleted', 'Tenant Deleted'),
        ('module_installed', 'Module Installed'),
        ('module_failed', 'Module Installation Failed'),
        ('user_created', 'User Created'),
        ('user_deleted', 'User Deleted'),
        ('backup_completed', 'Backup Completed'),
        ('backup_failed', 'Backup Failed'),
        ('health_alert', 'Health Alert'),
        ('payment_due', 'Payment Due'),
        ('payment_failed', 'Payment Failed'),
        ('storage_exceeded', 'Storage Exceeded'),
        ('custom', 'Custom Event'),
    ], required=True)

    event_timestamp = fields.Datetime(default=fields.Datetime.now)

    # Webhook destination
    webhook_url = fields.Char('Webhook URL')

    # Event payload
    payload = fields.Json('Event Payload')

    # Delivery status
    delivery_status = fields.Selection([
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ], default='pending')

    delivery_timestamp = fields.Datetime()
    http_status_code = fields.Integer()
    delivery_attempts = fields.Integer(default=0)
    max_delivery_attempts = fields.Integer(default=5)

    response_body = fields.Text('HTTP Response Body')
    error_message = fields.Text()

    @api.model
    def trigger_webhook(self, tenant_id, event_type, payload, webhook_url=None):
        """Trigger a webhook event."""
        if not webhook_url:
            # Try to get webhook URL from tenant config
            tenant = self.env['elsx.saas.tenant'].browse(tenant_id)
            webhook_url = tenant.webhook_url if hasattr(tenant, 'webhook_url') else None

        event = self.create({
            'tenant_id': tenant_id,
            'event_type': event_type,
            'payload': payload,
            'webhook_url': webhook_url,
            'delivery_status': 'pending',
            'delivery_attempts': 0,
        })

        # Trigger delivery (can be async via queue_job if available)
        event._deliver_webhook()

        return event

    def _deliver_webhook(self):
        """Attempt to deliver the webhook."""
        import requests

        if not self.webhook_url:
            self.delivery_status = 'failed'
            self.error_message = 'No webhook URL configured'
            return

        try:
            response = requests.post(
                self.webhook_url,
                json=self.payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-SaaS-Event': self.event_type,
                    'X-SaaS-Tenant': str(self.tenant_id.id),
                    'X-SaaS-Timestamp': self.event_timestamp.isoformat(),
                },
                timeout=30,
            )

            self.write({
                'delivery_status': 'success' if response.status_code in (200, 201, 204) else 'failed',
                'http_status_code': response.status_code,
                'delivery_timestamp': fields.Datetime.now(),
                'response_body': response.text[:1000],
            })
        except Exception as e:
            self.delivery_attempts += 1
            if self.delivery_attempts >= self.max_delivery_attempts:
                self.delivery_status = 'failed'
            else:
                self.delivery_status = 'retrying'

            self.error_message = str(e)[:500]
