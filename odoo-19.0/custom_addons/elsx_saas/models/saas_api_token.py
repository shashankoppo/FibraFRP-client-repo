# -*- coding: utf-8 -*-
import secrets
import hashlib
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, AccessDenied


class ELSXSaasApiToken(models.Model):
    _name = 'elsx.saas.api.token'
    _description = 'ELSx SaaS API Token / Credential'
    _order = 'create_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade')
    token_key = fields.Char('Token Key (stored masked)', readonly=True)
    token_secret = fields.Char('Token Secret (store securely)', readonly=True)
    display_key = fields.Char('Display Key', compute='_compute_display_key')
    last_four = fields.Char('Last Four Chars', readonly=True)
    description = fields.Char('Description/Purpose')

    is_active = fields.Boolean('Active', default=True)
    expires_on = fields.Date()
    days_until_expiry = fields.Integer(compute='_compute_days_until_expiry')

    last_used = fields.Datetime('Last Used')
    last_used_ip = fields.Char('Last Used IP')
    created_by = fields.Many2one('res.users', readonly=True, default=lambda self: self.env.user)

    allowed_ips = fields.Char('Allowed IP Addresses (comma-separated)', help='Leave blank to allow any IP')

    permissions = fields.Selection([
        ('read_only', 'Read-Only'),
        ('read_write', 'Read/Write'),
        ('admin', 'Admin'),
    ], default='read_only', required=True)

    scope = fields.Selection([
        ('all', 'All Resources'),
        ('tenant_only', 'Tenant Only'),
        ('specific', 'Specific Models'),
    ], default='tenant_only', required=True)

    allowed_models = fields.Char('Allowed Models (comma-separated)', help='Applies when scope is Specific')

    audit_log_ids = fields.One2many('elsx.saas.api.audit', 'token_id', string='API Call Audit Log')
    audit_log_count = fields.Integer(compute='_compute_audit_count')

    _token_key_unique = models.Constraint('UNIQUE (token_key)', 'API token must be unique.')

    @api.depends('tenant_id', 'permissions')
    def _compute_name(self):
        for record in self:
            record.name = '%s - %s' % (record.tenant_id.name or 'Tenant', record.permissions) if record.tenant_id else 'API Token'

    @api.depends('token_key')
    def _compute_display_key(self):
        for record in self:
            if record.token_key:
                record.display_key = record.token_key[:20] + '...' if len(record.token_key) > 20 else record.token_key
            else:
                record.display_key = ''

    @api.depends('expires_on')
    def _compute_days_until_expiry(self):
        today = fields.Date.today()
        for record in self:
            if record.expires_on:
                delta = (record.expires_on - today).days
                record.days_until_expiry = delta if delta >= 0 else 0
            else:
                record.days_until_expiry = None

    @api.depends('audit_log_ids')
    def _compute_audit_count(self):
        for record in self:
            record.audit_log_count = len(record.audit_log_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'token_key' not in vals:
                vals['token_key'] = self._generate_token()
            if 'token_secret' not in vals:
                vals['token_secret'] = self._generate_secret()
            if 'last_four' not in vals:
                vals['last_four'] = vals['token_key'][-4:] if vals.get('token_key') else 'xxxx'

        return super().create(vals_list)

    @staticmethod
    def _generate_token():
        """Generate a secure random API token."""
        return 'elsx_' + secrets.token_urlsafe(32)

    @staticmethod
    def _generate_secret():
        """Generate a secure random secret."""
        return secrets.token_urlsafe(64)

    def _hash_token(self, token):
        """Hash token for storage/validation."""
        return hashlib.sha256(token.encode()).hexdigest()

    def action_regenerate_token(self):
        """Regenerate a new token key for security."""
        self.ensure_one()
        new_token = self._generate_token()
        self.write({
            'token_key': new_token,
            'last_four': new_token[-4:],
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Token Regenerated'),
                'message': _('A new API token has been generated. Update your client immediately.'),
                'type': 'warning',
                'sticky': True,
            },
        }

    def action_extend_expiry(self):
        """Extend token expiry by 90 days."""
        self.ensure_one()
        new_expiry = (fields.Date.today() + timedelta(days=90))
        self.write({'expires_on': new_expiry})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Token Expiry Extended'),
                'message': _('Token will expire on %s') % new_expiry,
                'type': 'success',
            },
        }

    def action_deactivate(self):
        """Deactivate a token."""
        self.write({'is_active': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Token Deactivated'),
                'message': _('This API token is now inactive. Clients will be denied access.'),
                'type': 'info',
            },
        }

    def action_activate(self):
        """Activate a token."""
        self.write({'is_active': True})

    def action_view_audit_log(self):
        """Open the audit log for this token."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('API Audit Log'),
            'res_model': 'elsx.saas.api.audit',
            'view_mode': 'list,form',
            'domain': [('token_id', '=', self.id)],
            'context': {'default_token_id': self.id},
        }

    @api.model
    def verify_and_log(self, token_key, request_ip, method, path):
        """Verify a token and log the API call."""
        # Find token by key
        token = self.search([('token_key', '=', token_key), ('is_active', '=', True)], limit=1)

        if not token:
            raise AccessDenied(_('Invalid or inactive API token.'))

        # Check expiry
        if token.expires_on and token.expires_on < fields.Date.today():
            raise AccessDenied(_('API token has expired.'))

        # Check IP whitelist
        if token.allowed_ips:
            allowed = [ip.strip() for ip in token.allowed_ips.split(',')]
            if request_ip not in allowed:
                raise AccessDenied(_('Request IP %s not allowed for this token.') % request_ip)

        # Update last used
        token.write({
            'last_used': fields.Datetime.now(),
            'last_used_ip': request_ip,
        })

        # Log audit entry
        self.env['elsx.saas.api.audit'].create({
            'token_id': token.id,
            'request_ip': request_ip,
            'method': method,
            'path': path,
        })

        return token


class ELSXSaasApiAudit(models.Model):
    _name = 'elsx.saas.api.audit'
    _description = 'ELSx SaaS API Audit Log Entry'
    _order = 'create_date desc'

    token_id = fields.Many2one('elsx.saas.api.token', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(related='token_id.tenant_id', store=True, readonly=True)

    request_ip = fields.Char()
    method = fields.Char('HTTP Method')
    path = fields.Char('API Path')
    request_timestamp = fields.Datetime(default=fields.Datetime.now)
    response_time_ms = fields.Float('Response Time (ms)')
    status_code = fields.Integer('HTTP Status Code')
    error_message = fields.Text()

    _audit_log_immutable = models.Constraint('CHECK (1=1)', 'This table is immutable.')

    def unlink(self):
        """Prevent deletion of audit logs."""
        raise UserError(_('Audit logs cannot be deleted for compliance and security purposes.'))
