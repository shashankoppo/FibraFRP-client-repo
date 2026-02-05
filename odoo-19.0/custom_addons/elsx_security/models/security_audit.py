from odoo import models, fields, api, http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class ELSXSecurityAudit(models.Model):
    _name = 'elsx.security.audit'
    _description = 'Security Session Audit'
    _order = 'timestamp desc'

    user_id = fields.Many2one('res.users', 'User')
    login = fields.Char('Login')
    ip_address = fields.Char('IP Address')
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

    def _check_ip_security(self):
        """Autonomous IP security check"""
        user_ip = request.httprequest.remote_addr
        
        # Check if IP is in our Blocked list
        blocked_check = self.env['elsx.security.audit'].sudo().search([
            ('ip_address', '=', user_ip),
            ('action', '=', 'ip_blocked')
        ], limit=1)
        
        if blocked_check:
             _logger.warning(f"Blocked IP attempted access: {user_ip}")
             # In a real scenario, raise AccessDenied() or similar
             return False

        # Logic to check against blocked IPs or suspicious patterns
        # For demonstration, we log the access
        self.env['elsx.security.audit'].sudo().create({
            'user_id': self.id,
            'login': self.login,
            'ip_address': user_ip,
            'action': 'login',
            'threat_level': 'low'
        })
        return True
