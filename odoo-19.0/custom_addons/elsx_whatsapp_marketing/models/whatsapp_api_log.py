# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import json

_logger = logging.getLogger(__name__)

class WhatsAppApiLog(models.Model):
    _name = 'whatsapp.api.log'
    _description = 'WhatsApp Outbound API Log'
    _order = 'create_date desc'

    account_id = fields.Many2one('whatsapp.account', string='Account', ondelete='cascade')
    endpoint = fields.Char('Endpoint')
    method = fields.Selection([('GET', 'GET'), ('POST', 'POST'), ('DELETE', 'DELETE')], string='Method', default='POST')
    
    request_body = fields.Text('Request Body')
    response_body = fields.Text('Response Body')
    status_code = fields.Integer('HTTP Status Code')
    
    latency = fields.Float('Latency (ms)')
    
    # Context
    message_id_ref = fields.Many2one(
        'whatsapp.message', string='Message Reference', ondelete='set null', index=True,
    )
    campaign_id = fields.Many2one(
        'whatsapp.campaign', string='Campaign', related='message_id_ref.campaign_id',
        store=True, index=True,
    )
    phone_number = fields.Char(
        'Recipient', related='message_id_ref.phone_number', store=True, index=True,
    )
    message_status = fields.Selection(
        related='message_id_ref.status', string='Final Message Status', store=True,
    )
    template_name = fields.Char('Template Used')
    
    success = fields.Boolean('API Accepted', compute='_compute_success', store=True)

    @api.depends('status_code')
    def _compute_success(self):
        for rec in self:
            rec.success = 200 <= rec.status_code < 300

    @api.model
    def _repair_message_links(self):
        """Link historical HTTP attempts to messages using Meta's returned wamid."""
        logs = self.sudo().search([
            ('message_id_ref', '=', False),
            ('status_code', '>=', 200),
            ('status_code', '<', 300),
            ('response_body', '!=', False),
        ])
        linked = 0
        for offset in range(0, len(logs), 500):
            batch = logs[offset:offset + 500]
            wamid_by_log = {}
            for log in batch:
                try:
                    payload = json.loads(log.response_body or '{}')
                    wamid = (payload.get('messages') or [{}])[0].get('id')
                except (TypeError, ValueError, IndexError, AttributeError):
                    wamid = False
                if wamid:
                    wamid_by_log[log.id] = wamid
            messages = self.env['whatsapp.message'].sudo().search([
                ('message_id', 'in', list(set(wamid_by_log.values()))),
            ]) if wamid_by_log else self.env['whatsapp.message']
            message_by_wamid = {message.message_id: message for message in messages}
            for log in batch:
                message = message_by_wamid.get(wamid_by_log.get(log.id))
                if message:
                    log.message_id_ref = message.id
                    linked += 1
        _logger.info('WhatsApp API log message-link repair examined=%s linked=%s', len(logs), linked)
        return {'examined': len(logs), 'linked': linked}

    @api.model
    def _cron_cleanup_old_logs(self):
        """Remove logs older than 7 days to keep DB lean"""
        from datetime import datetime, timedelta
        limit_date = datetime.now() - timedelta(days=7)
        logs = self.search([('create_date', '<', limit_date)])
        count = len(logs)
        logs.unlink()
        _logger.info(f"[CLEANUP] Removed {count} old WhatsApp API logs.")
