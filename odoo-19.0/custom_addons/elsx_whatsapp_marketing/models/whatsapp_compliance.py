# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import pytz

_logger = logging.getLogger(__name__)


def _timezone_selection(self):
    return [(tz, tz) for tz in pytz.all_timezones]


class WhatsAppCompliancePolicy(models.Model):
    """GDPR and Compliance Settings"""
    _name = 'whatsapp.compliance.policy'
    _description = 'WhatsApp Compliance & Privacy Policy'
    _rec_name = 'name'

    name = fields.Char('Policy Name', required=True)
    account_id = fields.Many2one('whatsapp.account', required=True, ondelete='cascade')
    description = fields.Text('Description')
    
    # GDPR Compliance
    require_opt_in = fields.Boolean('Require Explicit Opt-in', default=True,
                                    help='Contacts must explicitly consent before messaging')
    require_consent_timestamp = fields.Boolean('Record Consent Timestamp', default=True)
    consent_retention_days = fields.Integer('Consent Retention Period (days)', default=365)
    
    # Do Not Contact
    respect_dnd_list = fields.Boolean('Respect Do Not Call/Text', default=True)
    dnd_contact_ids = fields.Many2many('res.partner', 'whatsapp_dnd_rel',
                                       string='Do Not Contact List')
    
    # Message Retention
    message_retention_type = fields.Selection([
        ('permanent', 'Permanent'),
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years'),
    ], default='months')
    message_retention_value = fields.Integer('Retention Period', default=12, help='Number of days/months/years')
    auto_delete_messages = fields.Boolean('Auto-delete Old Messages', default=False)
    
    # Data Privacy
    encrypt_sensitive_data = fields.Boolean('Encrypt Sensitive Data', default=True)
    mask_phone_numbers = fields.Boolean('Mask Phone Numbers in Reports', default=False)
    anonymize_old_data = fields.Boolean('Anonymize Data After Retention Period', default=False)
    
    # Consent Management
    consent_text = fields.Text('Consent Message',
                              help='Message shown to users requesting consent',
                              default='By continuing, you consent to receive WhatsApp messages from us.')
    
    # Audit & Logging
    audit_all_messages = fields.Boolean('Audit All Messages', default=True)
    audit_sensitive_operations = fields.Boolean('Audit Sensitive Operations', default=True,
                                               help='Log data access, exports, deletions')
    audit_retention_days = fields.Integer('Audit Log Retention (days)', default=365)
    
    # Regional Compliance
    region = fields.Selection([
        ('global', 'Global'),
        ('eu', 'EU (GDPR)'),
        ('uk', 'UK (UK GDPR)'),
        ('ca', 'Canada (PIPEDA)'),
        ('us', 'USA'),
        ('au', 'Australia (APPs)'),
    ], default='global')
    
    # Data Processing Agreement
    dpa_enabled = fields.Boolean('Data Processing Agreement Enabled', default=False)
    dpa_text = fields.Text('DPA Terms')
    processor_name = fields.Char('Data Processor Name')
    
    # Compliance Status
    active = fields.Boolean('Active', default=True)
    last_reviewed_date = fields.Date('Last Reviewed')
    next_review_date = fields.Date('Next Review Due')


class WhatsAppQuietHours(models.Model):
    """Define quiet hours when automated messages should not be sent"""
    _name = 'whatsapp.quiet.hours'
    _description = 'WhatsApp Quiet Hours'

    policy_id = fields.Many2one('whatsapp.compliance.policy', required=True, ondelete='cascade')
    name = fields.Char('Name', required=True, default='Night Time')
    active = fields.Boolean('Active', default=True)
    
    start_time = fields.Float('Start Time (24h)', required=True, default=21.0)
    end_time = fields.Float('End Time (24h)', required=True, default=8.0)
    timezone = fields.Selection(selection=_timezone_selection, default='UTC', required=True)
    
    days_of_week = fields.Selection([
        ('all', 'Everyday'),
        ('weekdays', 'Weekdays Only'),
        ('weekends', 'Weekends Only'),
    ], default='all', required=True)


