# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import uuid

_logger = logging.getLogger(__name__)

class WhatsAppApiLog(models.Model):
    _name = 'whatsapp.api.log'
    _description = 'WhatsApp Outbound API Log'
    _order = 'create_date desc'

    account_id = fields.Many2one('whatsapp.account', string='Account', ondelete='cascade')
    correlation_id = fields.Char(
        'Correlation ID',
        default=lambda self: str(uuid.uuid4()),
        copy=False,
        readonly=True,
        index=True,
    )
    endpoint = fields.Char('Endpoint')
    method = fields.Selection([('GET', 'GET'), ('POST', 'POST'), ('DELETE', 'DELETE')], string='Method', default='POST')
    
    request_body = fields.Text('Request Body')
    response_body = fields.Text('Response Body')
    status_code = fields.Integer('HTTP Status Code')
    
    latency = fields.Float('Latency (ms)')
    
    # Context
    message_id_ref = fields.Many2one('whatsapp.message', string='Message Reference')
    template_name = fields.Char('Template Used')
    
    success = fields.Boolean('Success', compute='_compute_success', store=True)

    @api.depends('status_code')
    def _compute_success(self):
        for rec in self:
            rec.success = 200 <= rec.status_code < 300

    @api.model
    def _cron_cleanup_old_logs(self):
        """Remove logs older than 7 days to keep DB lean"""
        from datetime import datetime, timedelta
        limit_date = datetime.now() - timedelta(days=7)
        logs = self.search([('create_date', '<', limit_date)])
        count = len(logs)
        logs.unlink()
        _logger.info(f"[CLEANUP] Removed {count} old WhatsApp API logs.")
