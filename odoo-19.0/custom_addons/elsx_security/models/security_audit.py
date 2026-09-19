from odoo import models, fields
from odoo.http import request
from odoo.addons.elsx_attendance_tracking.proxy_context import resolve_client_context
import logging

_logger = logging.getLogger(__name__)

class ELSXSecurityAudit(models.Model):
    _name = 'elsx.security.audit'
    _description = 'Security Session Audit'
    _order = 'timestamp desc'

    user_id = fields.Many2one('res.users', 'User')
    login = fields.Char('Login')
    ip_address = fields.Char('IP Address')
    ip_source = fields.Selection([
        ('direct', 'Direct Connection'),
        ('trusted_proxy', 'Trusted Proxy'),
        ('cloudflare_tunnel', 'Cloudflare Tunnel'),
    ], 'IP Source', readonly=True)
    device = fields.Char('Device', readonly=True)
    user_agent = fields.Char('User Agent', readonly=True)
    action = fields.Selection([
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('threat_detected', 'Threat Detected'),
        ('ip_blocked', 'IP Blocked')
    ], 'Action')
    threat_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], default='low')
    timestamp = fields.Datetime('Timestamp', default=fields.Datetime.now)

class ResUsers(models.Model):
    _inherit = 'res.users'

    def _record_security_login(self):
        """Record a successful interactive login without altering authentication."""
        self.ensure_one()
        client_context = resolve_client_context(request.httprequest)
        user_ip = client_context['ip_address']
        self.env['elsx.security.audit'].sudo().create({
            'user_id': self.id,
            'login': self.login,
            'ip_address': user_ip,
            'ip_source': client_context['ip_source'],
            'device': client_context['device'],
            'user_agent': client_context['user_agent'],
            'action': 'login',
            'threat_level': 'low'
        })
        return True

    def _check_ip_security(self):
        """Backward-compatible entry point for existing custom callers."""
        self.ensure_one()
        return self._record_security_login()

    def authenticate(self, credential, user_agent_env):
        auth_info = super().authenticate(credential, user_agent_env)
        # API authentication can execute outside an HTTP request. Do not create
        # incomplete audit rows in that case.
        if request:
            user = self.sudo().browse(auth_info['uid']).exists()
            if user:
                user._record_security_login()
        return auth_info