class WhatsAppConsentLog(models.Model):
    """Track user consent for GDPR compliance"""
    _name = 'whatsapp.consent.log'
    _description = 'WhatsApp Consent Log'
    _order = 'create_date desc'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    account_id = fields.Many2one('whatsapp.account', required=True)
    
    consent_type = fields.Selection([
        ('marketing', 'Marketing Messages'),
        ('transactional', 'Transactional Messages'),
        ('newsletter', 'Newsletter'),
        ('survey', 'Survey/Feedback'),
        ('all', 'All Communications'),
    ], required=True)
    
    status = fields.Selection([
        ('opted_in', 'Opted In'),
        ('opted_out', 'Opted Out'),
        ('revoked', 'Revoked'),
    ], default='opted_in')
    
    consent_date = fields.Datetime('Consent Date', default=fields.Datetime.now)
    source = fields.Selection([
        ('manual', 'Manual'),
        ('website', 'Website Form'),
        ('facebook', 'Facebook Ad'),
        ('import', 'CSV Import'),
        ('api', 'API'),
        ('whatsapp_message', 'WhatsApp Message'),
        ('other', 'Other'),
    ], required=True, default='manual')
    
    ip_address = fields.Char('IP Address')
    user_agent = fields.Char('User Agent')
    notes = fields.Text('Notes')
    
    # For audit trail
    revoked_date = fields.Datetime('Revoked Date', readonly=True)
    revoked_reason = fields.Char('Revoked Reason')
    revoked_by = fields.Many2one('res.users', 'Revoked By', readonly=True)

    @api.model
    def _opt_out_partner(self, partner, account, reason=None):
        """Helper to record an opt-out event and block future messages."""
        return self.create({
            'partner_id': partner.id,
            'account_id': account.id,
            'consent_type': 'all',
            'status': 'opted_out',
            'source': 'whatsapp_message',
            'notes': reason or 'User requested opt-out via WhatsApp',
            'revoked_date': fields.Datetime.now(),
        })


