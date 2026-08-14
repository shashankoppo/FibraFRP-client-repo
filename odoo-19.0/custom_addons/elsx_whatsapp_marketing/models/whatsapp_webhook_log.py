# -*- coding: utf-8 -*-
from datetime import timedelta
import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError
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

    def _process_received_payload(self):
        """Replay a durable top-level webhook through the normal dispatcher."""
        self.ensure_one()
        if self.event_type != 'waba_webhook':
            raise UserError(_("Only top-level WhatsApp webhook records can be replayed."))
        try:
            payload = json.loads(self.raw_payload or '{}')
        except (TypeError, ValueError) as exc:
            raise UserError(_("Webhook payload is not valid JSON: %s") % exc) from exc
        if payload.get('object') != 'whatsapp_business_account':
            self.write({'status': 'ignored', 'error_detail': False})
            return False

        account = self.account_id
        if not account:
            try:
                metadata = payload.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')
            except (AttributeError, IndexError, TypeError):
                phone_number_id = False
            if phone_number_id:
                account = self.env['whatsapp.account'].sudo().search([
                    ('phone_number_id', '=', phone_number_id),
                    ('active', '=', True),
                ], limit=1)
        if not account:
            raise UserError(_("No active WhatsApp account matches this webhook payload."))

        from odoo.addons.elsx_whatsapp_marketing.controllers.whatsapp_webhook import WhatsAppWebhook

        dispatcher = WhatsAppWebhook()
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                dispatcher._dispatch_change(
                    self.env,
                    account,
                    change.get('field', ''),
                    change.get('value') or {},
                    self.raw_payload or '',
                )
        self.write({
            'account_id': account.id,
            'status': 'processed',
            'error_detail': False,
        })
        return True

    def action_replay(self):
        processed = 0
        failed = 0
        for log in self:
            try:
                with self.env.cr.savepoint():
                    if log._process_received_payload():
                        processed += 1
            except Exception as exc:
                failed += 1
                log.sudo().write({
                    'status': 'error',
                    'error_detail': (str(exc) or exc.__class__.__name__)[:2000],
                })
                _logger.exception("WhatsApp webhook replay failed for log_id=%s", log.id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Webhook Replay'),
                'message': _('%(processed)s processed, %(failed)s failed.') % {
                    'processed': processed,
                    'failed': failed,
                },
                'type': 'warning' if failed else 'success',
                'sticky': bool(failed),
            },
        }

    @api.model
    def _cron_recover_received(self, limit=100):
        """Recover webhooks left behind by a worker restart or thread failure."""
        cutoff = fields.Datetime.now() - timedelta(minutes=1)
        pending = self.sudo().search([
            ('event_type', '=', 'waba_webhook'),
            ('status', '=', 'received'),
            ('create_date', '<=', cutoff),
        ], order='create_date asc, id asc', limit=limit)
        processed = 0
        failed = 0
        for log in pending:
            try:
                with self.env.cr.savepoint():
                    if log._process_received_payload():
                        processed += 1
            except Exception as exc:
                failed += 1
                log.sudo().write({
                    'status': 'error',
                    'error_detail': (str(exc) or exc.__class__.__name__)[:2000],
                })
                _logger.exception("WhatsApp webhook recovery failed for log_id=%s", log.id)
        _logger.info(
            "[WH-RECOVERY] pending=%s processed=%s failed=%s",
            len(pending), processed, failed,
        )
        return processed

    @api.model
    def _cron_cleanup_old_logs(self, days=30):
        """Cron job to cleanup old webhook logs (default 30 days retention)"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        
        deleted_count = len(old_logs)
        if deleted_count > 0:
            old_logs.unlink()
            _logger.info(f"[CRON] Deleted {deleted_count} webhook logs older than {days} days")
        
        return deleted_count
