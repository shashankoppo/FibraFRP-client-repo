# -*- coding: utf-8 -*-
import base64
import json
import time
import uuid

from markupsafe import Markup, escape

from odoo import api, fields, models


class WhatsAppDiagnosticSnapshot(models.Model):
    _name = 'whatsapp.diagnostic.snapshot'
    _description = 'WhatsApp Diagnostic Snapshot'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: fields.Datetime.to_string(fields.Datetime.now()))
    correlation_id = fields.Char(readonly=True, copy=False, index=True)
    snapshot_html = fields.Html(sanitize=False, readonly=True)
    snapshot_text = fields.Text(readonly=True)
    snapshot_json = fields.Text(readonly=True)
    severity = fields.Selection([
        ('ok', 'OK'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ], default='ok', required=True, index=True)
    duration_ms = fields.Float(readonly=True)
    snapshot_attachment_id = fields.Many2one('ir.attachment', readonly=True, copy=False)

    @api.model
    def _count_if_model(self, model_name, domain=None):
        if model_name not in self.env.registry.models:
            return 0
        return self.env[model_name].sudo().search_count(domain or [])

    @api.model
    def _collect_snapshot(self):
        ICP = self.env['ir.config_parameter'].sudo()
        now = fields.Datetime.now()
        Message = self.env['whatsapp.message'].sudo()
        Campaign = self.env['whatsapp.campaign'].sudo()
        Account = self.env['whatsapp.account'].sudo()
        Webhook = self.env['whatsapp.webhook.log'].sudo()

        data = {
            'generated_at': fields.Datetime.to_string(now),
            'settings': {
                'realtime_mode': ICP.get_param('whatsapp.realtime.mode', default='bus'),
                'history_initial_limit': ICP.get_param('whatsapp.history.initial.limit', default='50'),
                'ai_enabled': ICP.get_param('elsx_ai.enabled', default='False'),
                'ai_auto_write': ICP.get_param('elsx_ai.auto_write', default='False'),
                'sidecar_configured': bool(ICP.get_param('whatsapp.sidecar.url')),
            },
            'counts': {
                'accounts': Account.search_count([]),
                'chats': self._count_if_model('whatsapp.chat'),
                'messages': Message.search_count([]),
                'campaigns': Campaign.search_count([]),
                'ai_jobs': self._count_if_model('elsx.ai.job'),
            },
            'queues': {
                'queued_campaign_messages': Message.search_count([('campaign_id', '!=', False), ('status', 'in', ['draft', 'queued'])]),
                'failed_retryable_messages': Message.search_count([
                    ('status', '=', 'failed'),
                    ('retry_count', '<', 5),
                    ('next_retry_at', '!=', False),
                ]),
                'failed_messages': Message.search_count([('status', '=', 'failed')]),
                'running_campaigns': Campaign.search_count([('state', 'in', ('running', 'scheduled'))]),
                'failed_ai_jobs': self._count_if_model('elsx.ai.job', [('state', '=', 'failed')]),
            },
            'freshness': {},
        }

        last_webhook = Webhook.search([], order='create_date desc', limit=1)
        if last_webhook:
            delta = now - last_webhook.create_date
            data['freshness']['last_webhook_at'] = fields.Datetime.to_string(last_webhook.create_date)
            data['freshness']['last_webhook_age_minutes'] = round(delta.total_seconds() / 60, 2)
            data['freshness']['last_webhook_status'] = last_webhook.status

        stale_accounts = []
        for account in Account.search([]):
            webhook_at = account.last_webhook_at or account.last_inbound_webhook_at
            if webhook_at:
                age_minutes = (now - webhook_at).total_seconds() / 60
                if age_minutes > 120:
                    stale_accounts.append(account.display_name or account.name)
            elif account.status == 'connected':
                stale_accounts.append(account.display_name or account.name)
        data['freshness']['stale_connected_accounts'] = stale_accounts
        return data

    @api.model
    def _severity_for_snapshot(self, data):
        queues = data.get('queues', {})
        freshness = data.get('freshness', {})
        if queues.get('failed_messages', 0) > 50 or queues.get('failed_ai_jobs', 0) > 10:
            return 'critical'
        if queues.get('queued_campaign_messages', 0) > 500 or freshness.get('stale_connected_accounts'):
            return 'warning'
        if data.get('settings', {}).get('ai_enabled') == 'True' and data.get('settings', {}).get('ai_auto_write') == 'True':
            return 'warning'
        return 'ok'

    @api.model
    def _render_snapshot_html(self, data):
        severity = self._severity_for_snapshot(data)
        color = {'ok': '#16a34a', 'warning': '#f97316', 'critical': '#dc2626'}[severity]

        def card(title, value, detail=''):
            return (
                "<div style='border:1px solid #e5e7eb;border-radius:8px;padding:12px;background:#fff;'>"
                f"<div style='font-size:12px;color:#6b7280;text-transform:uppercase;'>{escape(title)}</div>"
                f"<div style='font-size:22px;font-weight:700;color:#111827;'>{escape(str(value))}</div>"
                f"<div style='font-size:12px;color:#6b7280;'>{escape(detail or '')}</div>"
                "</div>"
            )

        settings = data.get('settings', {})
        counts = data.get('counts', {})
        queues = data.get('queues', {})
        freshness = data.get('freshness', {})
        cards = [
            card('Realtime', settings.get('realtime_mode'), 'socket is optional; bus is default'),
            card('History Limit', settings.get('history_initial_limit'), 'initial messages rendered'),
            card('Messages', counts.get('messages')),
            card('Failed Messages', queues.get('failed_messages')),
            card('Queued Campaign', queues.get('queued_campaign_messages')),
            card('Retryable Failed', queues.get('failed_retryable_messages')),
            card('AI Enabled', settings.get('ai_enabled')),
            card('AI Jobs Failed', queues.get('failed_ai_jobs')),
        ]
        stale = freshness.get('stale_connected_accounts') or []
        stale_html = ''
        if stale:
            stale_html = (
                "<div style='margin-top:12px;border:1px solid #fed7aa;background:#fff7ed;border-radius:8px;padding:12px;'>"
                "<strong>Webhook freshness warning:</strong> "
                f"{escape(', '.join(stale))}</div>"
            )
        return Markup(
            f"<div style='border-left:4px solid {color};padding:12px;background:#f8fafc;border-radius:8px;'>"
            f"<h3 style='margin:0 0 8px;'>System Health: {escape(severity.upper())}</h3>"
            f"<div style='font-size:12px;color:#6b7280;'>Generated at {escape(data.get('generated_at'))}</div>"
            "</div>"
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:12px;'>"
            + ''.join(cards) +
            "</div>" + stale_html
        )

    @api.model
    def _render_snapshot_text(self, data):
        settings = data.get('settings', {})
        counts = data.get('counts', {})
        queues = data.get('queues', {})
        freshness = data.get('freshness', {})
        stale = freshness.get('stale_connected_accounts') or []
        lines = [
            "System Health: %s" % self._severity_for_snapshot(data).upper(),
            "Generated at: %s" % data.get('generated_at'),
            "Realtime mode: %s" % settings.get('realtime_mode'),
            "History initial limit: %s" % settings.get('history_initial_limit'),
            "Messages: %s" % counts.get('messages'),
            "Chats: %s" % counts.get('chats'),
            "Campaigns: %s" % counts.get('campaigns'),
            "Failed messages: %s" % queues.get('failed_messages'),
            "Queued campaign messages: %s" % queues.get('queued_campaign_messages'),
            "Retryable failed messages: %s" % queues.get('failed_retryable_messages'),
            "AI enabled: %s" % settings.get('ai_enabled'),
            "Failed AI jobs: %s" % queues.get('failed_ai_jobs'),
        ]
        if stale:
            lines.append("Webhook freshness warning: %s" % ", ".join(stale))
        return "\n".join(lines)

    @api.model
    def action_capture_now(self):
        start = time.monotonic()
        data = self._collect_snapshot()
        correlation_id = str(uuid.uuid4())
        data['correlation_id'] = correlation_id
        severity = self._severity_for_snapshot(data)
        snapshot = self.create({
            'name': 'WhatsApp Stabilization Snapshot %s' % data['generated_at'],
            'correlation_id': correlation_id,
            'snapshot_json': json.dumps(data, ensure_ascii=False, indent=2),
            'snapshot_html': self._render_snapshot_html(data),
            'snapshot_text': self._render_snapshot_text(data),
            'severity': severity,
            'duration_ms': round((time.monotonic() - start) * 1000, 2),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Health Snapshot',
            'res_model': 'whatsapp.diagnostic.snapshot',
            'res_id': snapshot.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def _redact_export_value(self, value):
        sensitive_parts = ('token', 'secret', 'password', 'authorization', 'access_key')
        if isinstance(value, dict):
            return {
                key: '[redacted]' if any(part in str(key).lower() for part in sensitive_parts)
                else self._redact_export_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_export_value(item) for item in value]
        return value

    def action_export_redacted_json(self):
        self.ensure_one()
        payload = json.loads(self.snapshot_json or '{}')
        payload = self._redact_export_value(payload)
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        filename = 'whatsapp-diagnostic-%s.json' % (self.correlation_id or self.id)
        values = {
            'name': filename,
            'datas': base64.b64encode(content),
            'mimetype': 'application/json',
            'res_model': self._name,
            'res_id': self.id,
        }
        if self.snapshot_attachment_id:
            self.snapshot_attachment_id.sudo().write(values)
            attachment = self.snapshot_attachment_id
        else:
            attachment = self.env['ir.attachment'].sudo().create(values)
            self.snapshot_attachment_id = attachment
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=1' % attachment.id,
            'target': 'self',
        }