class WhatsAppTeamMember(models.Model):
    """Team Collaboration - Assign team members to conversations"""
    _name = 'whatsapp.team.member'
    _description = 'WhatsApp Team Member'

    account_id = fields.Many2one('whatsapp.account', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    
    # Role and Permissions
    role = fields.Selection([
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('agent', 'Conversation Agent'),
        ('analyst', 'Analyst (Read-only)'),
    ], default='agent')
    
    # Availability
    is_available = fields.Boolean('Available', default=True)
    max_active_chats = fields.Integer('Max Active Chats', default=5,
                                      help='Maximum open conversations this agent should receive automatically.')
    working_hours_start = fields.Float('Working Hours Start (24h)', default=9.0)
    working_hours_end = fields.Float('Working Hours End (24h)', default=18.0)
    timezone_id = fields.Selection(selection=_timezone_selection, compute='_compute_timezone_id', readonly=True)
    
    # Stats
    assigned_chats = fields.Integer('Active Conversations', compute='_compute_stats')
    resolved_count = fields.Integer('Resolved (30d)', compute='_compute_stats')
    response_time_avg = fields.Float('Avg Response Time (min)', compute='_compute_stats')
    
    # Permissions
    can_send_messages = fields.Boolean('Can Send Messages', default=True)
    can_send_campaigns = fields.Boolean('Can Send Campaigns', default=False)
    can_manage_templates = fields.Boolean('Can Manage Templates', default=False)
    can_manage_team = fields.Boolean('Can Manage Team', default=False)
    can_view_analytics = fields.Boolean('Can View Analytics', default=True)
    can_manage_contacts = fields.Boolean('Can Manage Contacts', default=True)
    can_transfer_chats = fields.Boolean('Can Transfer Chats', default=True)
    can_delete_messages = fields.Boolean('Can Delete Messages', default=False)

    @api.depends('user_id', 'user_id.tz')
    def _compute_timezone_id(self):
        for record in self:
            record.timezone_id = record.user_id.tz or False
    
    def _compute_stats(self):
        """Calculate team member statistics"""
        for record in self:
            # Assigned chats
            record.assigned_chats = self.env['whatsapp.chat'].search_count([
                ('assigned_user_id', '=', record.user_id.id),
                ('state', '=', 'open'),
            ])
            
            # Resolved chats in last 30 days
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.now() - timedelta(days=30)
            record.resolved_count = self.env['whatsapp.chat'].search_count([
                ('assigned_user_id', '=', record.user_id.id),
                ('state', '=', 'resolved'),
                ('write_date', '>=', thirty_days_ago),
            ])
            
            record.response_time_avg = 0


class WhatsAppConversationAssignment(models.Model):
    """Track conversation assignments and transfers between team members"""
    _name = 'whatsapp.conversation.assignment'
    _description = 'Conversation Assignment'
    _rec_name = 'chat_id'

    chat_id = fields.Many2one('whatsapp.chat', required=True, ondelete='cascade')
    assigned_user_id = fields.Many2one('res.users', 'Assigned To', required=True)
    assigned_by = fields.Many2one('res.users', 'Assigned By')
    assigned_date = fields.Datetime('Assigned Date', default=fields.Datetime.now)
    
    # Transfer history
    previous_user_id = fields.Many2one('res.users', 'Previously Assigned To')
    transfer_reason = fields.Selection([
        ('initial', 'Initial Assignment'),
        ('availability', 'Agent Unavailable'),
        ('bot', 'Bot Transfer'),
        ('expertise', 'Expertise Required'),
        ('customer_request', 'Customer Request'),
        ('workload', 'Workload Balancing'),
        ('escalation', 'Escalation'),
        ('manual', 'Manual Transfer'),
    ], string='Transfer Reason')
    
    # Notes
    transfer_notes = fields.Text('Transfer Notes')
    
    # Timeline
    resolved_date = fields.Datetime('Resolved Date')
    duration_minutes = fields.Float('Duration (minutes)', compute='_compute_duration')
    
    def _compute_duration(self):
        """Calculate assignment duration"""
        for record in self:
            if record.resolved_date:
                delta = record.resolved_date - record.assigned_date
                record.duration_minutes = delta.total_seconds() / 60
            else:
                record.duration_minutes = 0


class WhatsAppTeamPerformance(models.Model):
    """Track team performance metrics"""
    _name = 'whatsapp.team.performance'
    _description = 'Team Performance Metrics'
    _auto = False  # SQL view

    account_id = fields.Many2one('whatsapp.account')
    user_id = fields.Many2one('res.users')
    
    # KPIs
    total_chats = fields.Integer('Total Conversations')
    resolved_chats = fields.Integer('Resolved')
    resolution_rate = fields.Float('Resolution Rate %')
    avg_response_time = fields.Float('Avg Response Time (min)')
    avg_resolution_time = fields.Float('Avg Resolution Time (min)')
    customer_satisfaction = fields.Float('Customer Satisfaction %')
    
    # Period
    date_from = fields.Date('Period Start')
    date_to = fields.Date('Period End')

    def init(self):
        from odoo import tools
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    c.account_id AS account_id,
                    c.assigned_user_id AS user_id,
                    COUNT(c.id) AS total_chats,
                    SUM(CASE WHEN c.state = 'resolved' THEN 1 ELSE 0 END) AS resolved_chats,
                    CASE
                        WHEN COUNT(c.id) > 0 
                        THEN (SUM(CASE WHEN c.state = 'resolved' THEN 1 ELSE 0 END)::float / COUNT(c.id)) * 100
                        ELSE 0
                    END AS resolution_rate,
                    0 AS avg_response_time,
                    0 AS avg_resolution_time,
                    0 AS customer_satisfaction,
                    MIN(c.create_date)::date AS date_from,
                    MAX(c.write_date)::date AS date_to
                FROM whatsapp_chat c
                WHERE c.assigned_user_id IS NOT NULL
                GROUP BY c.account_id, c.assigned_user_id
            )
        """ % self._table)
