# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class WhatsAppWebhookLog(models.Model):
    """Stores every raw Meta webhook event for audit, debugging and replay"""
    _name = 'whatsapp.webhook.log'
    _description = 'WhatsApp Webhook Event Log'
    _order = 'create_date desc'
    _rec_name = 'event_type'

    account_id = fields.Many2one('whatsapp.account', string='Account')
    event_type = fields.Char('Event Type', index=True)
    field_type = fields.Char('Field')  # e.g. "messages", "account_alerts"
    phone_number = fields.Char('Phone Number')
    message_id = fields.Char('Message ID / WAMID')
    status = fields.Selection([
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('ignored', 'Ignored'),
        ('error', 'Error'),
    ], string='Processing Status', default='received')
    error_detail = fields.Text('Error Detail')
    raw_payload = fields.Text('Raw JSON Payload')
    create_date = fields.Datetime('Received At', readonly=True)

    @api.model
    def _cron_cleanup_old_logs(self, days=30):
        """Cron job to cleanup old webhook logs (default 30 days retention)"""
        from datetime import datetime, timedelta
        
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        
        deleted_count = len(old_logs)
        if deleted_count > 0:
            old_logs.unlink()
            _logger.info(f"[CRON] Deleted {deleted_count} webhook logs older than {days} days")
        
        return deleted_count
