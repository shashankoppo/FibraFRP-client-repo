"""
SaaS Enterprise Features
========================
Advanced capabilities inspired by Odoo Enterprise Edition:
- Custom fields support for tenants
- Advanced workflow automation
- Scheduled jobs and automation
- Multi-tenant reporting
- Advanced security (SSO, 2FA readiness)
- Custom business processes
"""

from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class ELSXSaasCustomField(models.Model):
    """Custom fields support for tenant-specific data"""
    _name = 'elsx.saas.custom.field'
    _description = 'SaaS Custom Field'
    _rec_name = 'field_label'

    # Field Definition
    field_name = fields.Char(
        string='Field Name',
        required=True,
        help='Technical name for the field'
    )
    field_label = fields.Char(
        string='Label',
        required=True
    )
    field_type = fields.Selection([
        ('char', 'Text'),
        ('integer', 'Number'),
        ('float', 'Decimal'),
        ('boolean', 'Checkbox'),
        ('date', 'Date'),
        ('datetime', 'Date Time'),
        ('selection', 'Selection'),
        ('many2one', 'Link'),
        ('text', 'Long Text'),
    ], string='Type', required=True)

    # Configuration
    model_id = fields.Char(
        string='Model',
        required=True,
        help='Model to add field to (e.g., elsx.saas.tenant)'
    )
    required = fields.Boolean(string='Required')
    readonly = fields.Boolean(string='Read Only')
    stored = fields.Boolean(
        string='Stored in DB',
        default=True,
        help='If False, computed on-the-fly'
    )

    # Options
    selection_values = fields.Text(
        string='Selection Options',
        help='For selection fields: option1,option2,option3'
    )
    help_text = fields.Text(string='Help Text')

    # Visibility
    group_ids = fields.Many2many(
        'res.groups',
        string='Visible To Groups',
        help='Leave empty to show to all'
    )

    # Usage
    default_value = fields.Char(string='Default Value')
    is_active = fields.Boolean(
        string='Active',
        default=True
    )
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        readonly=True,
        default=lambda self: self.env.user
    )

    _sql_constraints = [
        ('field_name_unique', 'unique(field_name)', 'Field name must be unique'),
    ]


class ELSXSaasWorkflowAutomation(models.Model):
    """Automated business processes and workflows"""
    _name = 'elsx.saas.workflow.automation'
    _description = 'SaaS Workflow Automation'
    _rec_name = 'name'

    # Basic Info
    name = fields.Char(
        string='Workflow Name',
        required=True
    )
    description = fields.Text(string='Description')
    model_id = fields.Char(
        string='Model',
        required=True,
        help='Model to apply workflow to'
    )

    # Triggers
    trigger_on = fields.Selection([
        ('create', 'When Created'),
        ('write', 'When Updated'),
        ('state_change', 'When State Changes'),
        ('scheduled', 'Scheduled (Cron)'),
    ], string='Trigger On', required=True)

    trigger_conditions = fields.Text(
        string='Conditions (Python)',
        help='Python code: if <condition> in record.field: execute()'
    )

    # Actions
    action_type = fields.Selection([
        ('send_email', 'Send Email'),
        ('create_record', 'Create Record'),
        ('update_field', 'Update Field'),
        ('webhook', 'Call Webhook'),
        ('run_python', 'Run Python Code'),
    ], string='Action Type', required=True)

    action_details = fields.Text(
        string='Action Details',
        help='Details for the action (model, fields, code, etc.)'
    )

    # Schedule (for cron-based)
    cron_schedule = fields.Char(
        string='Cron Schedule',
        help='minute hour day month day_of_week'
    )

    # Status
    is_active = fields.Boolean(
        string='Active',
        default=True
    )
    run_count = fields.Integer(
        string='Times Run',
        readonly=True
    )
    last_run = fields.Datetime(
        string='Last Run',
        readonly=True
    )

    # Audit
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        readonly=True,
        default=lambda self: self.env.user
    )
    created_date = fields.Datetime(
        string='Created',
        readonly=True,
        default=lambda self: fields.Datetime.now()
    )


