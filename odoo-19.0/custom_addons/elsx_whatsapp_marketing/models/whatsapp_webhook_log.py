# -*- coding: utf-8 -*-
from datetime import timedelta
import json
import time

from odoo import SUPERUSER_ID, models, fields, api, _
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

    @api.model
    def _is_serialization_failure(self, exc):
        seen = set()
        current = exc
        while current and id(current) not in seen:
            seen.add(id(current))
            if (
                getattr(current, 'pgcode', None) == '40001'
                or current.__class__.__name__ == 'SerializationFailure'
                or 'could not serialize access due to concurrent update' in str(current)
            ):
                return True
            current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)
        return False

    @api.model
    def _process_log_with_retry(self, log_id):
        """Process one durable webhook in its own retryable transaction."""
        last_error = None
        for attempt, delay in enumerate((0, 0.05, 0.15, 0.35, 0.75), start=1):
            if delay:
                time.sleep(delay)
            with self.env.registry.cursor() as recovery_cr:
                recovery_env = api.Environment(recovery_cr, SUPERUSER_ID, {})
                log = recovery_env['whatsapp.webhook.log'].sudo().browse(log_id).exists()
                if not log or log.status in ('processed', 'ignored'):
                    return False
                try:
                    processed = log._process_received_payload()
                    recovery_cr.commit()
                    return bool(processed)
                except Exception as exc:
                    recovery_cr.rollback()
                    if self._is_serialization_failure(exc):
                        last_error = exc
                        _logger.info(
                            '[WH-RECOVERY] Serialization retry %s/5 for log_id=%s',
                            attempt,
                            log_id,
                        )
                        continue
                    raise
        raise last_error

    @api.model
    def _persist_processing_error(self, log_id, exc):
        with self.env.registry.cursor() as error_cr:
            error_env = api.Environment(error_cr, SUPERUSER_ID, {})
            log = error_env['whatsapp.webhook.log'].sudo().browse(log_id).exists()
            if log:
                log.write({
                    'status': 'error',
                    'error_detail': (str(exc) or exc.__class__.__name__)[:2000],
                })
            error_cr.commit()

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

        replay_log = self.with_context(whatsapp_webhook_replay=True)
        replay_env = replay_log.env
        replay_account = account.with_env(replay_env)
        dispatcher = WhatsAppWebhook()
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                dispatcher._dispatch_change(
                    replay_env,
                    replay_account,
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
        for log_id in self.ids:
            try:
                if self._process_log_with_retry(log_id):
                    processed += 1
            except Exception as exc:
                failed += 1
                self._persist_processing_error(log_id, exc)
                _logger.exception("WhatsApp webhook replay failed for log_id=%s", log_id)
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
            ('create_date', '<=', cutoff),
            '|',
                ('status', '=', 'received'),
                '&',
                    ('status', '=', 'error'),
                    ('error_detail', 'ilike', 'serialize'),
        ], order='create_date asc, id asc', limit=limit)
        processed = 0
        failed = 0
        for log_id in pending.ids:
            try:
                if self._process_log_with_retry(log_id):
                    processed += 1
            except Exception as exc:
                failed += 1
                self._persist_processing_error(log_id, exc)
                _logger.exception("WhatsApp webhook recovery failed for log_id=%s", log_id)
        _logger.info(
            "[WH-RECOVERY] pending=%s processed=%s failed=%s",
            len(pending), processed, failed,
        )
        return processed

    @api.model
    def _cron_cleanup_old_logs(self, days=None):
        """Cleanup webhook logs only when retention is explicitly enabled."""
        if days is None:
            retention_value = self.env['ir.config_parameter'].sudo().get_param(
                'whatsapp.webhook_log.retention_days',
                default=0,
            )
            try:
                days = int(retention_value or 0)
            except (TypeError, ValueError):
                _logger.warning(
                    "WhatsApp webhook log cleanup skipped; invalid retention value: %r",
                    retention_value,
                )
                return 0
        if days <= 0:
            _logger.info("WhatsApp webhook log cleanup skipped; retention is disabled.")
            return 0

        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        
        deleted_count = len(old_logs)
        if deleted_count > 0:
            old_logs.unlink()
            _logger.info(f"[CRON] Deleted {deleted_count} webhook logs older than {days} days")
        
        return deleted_count