class ELSXSaasScheduledJob(models.Model):
    """Scheduled maintenance and automation jobs"""
    _name = 'elsx.saas.scheduled.job'
    _description = 'SaaS Scheduled Job'
    _rec_name = 'name'

    # Job Definition
    name = fields.Char(
        string='Job Name',
        required=True
    )
    description = fields.Text(string='Description')
    job_type = fields.Selection([
        ('health_check', 'Health Check'),
        ('cleanup', 'Data Cleanup'),
        ('report', 'Generate Report'),
        ('sync', 'Synchronization'),
        ('backup', 'Backup'),
        ('maintenance', 'Maintenance'),
        ('custom', 'Custom Python'),
    ], string='Job Type', required=True)

    # Python Code
    python_code = fields.Text(
        string='Python Code',
        help='Code executed when job runs'
    )

    # Schedule
    frequency = fields.Selection([
        ('hourly', 'Every Hour'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
        ('custom', 'Custom Cron'),
    ], string='Frequency', required=True, default='daily')

    schedule_time = fields.Char(
        string='Time',
        help='HH:MM format'
    )

    cron_expression = fields.Char(
        string='Cron Expression',
        help='For custom cron'
    )

    # Execution
    is_active = fields.Boolean(
        string='Active',
        default=True
    )
    execution_count = fields.Integer(
        string='Executions',
        readonly=True
    )
    last_execution = fields.Datetime(
        string='Last Execution',
        readonly=True
    )
    last_result = fields.Selection([
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string='Last Result', readonly=True)

    last_error = fields.Text(
        string='Last Error',
        readonly=True
    )

    # Configuration
    notify_on_error = fields.Boolean(
        string='Notify on Error',
        default=True
    )
    notification_emails = fields.Char(
        string='Notification Emails',
        help='Comma-separated emails'
    )

    # Audit
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        readonly=True,
        default=lambda self: self.env.user
    )


class ELSXSaasSecurityPolicy(models.Model):
    """Advanced security policies and controls"""
    _name = 'elsx.saas.security.policy'
    _description = 'SaaS Security Policy'
    _rec_name = 'name'

    # Policy Definition
    name = fields.Char(
        string='Policy Name',
        required=True
    )
    description = fields.Text(string='Description')

    # Access Control
    policy_type = fields.Selection([
        ('ip_whitelist', 'IP Whitelist'),
        ('rate_limit', 'Rate Limiting'),
        ('api_permission', 'API Permissions'),
        ('field_level', 'Field-Level Security'),
        ('record_rule', 'Record Rules'),
        ('password_policy', 'Password Policy'),
    ], string='Policy Type', required=True)

    # IP Whitelist
    allowed_ips = fields.Text(
        string='Allowed IPs',
        help='One IP per line, supports CIDR notation'
    )
    ip_restriction_enabled = fields.Boolean(string='Enable IP Restriction')

    # Rate Limiting
    rate_limit_enabled = fields.Boolean(string='Enable Rate Limiting')
    requests_per_minute = fields.Integer(string='Requests per Minute')
    requests_per_hour = fields.Integer(string='Requests per Hour')

    # Password Policy
    min_password_length = fields.Integer(
        string='Min Password Length',
        default=8
    )
    require_uppercase = fields.Boolean(string='Require Uppercase')
    require_lowercase = fields.Boolean(string='Require Lowercase')
    require_numbers = fields.Boolean(string='Require Numbers')
    require_special = fields.Boolean(string='Require Special Characters')
    password_expiry_days = fields.Integer(string='Password Expiry (days)')

    # 2FA Readiness
    sso_enabled = fields.Boolean(
        string='SSO Support',
        help='Ready for SAML/OAuth integration'
    )
    two_fa_enabled = fields.Boolean(
        string='2FA Support',
        help='Two-factor authentication ready'
    )

    # Status
    is_active = fields.Boolean(
        string='Active',
        default=True
    )

    # Audit
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        readonly=True,
        default=lambda self: self.env.user
    )
    created_date = fields.Datetime(
        string='Created',
        readonly=True,
        default=lambda self: fields.Datetime.now()
    )


class ELSXSaasReportTemplate(models.Model):
    """Multi-tenant reporting templates"""
    _name = 'elsx.saas.report.template'
    _description = 'SaaS Report Template'
    _rec_name = 'name'

    # Report Definition
    name = fields.Char(
        string='Report Name',
        required=True
    )
    description = fields.Text(string='Description')

    # Report Type
    report_type = fields.Selection([
        ('usage', 'Usage Report'),
        ('billing', 'Billing Report'),
        ('health', 'Health Report'),
        ('support', 'Support Report'),
        ('custom', 'Custom Report'),
    ], string='Report Type', required=True)

    # Data Source
    data_model = fields.Char(
        string='Data Model',
        help='Model to pull data from'
    )

    # Filters
    filter_domains = fields.Text(
        string='Filters',
        help='Odoo domain filter conditions'
    )

    # Fields
    field_list = fields.Text(
        string='Fields',
        help='Fields to include in report'
    )

    # Scheduling
    auto_generate = fields.Boolean(
        string='Auto Generate',
        default=False
    )
    generation_frequency = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string='Generation Frequency')

    # Distribution
    auto_send = fields.Boolean(
        string='Auto Send',
        default=False
    )
    recipient_emails = fields.Char(
        string='Recipients',
        help='Comma-separated emails'
    )

    # Status
    is_active = fields.Boolean(
        string='Active',
        default=True
    )
    generation_count = fields.Integer(
        string='Times Generated',
        readonly=True
    )
    last_generated = fields.Datetime(
        string='Last Generated',
        readonly=True
    )

    # Audit
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        readonly=True,
        default=lambda self: self.env.user
    )
