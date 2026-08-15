# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
import logging
import json
import random
import time
import base64
import csv
import io
from html import escape as html_escape
from datetime import timedelta
from urllib.parse import quote

import requests

_logger = logging.getLogger(__name__)


class WhatsAppCampaign(models.Model):
    _name = 'whatsapp.campaign'
    _description = 'WhatsApp Marketing Campaign'
    _order = 'create_date desc'

    _campaign_state_schedule_idx = models.Index("(state, schedule_date, create_date)")
    _SERIALIZATION_RETRY_DELAYS = (0, 0.1, 0.25, 0.5, 1.0)

    def _is_serialization_failure(self, exc):
        pgcode = getattr(exc, 'pgcode', None)
        if pgcode == '40001':
            return True
        cause = getattr(exc, '__cause__', None)
        if getattr(cause, 'pgcode', None) == '40001':
            return True
        text = str(exc).lower()
        return 'could not serialize access' in text or 'serializationfailure' in text

    def _create_campaign_messages_safely(self, message_model, vals_list, batch_size=100):
        """Create campaign queue rows in retryable batches under webhook load."""
        created = message_model.browse()
        total = len(vals_list)
        for offset in range(0, total, batch_size):
            batch = vals_list[offset:offset + batch_size]
            for attempt, delay in enumerate(self._SERIALIZATION_RETRY_DELAYS, start=1):
                if delay:
                    time.sleep(delay)
                try:
                    with self.env.cr.savepoint():
                        created |= message_model.create(batch)
                    break
                except Exception as exc:
                    if not self._is_serialization_failure(exc) or attempt == len(self._SERIALIZATION_RETRY_DELAYS):
                        raise
                    _logger.warning(
                        "Campaign %s queue create serialization retry %s/%s for rows %s-%s: %s",
                        self.id,
                        attempt,
                        len(self._SERIALIZATION_RETRY_DELAYS),
                        offset + 1,
                        min(offset + len(batch), total),
                        exc,
                    )
        return created

    @api.model
    def _schedule_campaign_queue_cron(self, delay_seconds=60):
        """Trigger the regular queue cron without changing its recurring schedule."""
        cron = self.env.ref('elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue', raise_if_not_found=False)
        if not cron:
            _logger.warning("WhatsApp campaign queue cron is missing; queued campaigns will need manual processing.")
            return False

        delay_seconds = max(int(delay_seconds or 0), 0)
        call_at = fields.Datetime.now() + timedelta(seconds=delay_seconds)
        try:
            if not cron.active:
                cron.sudo().write({'active': True})
            cron.sudo()._trigger(at=call_at)
        except Exception as exc:
            _logger.warning("Could not trigger WhatsApp campaign queue cron: %s", exc)
            return False
        return True

    @api.model
    def _wake_campaign_queue_cron(self):
        """Make the campaign queue worker due soon after queue creation or repair."""
        return self._schedule_campaign_queue_cron(delay_seconds=10)

    @api.model
    def _schedule_next_campaign_queue_run(self, default_delay_seconds=60):
        """Schedule the queue cron near the next due queued campaign message."""
        now = fields.Datetime.now()
        Message = self.env['whatsapp.message'].sudo()
        due_count = Message.search_count([
            ('campaign_id.state', 'in', ['running', 'scheduled']),
            '|',
                ('status', '=', 'draft'),
                '&', ('status', '=', 'queued'), '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
        ])
        if due_count:
            return self._schedule_campaign_queue_cron(delay_seconds=default_delay_seconds)

        next_msg = Message.search([
            ('campaign_id.state', 'in', ['running', 'scheduled']),
            ('status', 'in', ['draft', 'queued']),
            ('next_retry_at', '!=', False),
        ], order='next_retry_at asc, create_date asc', limit=1)
        if not next_msg:
            return False

        delay_seconds = max(int((next_msg.next_retry_at - now).total_seconds()), default_delay_seconds)
        return self._schedule_campaign_queue_cron(delay_seconds=delay_seconds)

    @api.model
    def _repair_running_campaign_queues(self):
        """Unstick running campaigns that have queued rows but no due batch."""
        Message = self.env['whatsapp.message'].sudo()
        now = fields.Datetime.now()
        repaired = 0
        campaigns = self.sudo().search([('state', '=', 'running')])
        for campaign in campaigns:
            queued_domain = [
                ('campaign_id', '=', campaign.id),
                ('status', 'in', ['draft', 'queued']),
            ]
            if not Message.search_count(queued_domain):
                continue
            due_domain = queued_domain + [
                '|',
                    ('status', '=', 'draft'),
                    '&', ('status', '=', 'queued'), '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
            ]
            if Message.search_count(due_domain):
                continue
            batch_size = max(int(campaign.batch_size or 50), 1)
            to_release = Message.search(queued_domain, order='next_retry_at asc, create_date asc', limit=batch_size)
            if to_release:
                to_release.write({'status': 'queued', 'next_retry_at': now})
                campaign.last_batch_at = False
                repaired += len(to_release)

        if repaired:
            self._wake_campaign_queue_cron()
        _logger.info("WhatsApp running campaign queue repair released=%s", repaired)
        return repaired

    @api.model
    def _repair_campaign_statistics(self):
        """Refresh stored campaign counters after rate calculation upgrades."""
        campaign_ids = self.sudo().search([]).ids
        for offset in range(0, len(campaign_ids), 200):
            self.browse(campaign_ids[offset:offset + 200])._compute_statistics()
        _logger.info("WhatsApp campaign statistics refreshed=%s", len(campaign_ids))
        return len(campaign_ids)

    @api.model
    def _repair_cancelled_campaign_queues(self):
        """Keep canceled/archived campaigns from leaking work into delivery queues."""
        Message = self.env['whatsapp.message'].sudo()
        pending = Message.search([
            ('campaign_id.state', 'in', ['cancelled', 'archived']),
            ('status', 'in', ['draft', 'queued']),
        ])
        if pending:
            pending.write({
                'status': 'cancelled',
                'next_retry_at': False,
                'error_message': False,
            })
        retryable_failed = Message.search([
            ('campaign_id.state', 'in', ['cancelled', 'archived']),
            ('status', '=', 'failed'),
            ('next_retry_at', '!=', False),
        ])
        if retryable_failed:
            retryable_failed.write({'next_retry_at': False})
        _logger.info(
            "WhatsApp cancelled campaign queue repair cancelled=%s retries_stopped=%s",
            len(pending),
            len(retryable_failed),
        )
        return len(pending) + len(retryable_failed)

    @api.model
    def recover_deleted_campaign_messages(
        self,
        source_campaign_id,
        apply=False,
        window_minutes=15,
        expected_message_count=0,
        expected_recipient_count=0,
        pending_action='cancel',
    ):
        """Rebuild a deleted campaign from its detached message rows without sending."""
        try:
            source_campaign_id = int(source_campaign_id)
            window_minutes = max(int(window_minutes or 15), 1)
            expected_message_count = max(int(expected_message_count or 0), 0)
            expected_recipient_count = max(int(expected_recipient_count or 0), 0)
        except (TypeError, ValueError):
            raise UserError(_(
                'Campaign ID, recovery window, and expected counts must be numeric.'
            ))
        if pending_action not in ('cancel', 'resume'):
            raise UserError(_('Pending action must be either cancel or resume.'))

        source = self.sudo().browse(source_campaign_id).exists()
        if not source:
            raise UserError(_('Reference campaign %s was not found.') % source_campaign_id)
        source.ensure_one()

        Message = self.env['whatsapp.message'].sudo()
        domain = [
            ('direction', '=', 'outbound'),
            ('campaign_id', '=', False),
            ('is_campaign_message', '=', True),
            ('account_id', '=', source.account_id.id),
        ]
        if source.partner_ids:
            domain.append(('partner_id', 'in', source.partner_ids.ids))
        candidates = Message.search(domain, order='create_date desc, id desc')

        templates = source.template_id | source.template_id_b
        if templates:
            template_ids = set(templates.ids)
            template_names = set(filter(None, templates.mapped('meta_template_name')))
            template_names.update(filter(None, templates.mapped('name')))
            candidates = candidates.filtered(
                lambda message: message.template_id.id in template_ids
                or message.template_name in template_names
            )

        if not candidates:
            raise UserError(_(
                'No detached campaign messages match reference campaign %s. '
                'Run the WhatsApp module upgrade before recovery.'
            ) % source.display_name)

        # Prefer the immutable provenance left by the deleted campaign. The time
        # window remains a second boundary for legacy rows without provenance.
        anchor_candidate = candidates[0]
        cohort_key = (
            anchor_candidate.campaign_origin_id or 0,
            anchor_candidate.campaign_name_snapshot or '',
        )
        candidates = candidates.filtered(lambda message: (
            message.campaign_origin_id or 0,
            message.campaign_name_snapshot or '',
        ) == cohort_key)
        anchor = candidates[0].create_date
        window_start = anchor - timedelta(minutes=window_minutes)
        messages = candidates.filtered(lambda message: message.create_date >= window_start)
        status_counts = {
            status: len(messages.filtered(lambda message, value=status: message.status == value))
            for status in dict(Message._fields['status'].selection)
        }
        status_counts = {status: count for status, count in status_counts.items() if count}
        quarantine_reason = _(
            'Delivery stopped automatically because the original campaign was deleted.'
        )

        def recipient_key(message):
            phone = False
            try:
                phone = Message._normalize_phone(
                    message.phone_number,
                    account=source.account_id,
                    strict=False,
                )
            except (UserError, ValidationError, TypeError, ValueError):
                phone = ''.join(character for character in (message.phone_number or '') if character.isdigit())
            if phone:
                return ('phone', phone)
            if message.partner_id:
                return ('partner', message.partner_id.id)
            return ('message', message.id)

        recipient_groups = {}
        for message in messages:
            key = recipient_key(message)
            recipient_groups.setdefault(key, Message.browse())
            recipient_groups[key] |= message

        accepted_messages = Message.browse()
        accepted_pending = Message.browse()
        accepted_retryable = Message.browse()
        queue_to_resume = Message.browse()
        duplicate_queue_rows = Message.browse()
        failed_only_recipient_count = 0
        for group in recipient_groups.values():
            accepted = group.filtered(lambda message: (
                bool(message.message_id)
                or message.status in ('sent', 'delivered', 'read')
            ))
            accepted_messages |= accepted
            accepted_pending |= accepted.filtered(
                lambda message: message.status in ('draft', 'queued')
            )
            accepted_retryable |= accepted.filtered(
                lambda message: message.status == 'failed' and message.next_retry_at
            )
            recoverable = group.filtered(lambda message: (
                not message.message_id
                and (
                    message.status in ('draft', 'queued')
                    or (
                        message.status == 'cancelled'
                        and message.error_message == quarantine_reason
                    )
                    or (message.status == 'failed' and message.next_retry_at)
                )
            ))
            if accepted:
                duplicate_queue_rows |= recoverable
            elif recoverable:
                selected = recoverable.sorted(lambda message: message.id)[:1]
                queue_to_resume |= selected
                duplicate_queue_rows |= recoverable - selected
            elif group.filtered(lambda message: message.status == 'failed'):
                failed_only_recipient_count += 1

        unique_recipient_count = len(recipient_groups)
        result = {
            'apply': bool(apply),
            'reference_campaign_id': source.id,
            'reference_campaign': source.display_name,
            'anchor_utc': fields.Datetime.to_string(anchor),
            'first_message_utc': fields.Datetime.to_string(min(messages.mapped('create_date'))),
            'original_campaign_id': cohort_key[0] or False,
            'original_campaign': cohort_key[1] or False,
            'window_minutes': window_minutes,
            'message_count': len(messages),
            'expected_message_count': expected_message_count or False,
            'expected_count_matches': not expected_message_count or len(messages) == expected_message_count,
            'unique_recipient_count': unique_recipient_count,
            'expected_recipient_count': expected_recipient_count or False,
            'expected_recipient_count_matches': (
                not expected_recipient_count
                or unique_recipient_count == expected_recipient_count
            ),
            'duplicate_message_row_count': len(messages) - unique_recipient_count,
            'partner_count': len(messages.mapped('partner_id')),
            'meta_accepted_count': len(messages.filtered('message_id')),
            'accepted_message_count': len(accepted_messages),
            'accepted_retry_stopped_count': len(accepted_retryable),
            'accepted_recipient_count': sum(
                1 for group in recipient_groups.values()
                if group & accepted_messages
            ),
            'recipient_count_to_resume': len(queue_to_resume),
            'duplicate_queue_rows_to_suppress': len(duplicate_queue_rows),
            'failed_only_recipient_count': failed_only_recipient_count,
            'pending_action': pending_action,
            'statuses_before': status_counts,
        }
        if not apply:
            return result
        if expected_message_count and len(messages) != expected_message_count:
            raise UserError(_(
                'Recovery stopped before making changes: matched %(matched)s messages, '
                'but %(expected)s were expected. Adjust the recovery window or reference '
                'campaign and run a dry run again.'
            ) % {
                'matched': len(messages),
                'expected': expected_message_count,
            })
        if expected_recipient_count and unique_recipient_count != expected_recipient_count:
            raise UserError(_(
                'Recovery stopped before making changes: matched %(matched)s unique recipients, '
                'but %(expected)s were expected. Do not bypass this check; review the dry run.'
            ) % {
                'matched': unique_recipient_count,
                'expected': expected_recipient_count,
            })

        if accepted_pending:
            accepted_pending.write({
                'status': 'sent',
                'error_message': False,
                'next_retry_at': False,
            })
        if accepted_retryable:
            accepted_retryable.write({'next_retry_at': False})
        if pending_action == 'resume':
            if queue_to_resume:
                queue_to_resume.write({
                    'status': 'queued',
                    'error_message': False,
                    'next_retry_at': False,
                })
            if duplicate_queue_rows:
                duplicate_queue_rows.write({
                    'status': 'cancelled',
                    'next_retry_at': False,
                    'error_message': _(
                        'Duplicate queue row suppressed during deleted campaign recovery.'
                    ),
                })
        elif queue_to_resume or duplicate_queue_rows:
            (queue_to_resume | duplicate_queue_rows).write({
                'status': 'cancelled',
                'next_retry_at': False,
                'error_message': _(
                    'Unsent work was stopped while recovering the deleted campaign.'
                ),
            })
        anchor_label = fields.Datetime.to_string(anchor)
        recovered = source.copy({
            'name': _('%s (Recovered %s)') % (source.name, anchor_label),
        })
        recovered_state = 'running' if pending_action == 'resume' and queue_to_resume else (
            'completed' if pending_action == 'resume' else 'cancelled'
        )
        recovered.write({
            'state': recovered_state,
            'schedule_type': 'immediate',
            'schedule_date': False,
            'last_batch_at': False,
            'preflight_state': 'warning',
            'preflight_checked_at': fields.Datetime.now(),
            'preflight_report': _(
                'Recovered from a deleted campaign. Accepted delivery history was preserved. '
                '%(pending)s existing pending message(s) were %(action)s; recovery itself '
                'created and sent no messages.'
            ) % {
                'pending': len(queue_to_resume),
                'action': _('reattached for normal queue processing')
                if pending_action == 'resume' else _('cancelled'),
            },
        })
        messages.write({
            'campaign_id': recovered.id,
            'is_campaign_message': True,
        })
        recovered._compute_statistics()
        if recovered.state == 'running':
            recovered._wake_campaign_queue_cron()

        result.update({
            'recovered_campaign_id': recovered.id,
            'recovered_campaign': recovered.display_name,
            'recovered_state': recovered.state,
            'pending_cancelled': len(queue_to_resume | duplicate_queue_rows)
            if pending_action == 'cancel' else 0,
            'pending_resumed': len(queue_to_resume) if pending_action == 'resume' else 0,
            'accepted_pending_normalized': len(accepted_pending),
            'accepted_retries_stopped': len(accepted_retryable),
            'duplicate_queue_rows_suppressed': len(duplicate_queue_rows)
            if pending_action == 'resume' else 0,
        })
        _logger.warning('Recovered deleted WhatsApp campaign: %s', result)
        return result

    def unlink(self):
        """Preserve campaign delivery history; operators should cancel or archive it."""
        ScheduledCampaign = self.env['whatsapp.scheduled.campaign'].sudo()
        protected = self.filtered(
            lambda campaign: campaign.message_ids
            or campaign.participant_ids
            or ScheduledCampaign.search_count([('campaign_id', '=', campaign.id)])
        )
        if protected:
            raise UserError(_(
                'Campaigns with messages, participants, or schedules cannot be deleted. '
                'Cancel or archive them so delivery history and queue ownership remain intact.'
            ))
        return super().unlink()

    def copy_data(self, default=None):
        """Duplicate campaign configuration as a clean, unsent draft."""
        defaults = dict(default or {})
        defaults.update({
            'state': 'draft',
            'schedule_type': 'immediate',
            'schedule_date': False,
            'last_batch_at': False,
            'tracking_campaign_code': False,
            'tracking_entry_keyword': False,
            'conversion_count': 0,
            'excluded_count': 0,
            'exclusion_notes': False,
            'audience_source_count': 0,
            'audience_unique_count': 0,
            'audience_duplicate_count': 0,
            'audience_unlinked_count': 0,
            'audience_missing_phone_count': 0,
            'audience_invalid_phone_count': 0,
            'preflight_state': 'not_run',
            'preflight_checked_at': False,
            'preflight_report': False,
        })
        return super().copy_data(defaults)

    name = fields.Char('Campaign Name', required=True)
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True)
    
    # Campaign type
    campaign_type = fields.Selection([
        ('broadcast', 'Broadcast'),
        ('drip', 'Drip Campaign'),
        ('triggered', 'Event Triggered'),
        ('conversational', 'Conversational'),
    ], string='Campaign Type', default='broadcast', required=True)
    
    # Targeting
    target_type = fields.Selection([
        ('all', 'All Contacts'),
        ('segment', 'Segmented'),
        ('manual', 'Manual Selection'),
        ('crm_stage', 'CRM Stage'),
        ('tags', 'Tags'),
        ('csv', 'CSV Upload (Excel)'),
    ], string='Target Type', default='segment', required=True)
    
    csv_file = fields.Binary('Upload CSV')
    csv_filename = fields.Char('CSV Filename')
    tag_ids = fields.Many2many('res.partner.category', string='Tags')
    
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    segment_id = fields.Many2one('whatsapp.contact.segment', string='Contact Segment')
    crm_stage_id = fields.Many2one('crm.stage', string='CRM Stage')
    domain_filter = fields.Char('Domain Filter', help='Technical domain for filtering contacts')
    
    # Message content
    template_id = fields.Many2one('whatsapp.template', string='Message Template')
    template_header_type = fields.Selection(related='template_id.header_type', string='Template Header Type', readonly=True)
    template_header_media_url = fields.Char(
        'Campaign Header Media URL',
        help='Optional public HTTPS URL or Meta media ID used only for this campaign template header.',
    )
    template_header_media_file = fields.Binary(
        'Campaign Header Media File',
        help='Optional image/video/document used only for this campaign template header.',
    )
    template_header_media_filename = fields.Char('Campaign Header Media Filename')
    message_body = fields.Text('Message Body')
    ai_audience_warning = fields.Text('AI Audience Warning', readonly=True)
    ai_spam_risk = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='AI Spam Risk', readonly=True)
    ai_reply_rule_suggestions = fields.Text('AI Reply Rule Suggestions', readonly=True)
    ai_variant_a = fields.Text('AI Variant A', readonly=True)
    ai_variant_b = fields.Text('AI Variant B', readonly=True)
    
    # A/B Testing
    is_ab_test = fields.Boolean('Enable A/B Testing')
    split_percentage = fields.Float('Split Percentage', default=50.0)
    split_percentage_b = fields.Float('Split Percentage (B)', compute='_compute_split_b', store=True)
    template_id_b = fields.Many2one('whatsapp.template', string='Message Template (B)')
    template_b_header_type = fields.Selection(related='template_id_b.header_type', string='Template B Header Type', readonly=True)
    template_b_header_media_url = fields.Char(
        'Campaign Header Media URL (B)',
        help='Optional public HTTPS URL or Meta media ID used only for Version B template header.',
    )
    template_b_header_media_file = fields.Binary(
        'Campaign Header Media File (B)',
        help='Optional image/video/document used only for Version B template header.',
    )
    template_b_header_media_filename = fields.Char('Campaign Header Media Filename (B)')
    message_body_b = fields.Text('Message Body (B)')
    ab_test_winner = fields.Selection([
        ('a', 'Version A'),
        ('b', 'Version B'),
    ], string='Winner', readonly=True, copy=False)

    @api.depends('split_percentage')
    def _compute_split_b(self):
        for rec in self:
            rec.split_percentage_b = 100.0 - (rec.split_percentage or 50.0)

    # Scheduling
    schedule_type = fields.Selection([
        ('immediate', 'Send Immediately'),
        ('scheduled', 'Schedule'),
    ], string='Schedule', default='immediate', copy=False)
    
    schedule_date = fields.Datetime('Scheduled Date', copy=False)
    last_batch_at = fields.Datetime(
        'Last Batch Sent At',
        readonly=True,
        copy=False,
        index=True,
        help='Internal queue pacing timestamp for the most recently processed campaign batch.',
    )
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', required=True, copy=False)
    
    # Statistics
    total_recipients = fields.Integer('Total Recipients', compute='_compute_statistics', store=True)
    queued_count = fields.Integer('Queued', compute='_compute_statistics', store=True)
    sent_count = fields.Integer('Sent', compute='_compute_statistics', store=True)
    api_accepted_count = fields.Integer('API Accepted', compute='_compute_statistics', store=True)
    delivered_count = fields.Integer('Delivered', compute='_compute_statistics', store=True)
    read_count = fields.Integer('Read', compute='_compute_statistics', store=True)
    failed_count = fields.Integer('Failed Attempts', compute='_compute_statistics', store=True)
    failed_recipient_count = fields.Integer(
        'Failed Recipients', compute='_compute_statistics', store=True,
    )
    duplicate_attempt_count = fields.Integer(
        'Duplicate/Audit Rows', compute='_compute_statistics', store=True,
    )
    
    delivery_rate = fields.Float('Delivery Rate', compute='_compute_statistics', store=True)
    read_rate = fields.Float('Read Rate', compute='_compute_statistics', store=True)
    
    # Relations
    message_ids = fields.One2many('whatsapp.message', 'campaign_id', string='Messages', copy=False)
    step_ids = fields.One2many('whatsapp.campaign.step', 'campaign_id', string='Drip Steps', copy=True)
    participant_ids = fields.One2many('whatsapp.campaign.participant', 'campaign_id', string='Participants', copy=False)
    
    # Analytics
    click_count = fields.Integer('Clicks', compute='_compute_statistics', store=True)
    conversion_count = fields.Integer('Conversions', default=0, copy=False)
    roi = fields.Float('ROI %', compute='_compute_roi')
    
    # Enterprise Logic
    batch_size = fields.Integer('Batch Size', default=50, help="Number of messages to send per batch")
    batch_interval = fields.Integer('Batch Interval (Min)', default=5, help="Minutes between batches")
    flow_id = fields.Many2one('whatsapp.bot.flow', string='Auto-Start Flow', help="Link recipients to this flow upon delivery")
    form_id = fields.Many2one(
        'whatsapp.form',
        string='Campaign Form',
        domain="[('active', '=', True)]",
        help='Optional form used by reply actions and campaign conversion tracking.',
    )
    tracking_source = fields.Char('Source', default='whatsapp')
    tracking_medium = fields.Char('Medium', default='campaign')
    tracking_campaign_code = fields.Char('Campaign Code', copy=False)
    tracking_entry_keyword = fields.Char('Entry Keyword', copy=False)
    tracking_wa_link = fields.Char('wa.me Tracking Link', compute='_compute_tracking_wa_link')
    form_submission_count = fields.Integer('Form Submissions', compute='_compute_conversion_counters')
    payment_action_count = fields.Integer('Payment Actions', compute='_compute_conversion_counters')
    tracked_reply_count = fields.Integer('Tracked Replies', compute='_compute_conversion_counters')

    # Reply handling and audience safety
    reply_rule_ids = fields.One2many('whatsapp.campaign.reply.rule', 'campaign_id', string='Reply Actions', copy=True)
    default_reply_action = fields.Selection([
        ('none', 'No Action'),
        ('start_flow', 'Start Flow'),
        ('send_message', 'Send Message'),
        ('send_form_link', 'Send Form Link'),
        ('send_payment_link', 'Send Payment Link'),
        ('assign_user', 'Assign Agent'),
        ('assign_team_member', 'Assign Team Member'),
        ('assign_tag', 'Assign Tag'),
        ('create_lead', 'Create Lead'),
        ('update_lead_note', 'Create / Update Lead Note'),
        ('set_chat_status', 'Set Chat Status'),
        ('resolve_chat', 'Resolve Chat'),
        ('reopen_chat', 'Reopen Chat'),
    ], default='none', string='Default Free-text Reply Action')
    reply_flow_id = fields.Many2one('whatsapp.bot.flow', string='Default Reply Flow')
    reply_response_message = fields.Text('Default Reply Message')
    reply_assign_user_id = fields.Many2one('res.users', string='Default Reply Agent')
    reply_assign_team_member_id = fields.Many2one('whatsapp.team.member', string='Default Reply Team Member')
    reply_assign_tag_id = fields.Many2one('res.partner.category', string='Default Reply Tag')
    reply_form_id = fields.Many2one('whatsapp.form', string='Default Reply Form', domain="[('active', '=', True)]")
    reply_chat_status = fields.Selection([
        ('open', 'Open / Pending'),
        ('snoozed', 'Snoozed'),
        ('resolved', 'Resolved'),
    ], string='Default Reply Chat Status')
    reply_lead_note = fields.Text('Default Reply Lead Note')
    exclude_recently_contacted = fields.Boolean('Exclude Recently Contacted', default=True)
    recent_contact_days = fields.Integer('Recent Contact Window (days)', default=7)
    frequency_cap_days = fields.Integer('Frequency Cap (days)', default=0)
    excluded_count = fields.Integer('Excluded', readonly=True, default=0, copy=False)
    exclusion_notes = fields.Text('Audience Exclusion Notes', readonly=True, copy=False)
    audience_source_count = fields.Integer('Matched Contact Rows', readonly=True, copy=False)
    audience_unique_count = fields.Integer('Unique Contact Records', readonly=True, copy=False)
    audience_duplicate_count = fields.Integer('Duplicate Rows', readonly=True, copy=False)
    audience_unlinked_count = fields.Integer('Unresolved Contacts', readonly=True, copy=False)
    audience_missing_phone_count = fields.Integer('Missing Phone', readonly=True, copy=False)
    audience_invalid_phone_count = fields.Integer('Invalid Phone', readonly=True, copy=False)
    preview_partner_id = fields.Many2one('res.partner', string='Preview Recipient', copy=False)
    preflight_state = fields.Selection([
        ('not_run', 'Not Run'),
        ('passed', 'Passed'),
        ('warning', 'Passed with Warnings'),
        ('failed', 'Failed'),
    ], string='Preflight', default='not_run', readonly=True, copy=False)
    preflight_checked_at = fields.Datetime('Preflight Checked At', readonly=True, copy=False)
    preflight_report = fields.Text('Preflight Report', readonly=True, copy=False)
    recipient_preview_html = fields.Html('Recipient Preview', compute='_compute_recipient_preview_html')
    recipient_preview_text = fields.Text('Recipient Preview Text', compute='_compute_recipient_preview_html')
    pre_send_checklist_html = fields.Html('Pre-send Checklist', compute='_compute_pre_send_checklist_html')
    pre_send_checklist_text = fields.Text('Pre-send Checklist Text', compute='_compute_pre_send_checklist_html')
    
    @api.depends(
        'partner_ids', 'message_ids.status', 'message_ids.direction',
        'message_ids.message_id', 'message_ids.phone_number', 'message_ids.partner_id',
        'message_ids.button_text', 'message_ids.button_payload', 'message_ids.list_item_id',
    )
    def _compute_statistics(self):
        for record in self:
            outbound_messages = record.message_ids.filtered(lambda m: m.direction == 'outbound')
            inbound_interactions = record.message_ids.filtered(
                lambda message: message.direction == 'inbound'
                and (message.button_text or message.button_payload or message.list_item_id)
            )
            record.total_recipients = len(record.partner_ids)
            recipient_outcomes = {}
            for message in outbound_messages:
                key = self._message_recipient_key(message)
                outcome = recipient_outcomes.setdefault(key, {
                    'api_accepted': False,
                    'failed': False,
                    'successful': False,
                    'pending': False,
                })
                outcome['api_accepted'] |= bool(message.message_id)
                outcome['failed'] |= message.status == 'failed'
                outcome['successful'] |= message.status in ('sent', 'delivered', 'read')
                outcome['pending'] |= message.status in ('draft', 'queued')
            record.queued_count = len(outbound_messages.filtered(lambda m: m.status in ['draft', 'queued']))
            record.sent_count = len(outbound_messages.filtered(lambda m: m.status in ['sent', 'delivered', 'read']))
            record.api_accepted_count = sum(
                1 for outcome in recipient_outcomes.values() if outcome['api_accepted']
            )
            record.delivered_count = len(outbound_messages.filtered(lambda m: m.status in ['delivered', 'read']))
            record.read_count = len(outbound_messages.filtered(lambda m: m.status == 'read'))
            record.failed_count = len(outbound_messages.filtered(lambda m: m.status == 'failed'))
            record.failed_recipient_count = sum(
                1 for outcome in recipient_outcomes.values()
                if outcome['failed'] and not outcome['successful'] and not outcome['pending']
            )
            record.duplicate_attempt_count = max(
                len(outbound_messages) - len(recipient_outcomes), 0,
            )
            record.click_count = len(inbound_interactions)
            
            # Rates
            if record.total_recipients > 0:
                record.delivery_rate = record.delivered_count / record.total_recipients
                record.read_rate = record.read_count / record.total_recipients
            else:
                record.delivery_rate = 0.0
                record.read_rate = 0.0

    @api.model
    def _message_recipient_key(self, message):
        phone = ''.join(character for character in (message.phone_number or '') if character.isdigit())
        if phone:
            return ('phone', phone)
        if message.partner_id:
            return ('partner', message.partner_id.id)
        return ('message', message.id)
    
    @api.depends('conversion_count', 'sent_count')
    def _compute_roi(self):
        for record in self:
            if record.sent_count > 0:
                record.roi = record.conversion_count / record.sent_count
            else:
                record.roi = 0.0

    @api.depends('account_id.phone_number', 'tracking_entry_keyword', 'tracking_campaign_code')
    def _compute_tracking_wa_link(self):
        for record in self:
            phone = ''.join(ch for ch in (record.account_id.phone_number or '') if ch.isdigit())
            keyword = (record.tracking_entry_keyword or record.tracking_campaign_code or '').strip()
            if phone and keyword:
                record.tracking_wa_link = "https://wa.me/%s?text=%s" % (phone, quote(keyword))
            elif phone:
                record.tracking_wa_link = "https://wa.me/%s" % phone
            else:
                record.tracking_wa_link = False

    def _compute_conversion_counters(self):
        Submission = self.env['whatsapp.form.submission'].sudo()
        for record in self:
            record.form_submission_count = Submission.search_count([('campaign_id', '=', record.id)])
            linked_reply_count = len(record.message_ids.filtered(lambda msg: msg.direction == 'inbound'))
            handled_reply_count = sum(record.reply_rule_ids.mapped('handled_count'))
            record.tracked_reply_count = max(linked_reply_count, handled_reply_count)
            record.payment_action_count = sum(record.reply_rule_ids.filtered(lambda r: r.action_type == 'send_payment_link').mapped('handled_count'))

    @api.depends(
        'preview_partner_id', 'template_id', 'template_id.body', 'template_id.header_type',
        'template_id.header_media_file', 'template_id.header_media_url', 'template_id.header_media_filename',
        'template_header_media_file', 'template_header_media_url', 'template_header_media_filename',
        'template_id.header_text', 'template_id.footer', 'template_id.has_buttons',
        'template_id.button_type', 'template_id.button_text_1', 'template_id.button_text_2',
        'template_id.button_text_3', 'template_id.cta_url_text', 'template_id.cta_phone_text',
        'template_id.copy_code_example', 'template_id.variable_ids.sample_value', 'message_body',
    )
    def _compute_recipient_preview_html(self):
        for record in self:
            partner = record.preview_partner_id or record.partner_ids[:1]
            template = record.template_id
            if template:
                media_kwargs = record._campaign_header_media_kwargs('a')
                record.recipient_preview_html = template._render_customer_preview_html(
                    partner=partner,
                    shell=True,
                    compact=True,
                    **media_kwargs,
                )
                record.recipient_preview_text = template._render_customer_preview_text(
                    partner=partner,
                    **media_kwargs,
                )
                continue
            else:
                body = record._render_body_for_partner(record.message_body or '', partner) if partner else (record.message_body or '')
                record.recipient_preview_html = self.env['whatsapp.template']._render_text_preview_html(
                    body,
                    partner=partner,
                    shell=True,
                )
                record.recipient_preview_text = body or 'Add message body or select an approved template.'

    @api.depends(
        'account_id', 'partner_ids', 'excluded_count', 'exclusion_notes', 'template_id',
        'account_id.active', 'account_id.status',
        'template_id.header_type', 'template_id.header_media_file', 'template_id.header_media_url',
        'template_header_media_file', 'template_header_media_url', 'template_header_media_filename',
        'template_id.has_buttons', 'template_id.button_type', 'template_id.button_text_1',
        'template_id.button_text_2', 'template_id.button_text_3', 'message_body',
        'reply_rule_ids.active', 'reply_rule_ids.match_type', 'reply_rule_ids.match_value',
        'reply_rule_ids.action_type', 'default_reply_action', 'form_id', 'reply_form_id', 'tracking_entry_keyword',
        'tracking_campaign_code', 'tracking_wa_link', 'account_id.payment_link_mode',
    )
    def _compute_pre_send_checklist_html(self):
        for record in self:
            items = []
            text_items = []

            def add(ok, label, detail='', warn=False):
                icon = 'fa-check-circle text-success' if ok else ('fa-warning text-warning' if warn else 'fa-times-circle text-danger')
                marker = 'OK' if ok else ('CHECK' if warn else 'FIX')
                text_items.append("%s - %s%s" % (marker, label, (": %s" % detail) if detail else ""))
                items.append(
                    "<li style='display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;'>"
                    "<i class='fa %s' style='margin-top:2px;'></i>"
                    "<span><strong>%s</strong>%s</span></li>"
                    % (
                        icon,
                        html_escape(label),
                        f"<br/><small style='color:#667781;'>{html_escape(detail)}</small>" if detail else '',
                    )
                )

            add(bool(record.partner_ids), 'Recipients loaded', f"{len(record.partner_ids)} recipient(s) ready.")
            add(
                True,
                'Recipient name personalization',
                'Template name variables use the linked Odoo Contact Name; the Meta WhatsApp profile name labels the Team Inbox separately.',
            )
            if record.excluded_count:
                add(True, 'Audience exclusions applied', record.exclusion_notes or f"{record.excluded_count} excluded.", warn=True)
            else:
                add(True, 'No current exclusions', 'Load recipients to refresh opt-out, recent-contact, and frequency checks.')

            if record.template_id:
                template = record.template_id
                media_needed = template.header_type in ('image', 'video', 'document')
                media_ready = record._template_media_ready(template, 'a')
                add(
                    media_ready,
                    'Template media header',
                    (
                        f"{template.header_type.title()} header is ready."
                        if media_ready and media_needed else
                        "No media header required."
                        if not media_needed else
                        f"{template.header_type.title()} header requires a template file/URL or campaign header media override."
                    ),
                )
                add(template.status == 'approved', 'Template approval', f"Status: {template.status or 'unknown'}")
                if template.has_buttons and template.button_type == 'quick_reply':
                    buttons = [b for b in [template.button_text_1, template.button_text_2, template.button_text_3] if b]
                    active_rules = record.reply_rule_ids.filtered(lambda r: r.active)
                    covered = {
                        (rule.match_value or '').strip().lower()
                        for rule in active_rules
                        if rule.match_type in ('button_text', 'button_payload')
                    }
                    missing = [btn for btn in buttons if btn.strip().lower() not in covered]
                    add(
                        not missing,
                        'Template reply actions',
                        'All quick replies are mapped.' if not missing else 'Missing mappings: %s' % ', '.join(missing),
                        warn=bool(missing),
                    )
                else:
                    has_reply_handling = bool(record.default_reply_action and record.default_reply_action != 'none') or bool(record.reply_rule_ids.filtered('active'))
                    add(
                        has_reply_handling,
                        'Reply handling',
                        'Default or rule-based reply handling is configured.' if has_reply_handling else 'Optional: configure what happens when a customer replies.',
                        warn=True,
                    )
            else:
                add(
                    bool((record.message_body or '').strip()),
                    'Message content',
                    (
                        'Plain text is limited to an open customer-service window; use an approved template for proactive broadcasts.'
                        if record.message_body else 'Add an approved template or message body.'
                    ),
                    warn=bool(record.message_body),
                )

            account_ready = bool(
                record.account_id
                and record.account_id.active
                and record.account_id.status == 'connected'
            )
            add(
                account_ready,
                'WhatsApp account connection',
                (
                    'Connected and ready for Meta API requests.'
                    if account_ready
                    else 'Open Configuration, test the API connection, and confirm the account is Connected.'
                ),
            )

            policy = self.env['whatsapp.compliance.policy'].sudo().search([
                ('account_id', '=', record.account_id.id),
                ('active', '=', True),
            ], limit=1) if record.account_id else False
            add(True, 'Compliance policy', policy.name if policy else 'No active account policy found; message-level checks still run at send time.', warn=not bool(policy))
            quiet = False
            if record.account_id and policy:
                probe = self.env['whatsapp.message'].new({
                    'account_id': record.account_id.id,
                    'phone_number': '0000000000',
                    'direction': 'outbound',
                    'message_type': 'text',
                    'campaign_id': record.id,
                    'is_automated': True,
                })
                quiet = probe._current_quiet_hour(policy)
            add(
                not bool(quiet),
                'Quiet hours',
                f"Quiet hours active now: {quiet.display_name}" if quiet else 'No active quiet-hour block detected right now.',
                warn=bool(quiet),
            )
            form_needed = bool(record.reply_rule_ids.filtered(lambda r: r.active and r.action_type == 'send_form_link') or record.default_reply_action == 'send_form_link')
            selected_form = record.form_id or record.reply_form_id or (record.account_id.default_form_id if record.account_id else False)
            add(
                not form_needed or bool(selected_form),
                'Form link readiness',
                selected_form.display_name if selected_form else 'A form-link reply action needs a campaign, default reply, or account default form.',
                warn=form_needed and not bool(selected_form),
            )
            payment_needed = bool(record.reply_rule_ids.filtered(lambda r: r.active and r.action_type == 'send_payment_link') or record.default_reply_action == 'send_payment_link')
            payment_ready = bool(record.account_id and record.account_id.payment_link_mode != 'disabled')
            add(
                not payment_needed or payment_ready,
                'Payment link readiness',
                'Payment links use account mode: %s' % (record.account_id.payment_link_mode if record.account_id else 'not configured'),
                warn=payment_needed and not payment_ready,
            )
            add(
                bool(record.tracking_wa_link),
                'Click-to-WhatsApp tracking link',
                record.tracking_wa_link or 'Set a campaign code or entry keyword to generate a wa.me link.',
                warn=True,
            )
            record.pre_send_checklist_html = (
                "<div class='alert alert-light border mb-0'><ul style='list-style:none;padding-left:0;margin:0;'>%s</ul></div>"
            ) % ''.join(items)
            record.pre_send_checklist_text = "\n".join(text_items)

    def action_sync_template_reply_buttons(self):
        """Create/update reply rules from the selected quick-reply template buttons."""
        self.ensure_one()
        if not self.template_id or not self.template_id.has_buttons or self.template_id.button_type != 'quick_reply':
            return False
        existing_by_value = {rule.match_value: rule for rule in self.reply_rule_ids}
        sequence = 10
        for text in [self.template_id.button_text_1, self.template_id.button_text_2, self.template_id.button_text_3]:
            if not text:
                continue
            vals = {
                'name': text,
                'sequence': sequence,
                'match_type': 'button_text',
                'match_value': text,
            }
            if text in existing_by_value:
                existing_by_value[text].write(vals)
            else:
                self.env['whatsapp.campaign.reply.rule'].create(dict(vals, campaign_id=self.id))
            sequence += 10
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reply Buttons Synced',
                'message': 'Template quick replies are available in Reply Actions.',
                'type': 'success',
            },
        }

    def action_generate_tracking_keyword(self):
        for record in self:
            code = (record.tracking_campaign_code or record.name or 'campaign').lower()
            clean = ''.join(ch if ch.isalnum() else '_' for ch in code).strip('_')
            clean = '_'.join(part for part in clean.split('_') if part)
            record.tracking_campaign_code = record.tracking_campaign_code or clean[:48]
            record.tracking_entry_keyword = record.tracking_entry_keyword or ("%s_start" % (clean[:42] or 'wa'))
        return True

    def action_export_failed_recipients(self):
        self.ensure_one()
        failed = self.message_ids.filtered(lambda msg: msg.status == 'failed')
        if not failed:
            raise UserError(_("There are no failed recipients to export."))
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['partner', 'phone', 'message_type', 'status', 'error'])
        for msg in failed:
            writer.writerow([
                msg.partner_id.display_name if msg.partner_id else '',
                msg.phone_number or '',
                msg.message_type or '',
                msg.status or '',
                msg.error_message or '',
            ])
        data = base64.b64encode(buffer.getvalue().encode('utf-8')).decode('ascii')
        attachment = self.env['ir.attachment'].sudo().create({
            'name': '%s_failed_recipients.csv' % (self.name or 'campaign'),
            'type': 'binary',
            'datas': data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    @api.constrains(
        'split_percentage', 'schedule_type', 'schedule_date', 'campaign_type', 'step_ids',
        'target_type', 'segment_id', 'domain_filter', 'partner_ids', 'tag_ids', 'csv_file',
        'template_id', 'message_body', 'is_ab_test', 'template_id_b', 'message_body_b',
        'batch_size', 'batch_interval',
    )
    def _check_campaign_configuration(self):
        for record in self:
            if record.batch_size <= 0:
                raise ValidationError("Batch size must be greater than zero.")
            if record.batch_interval < 0:
                raise ValidationError("Batch interval cannot be negative.")
            if record.split_percentage < 0 or record.split_percentage > 100:
                raise ValidationError("A/B split percentage must be between 0 and 100.")
            if record.is_ab_test and (record.split_percentage <= 0 or record.split_percentage >= 100):
                raise ValidationError("A/B testing requires both versions to receive recipients. Use a split between 1 and 99.")

            strict = (
                self.env.context.get('strict_campaign_validation')
                or record.state in ('scheduled', 'running', 'completed')
            )
            if not strict:
                continue

            if record.schedule_type == 'scheduled' and not record.schedule_date:
                raise ValidationError("Scheduled campaigns require a schedule date.")
            if record.campaign_type == 'drip' and not record.step_ids:
                raise ValidationError("Drip campaigns require at least one step.")
            if record.campaign_type == 'broadcast':
                record._check_recipient_configuration()
                record._check_message_configuration()

    def _check_recipient_configuration(self):
        self.ensure_one()
        if self.target_type == 'segment' and not (self.segment_id or (self.domain_filter or '').strip()):
            raise ValidationError("Segmented campaigns require a contact segment or a domain filter.")
        if self.target_type == 'manual' and not self.partner_ids:
            raise ValidationError("Manual campaigns require at least one recipient.")
        if self.target_type == 'tags' and not self.tag_ids:
            raise ValidationError("Tag campaigns require at least one tag.")
        if self.target_type == 'csv' and not self.csv_file:
            raise ValidationError("CSV campaigns require an uploaded audience CSV.")

    def _campaign_header_media_kwargs(self, version='a'):
        self.ensure_one()
        if version == 'b':
            return {
                'header_media_file': self.template_b_header_media_file or False,
                'header_media_filename': self.template_b_header_media_filename or False,
                'header_media_url': self.template_b_header_media_url or False,
            }
        return {
            'header_media_file': self.template_header_media_file or False,
            'header_media_filename': self.template_header_media_filename or False,
            'header_media_url': self.template_header_media_url or False,
        }

    def _effective_header_media_kwargs(self, template, version='a'):
        self.ensure_one()
        if not template or template.header_type not in ('image', 'video', 'document'):
            return {}
        media_kwargs = self._campaign_header_media_kwargs(version)
        if media_kwargs.get('header_media_file') or media_kwargs.get('header_media_url'):
            return media_kwargs
        if template.header_media_url and template._is_send_media_reference(template.header_media_url):
            return {
                'header_media_url': template.header_media_url,
                'header_media_filename': template.header_media_filename or template._header_media_upload_filename(template.header_type),
            }
        if template.header_media_file:
            return {
                'header_media_file': template.header_media_file,
                'header_media_filename': template.header_media_filename or template._header_media_upload_filename(template.header_type),
            }
        return template._latest_send_header_media_kwargs(account=self.account_id)

    def _template_media_ready(self, template, version='a'):
        self.ensure_one()
        if not template or template.header_type not in ('image', 'video', 'document'):
            return True
        media_kwargs = self._effective_header_media_kwargs(template, version)
        return bool(media_kwargs.get('header_media_url') or media_kwargs.get('header_media_file'))

    def _prepare_shared_header_media(self, template, version='a'):
        """Resolve campaign header media once so every recipient reuses one reference."""
        self.ensure_one()
        if not template or template.header_type not in ('image', 'video', 'document'):
            return {}
        media_kwargs = self._effective_header_media_kwargs(template, version)
        filename = (
            media_kwargs.get('header_media_filename')
            or template.header_media_filename
            or template._header_media_upload_filename(template.header_type)
        )
        media_value = template._resolve_header_media_value(
            template.header_type,
            media_file=media_kwargs.get('header_media_file'),
            media_filename=filename,
            media_url=media_kwargs.get('header_media_url'),
            account=self.account_id,
        )
        if self.account_id._is_private_meta_media_url(media_value):
            media_value = self.account_id._download_and_upload_private_media(
                media_value,
                template.header_type,
                filename,
            )
        return {
            'header_media_url': media_value,
            'header_media_filename': filename,
        }

    def _check_template_ready_for_campaign(self, template, label, version='a'):
        if not template:
            return
        if not template.active:
            raise ValidationError(f"{label} template is archived and cannot be used in a campaign.")
        if template.account_id and self.account_id and template.account_id != self.account_id:
            raise ValidationError(f"{label} template must belong to the selected WhatsApp account.")
        if template.status != 'approved':
            raise ValidationError(f"{label} template must be approved before it can be used in a campaign.")
        template._validate_variable_structure()
        if not self._template_media_ready(template, version=version):
            raise ValidationError(
                f"{label} template requires a send-ready {template.header_type} header. "
                "Upload campaign header media, use a valid Meta media ID, or configure a public HTTPS URL."
            )

    def _check_variant_message(self, label, template, body, version='a'):
        if template:
            self._check_template_ready_for_campaign(template, label, version=version)
            return
        if not (body or '').strip():
            raise ValidationError(f"{label} requires either an approved template or a text message.")

    def _check_message_configuration(self):
        self.ensure_one()
        primary_label = "Version A" if self.is_ab_test else "Campaign message"
        self._check_variant_message(primary_label, self.template_id, self.message_body, version='a')
        if self.is_ab_test:
            self._check_variant_message("Version B", self.template_id_b, self.message_body_b, version='b')
        self._check_reply_rule_configuration()

    def _check_account_ready_for_send(self):
        self.ensure_one()
        if not self.account_id.active:
            raise ValidationError('The selected WhatsApp account is inactive.')
        if self.account_id.status != 'connected':
            raise ValidationError(
                'The selected WhatsApp account is not connected. Test the API connection '
                'in Configuration before launching this campaign.'
            )

    def _check_reply_rule_configuration(self):
        self.ensure_one()
        for rule in self.reply_rule_ids.filtered('active'):
            rule._validate_configuration()
        default_required = {
            'start_flow': (self.reply_flow_id, "Default reply action 'Start Flow' needs a flow."),
            'send_message': ((self.reply_response_message or '').strip(), "Default reply action 'Send Message' needs a response message."),
            'send_form_link': (self.reply_form_id or self.form_id or self.account_id.default_form_id, "Default reply action 'Send Form Link' needs a form."),
            'send_payment_link': (self.account_id and self.account_id.payment_link_mode != 'disabled', "Default reply action 'Send Payment Link' needs payment links enabled on the account."),
            'assign_user': (self.reply_assign_user_id, "Default reply action 'Assign Agent' needs an agent."),
            'assign_team_member': (self.reply_assign_team_member_id, "Default reply action 'Assign Team Member' needs a team member."),
            'assign_tag': (self.reply_assign_tag_id, "Default reply action 'Assign Tag' needs a tag."),
            'set_chat_status': (self.reply_chat_status, "Default reply action 'Set Chat Status' needs a chat status."),
            'update_lead_note': ((self.reply_lead_note or '').strip(), "Default reply action 'Create / Update Lead Note' needs a lead note."),
        }
        value, message = default_required.get(self.default_reply_action or 'none', (True, ''))
        if not value:
            raise ValidationError(message)

    def _render_body_for_partner(self, body, partner, template=False):
        if not body:
            return ''
        body = body.replace('{{name}}', partner.name or '')
        body = body.replace('{{company}}', partner.company_name or '' if hasattr(partner, 'company_name') else '')
        if template:
            sorted_variables = template.variable_ids.sorted(lambda var: var.sequence or 0)
            for idx, var in enumerate(sorted_variables, start=1):
                val = template._resolve_variable_value(var, partner)
                body = body.replace(f'{{{{{idx}}}}}', str(val))
        return body

    def _template_payload_for_partner(self, template, partner, version='a', media_kwargs=None):
        media_kwargs = media_kwargs if media_kwargs is not None else self._effective_header_media_kwargs(template, version)
        return template._prepare_send_payload(
            partner=partner,
            account=self.account_id,
            **media_kwargs,
        )

    def _partner_phone_domain(self):
        domain = [('phone', '!=', False)]
        if 'mobile' in self.env['res.partner']._fields:
            domain = ['|', ('mobile', '!=', False)] + domain
        return domain

    def _qualify_recipient_phones(self, partners):
        valid = self.env['res.partner']
        missing = self.env['res.partner']
        invalid = self.env['res.partner']
        normalizer = self.env['whatsapp.message']
        for partner in partners:
            phone = getattr(partner, 'mobile', False) or partner.phone
            if not phone:
                missing |= partner
                continue
            try:
                normalizer._normalize_phone(phone, account=self.account_id, strict=True)
                valid |= partner
            except ValidationError:
                invalid |= partner
        return valid, missing, invalid

    def _normalized_recipient_phones(self, partners):
        self.ensure_one()
        normalizer = self.env['whatsapp.message']
        result = {}
        for partner in partners:
            phone = getattr(partner, 'mobile', False) or partner.phone
            if phone:
                result[partner.id] = normalizer._normalize_phone(phone, account=self.account_id)
        return result

    def _partners_with_recent_campaign_activity(self, partners, cutoff, campaign_only=False):
        """Match actual sends by partner or normalized phone, never queued-only rows."""
        self.ensure_one()
        if not partners:
            return self.env['res.partner']
        phone_by_partner = self._normalized_recipient_phones(partners)
        phones = list({phone for phone in phone_by_partner.values() if phone})
        identity_domain = ['|', ('partner_id', 'in', partners.ids), ('phone_number', 'in', phones)]
        domain = identity_domain + [
            ('direction', '=', 'outbound'),
            ('status', 'in', ['sent', 'delivered', 'read']),
            '|',
                ('sent_date', '>=', cutoff),
                '&', ('sent_date', '=', False), ('create_date', '>=', cutoff),
        ]
        if campaign_only:
            domain.append(('campaign_id', '!=', False))
        history = self.env['whatsapp.message'].sudo().search(domain)
        history_partner_ids = set(history.mapped('partner_id').ids)
        history_phones = {
            self.env['whatsapp.message']._normalize_phone(message.phone_number, account=self.account_id)
            for message in history
            if message.phone_number
        }
        return partners.filtered(
            lambda partner: partner.id in history_partner_ids
            or phone_by_partner.get(partner.id) in history_phones
        )

    def _deduplicate_recipient_phones(self, partners):
        """Keep one eligible recipient per normalized WhatsApp number."""
        self.ensure_one()
        phone_by_partner = self._normalized_recipient_phones(partners)
        seen = set()
        unique = self.env['res.partner']
        duplicates = self.env['res.partner']
        for partner in partners:
            phone = phone_by_partner.get(partner.id)
            if phone and phone in seen:
                duplicates |= partner
            else:
                if phone:
                    seen.add(phone)
                unique |= partner
        return unique, duplicates

    def action_load_recipients(self):
        """Load, reconcile, qualify, and explain the campaign audience."""
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        Contact = self.env['whatsapp.contact'].sudo()
        ContactTag = self.env['whatsapp.contact.tag'].sudo()

        legacy_tags = ContactTag.search([('partner_category_id', '=', False)])
        if legacy_tags:
            legacy_tags._ensure_partner_categories()
        unlinked_contacts = Contact.search([
            ('partner_id', '=', False),
            '|', ('phone_number', '!=', False), ('email', '!=', False),
        ])
        if unlinked_contacts:
            unlinked_contacts._reconcile_partner_links()

        source_contacts = Contact.browse()
        if self.target_type == 'all':
            partners = Partner.search(self._partner_phone_domain())
        elif self.target_type == 'segment' and self.domain_filter:
            try:
                custom_domain = safe_eval(self.domain_filter)
                if not isinstance(custom_domain, (list, tuple)):
                    raise ValueError("Domain filter must be a list or tuple.")
            except Exception as e:
                raise UserError(f"Invalid recipient domain filter: {e}")
            partners = Partner.search(list(custom_domain))
        elif self.target_type == 'segment' and self.segment_id:
            self.segment_id.action_refresh_contacts()
            partners = self.segment_id.contact_ids
        elif self.target_type == 'manual':
            partners = self.partner_ids
        elif self.target_type == 'crm_stage' and 'crm.lead' in self.env.registry.models:
            lead_domain = [('partner_id', '!=', False)]
            if self.crm_stage_id:
                lead_domain.append(('stage_id', '=', self.crm_stage_id.id))
            else:
                lead_domain.append(('stage_id', '!=', False))
            leads = self.env['crm.lead'].sudo().search(lead_domain)
            partners = leads.mapped('partner_id')
        elif self.target_type == 'tags' and self.tag_ids:
            matching_contact_tags = ContactTag.search([
                ('partner_category_id', 'in', self.tag_ids.ids),
            ])
            for tag_name in self.tag_ids.mapped('name'):
                matching_contact_tags |= ContactTag.search([('name', '=ilike', tag_name)])
            if matching_contact_tags:
                source_contacts = Contact.search([('tag_ids', 'in', matching_contact_tags.ids)])
                still_unlinked = source_contacts.filtered(lambda contact: not contact.partner_id)
                if still_unlinked:
                    still_unlinked._reconcile_partner_links()
            partners = (
                Partner.search([('category_id', 'in', self.tag_ids.ids)])
                | source_contacts.mapped('partner_id')
            )
        elif self.target_type == 'csv' and self.csv_file:
            import base64
            import csv
            import io
            
            try:
                file_content = base64.b64decode(self.csv_file).decode('utf-8', errors='ignore')
                reader = csv.DictReader(io.StringIO(file_content))
                
                # Check if it has a phone column
                if not reader.fieldnames or not any(f.lower() in ['phone', 'mobile', 'whatsapp'] for f in reader.fieldnames):
                    raise ValueError("CSV must contain a column named 'Phone' or 'Mobile'")
                
                partner_ids = []
                for row in reader:
                    # Case insensitive dict get
                    row_lower = {k.lower().strip(): v for k, v in row.items() if k}
                    phone = row_lower.get('phone') or row_lower.get('mobile') or row_lower.get('whatsapp')
                    name = row_lower.get('name') or phone
                    
                    if phone:
                        phone = self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id)
                        partner_domain = [('phone', '=', phone)]
                        if 'mobile' in self.env['res.partner']._fields:
                            partner_domain = ['|', ('phone', '=', phone), ('mobile', '=', phone)]
                        partner = Partner.search(partner_domain, limit=1)
                        if not partner:
                            create_vals = {'name': name, 'phone': phone}
                            if 'mobile' in self.env['res.partner']._fields:
                                create_vals['mobile'] = phone
                            partner = Partner.create(create_vals)
                        partner_ids.append(partner.id)
                
                partners = Partner.browse(list(dict.fromkeys(partner_ids)))
            except Exception as e:
                from odoo.exceptions import UserError
                raise UserError(f"Error parsing CSV: {str(e)}")
        else:
            partners = self.env['res.partner']

        source_partners = partners
        source_count = len(source_partners)
        unique_contact_count = len(source_partners)
        duplicate_count = 0
        unlinked_count = 0
        if source_contacts:
            linked_source_partners = source_contacts.mapped('partner_id')
            additional_partners = source_partners - linked_source_partners
            source_count = len(source_contacts) + len(additional_partners)
            unique_contact_count = len(source_partners)
            unlinked_count = len(source_contacts.filtered(lambda contact: not contact.partner_id))
            duplicate_count = max(0, len(source_contacts) - len(linked_source_partners) - unlinked_count)

        partners, missing_phone, invalid_phone = self._qualify_recipient_phones(source_partners)
        missing_phone.write({'whatsapp_last_exclusion_reason': 'Missing phone number'})
        invalid_phone.write({'whatsapp_last_exclusion_reason': 'Invalid WhatsApp phone number'})

        # Enforce compliance: Exclude partners who have a linked opted-out whatsapp.contact or have whatsapp_opt_in = False
        original_partners = partners
        exclusion_notes = []
        opted_out = self.env['whatsapp.contact'].sudo().search([
            ('partner_id', 'in', partners.ids),
            ('opt_in', '=', False)
        ]).mapped('partner_id')
        partners = partners.filtered(lambda p: p.whatsapp_opt_in)
        if opted_out:
            partners = partners - opted_out
            exclusion_notes.append(f'Opted out/DND: {len(opted_out)}')
        if self.exclude_recently_contacted and self.recent_contact_days > 0 and partners:
            cutoff = fields.Datetime.now() - timedelta(days=self.recent_contact_days)
            recent_partners = self._partners_with_recent_campaign_activity(partners, cutoff)
            if recent_partners:
                partners = partners - recent_partners
                exclusion_notes.append(f'Recently contacted ({self.recent_contact_days}d): {len(recent_partners)}')
        if self.frequency_cap_days > 0 and partners:
            cutoff = fields.Datetime.now() - timedelta(days=self.frequency_cap_days)
            capped_partners = self._partners_with_recent_campaign_activity(
                partners,
                cutoff,
                campaign_only=True,
            )
            if capped_partners:
                partners = partners - capped_partners
                exclusion_notes.append(f'Campaign frequency cap ({self.frequency_cap_days}d): {len(capped_partners)}')

        partners, duplicate_phone_partners = self._deduplicate_recipient_phones(partners)
        if duplicate_phone_partners:
            duplicate_phone_partners.write({
                'whatsapp_last_exclusion_reason': 'Duplicate normalized WhatsApp phone number',
            })
            duplicate_count += len(duplicate_phone_partners)
            exclusion_notes.append(f'Duplicate WhatsApp numbers merged: {len(duplicate_phone_partners)}')

        compliance_excluded = original_partners - partners
        if compliance_excluded:
            compliance_excluded.write({
                'whatsapp_last_exclusion_reason': '; '.join(exclusion_notes) or 'Excluded by campaign audience rules',
            })
        filtered_excluded = compliance_excluded - duplicate_phone_partners
        excluded_count = (
            duplicate_count
            + unlinked_count
            + len(missing_phone)
            + len(invalid_phone)
            + len(filtered_excluded)
        )
        audience_notes = [
            f'Matched contact rows: {source_count}',
            f'Unique contact records: {unique_contact_count}',
        ]
        if duplicate_count:
            audience_notes.append(f'Duplicate rows merged: {duplicate_count}')
        if unlinked_count:
            audience_notes.append(f'Unresolved contact links: {unlinked_count}')
        if missing_phone:
            audience_notes.append(f'Missing phone number: {len(missing_phone)}')
        if invalid_phone:
            audience_notes.append(f'Invalid WhatsApp phone number: {len(invalid_phone)}')
        audience_notes.extend(exclusion_notes)
        audience_notes.append(f'Final sendable recipients: {len(partners)}')

        audience_vals = {
            'partner_ids': [(6, 0, partners.ids)],
            'excluded_count': excluded_count,
            'exclusion_notes': '\n'.join(audience_notes),
            'audience_source_count': source_count,
            'audience_unique_count': unique_contact_count,
            'audience_duplicate_count': duplicate_count,
            'audience_unlinked_count': unlinked_count,
            'audience_missing_phone_count': len(missing_phone),
            'audience_invalid_phone_count': len(invalid_phone),
        }
        if not self.env.context.get('preserve_campaign_preflight'):
            audience_vals.update({
                'preflight_state': 'not_run',
                'preflight_checked_at': False,
                'preflight_report': False,
            })
        self.write(audience_vals)
        if not partners:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Recipients',
                    'message': 'No contacts found matching the criteria.',
                    'type': 'warning',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recipients Loaded',
                'message': (
                    f'Loaded {len(partners)} sendable recipients from {source_count} matched contact rows. '
                    f'Excluded or merged: {excluded_count}. Review the audience summary for details.'
                ),
                'type': 'warning' if excluded_count else 'success',
            }
        }
    
    def _prepare_campaign_for_launch(self):
        """Refresh dynamic inputs and enforce local launch requirements."""
        self.ensure_one()
        self._check_account_ready_for_send()
        if self.campaign_type not in ('broadcast', 'drip'):
            raise UserError(_(
                "Campaign type '%s' is not wired to a sender yet. "
                "Use Broadcast or Drip Campaign for production sends."
            ) % dict(self._fields['campaign_type'].selection).get(self.campaign_type, self.campaign_type))
        if self.campaign_type == 'broadcast':
            self._check_recipient_configuration()
            self._check_message_configuration()
        elif not self.step_ids:
            raise UserError(_('Please configure at least one drip step before launching this campaign.'))

        # Refresh immediately before queue creation so copied campaigns include
        # current opt-outs, valid phones, tags, and frequency exclusions.
        self.with_context(preserve_campaign_preflight=True).action_load_recipients()
        if not self.partner_ids:
            raise UserError(_('No sendable recipients remain after phone, consent, and frequency checks.'))
        return True

    def action_run_preflight(self):
        """Run a non-sending end-to-end readiness check for this campaign."""
        self.ensure_one()
        checks = []
        warnings = []
        errors = []

        if self.state != 'draft':
            errors.append(_("Campaign must be a Draft. Use Reset to Draft only for an empty copied campaign."))
        if self.message_ids.filtered(lambda message: message.direction == 'outbound'):
            errors.append(_("This campaign already has outbound history. Duplicate it before launching another send."))

        if not errors:
            try:
                self._prepare_campaign_for_launch()
                checks.append(_("Audience refreshed: %s unique sendable recipient(s).") % len(self.partner_ids))
                checks.append(_("Template/content, media, reply rules, consent, and phone checks passed."))
            except (UserError, ValidationError) as exc:
                errors.append(str(exc))

        try:
            self.account_id.action_sync_meta_health()
            checks.append(
                _("Meta account is reachable (quality: %s, limit: %s).") % (
                    self.account_id.quality_rating or _('unknown'),
                    self.account_id.messaging_limit or _('unknown'),
                )
            )
        except Exception as exc:
            errors.append(_("Meta account health check failed: %s") % (str(exc) or exc.__class__.__name__))

        worker_issues = []
        for xmlid, model_name, code, _interval, _interval_type in self._delivery_cron_specs():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            actual_model = cron.model_id.model if cron and cron.model_id else False
            if not cron or not cron.active or actual_model != model_name or cron.code != code:
                worker_issues.append(xmlid.rsplit('.', 1)[-1])
        if worker_issues:
            errors.append(_("Delivery workers need repair: %s") % ', '.join(worker_issues))
        else:
            checks.append(_("All %s WhatsApp delivery workers are active.") % len(self._delivery_cron_specs()))

        parameters = self.env['ir.config_parameter'].sudo()
        realtime_mode = parameters.get_param('whatsapp.realtime.mode', default='bus')
        sidecar_url = parameters.get_param('whatsapp.sidecar.url')
        if sidecar_url:
            try:
                response = requests.get(f"{sidecar_url.rstrip('/')}/health", timeout=5)
                response.raise_for_status()
                sidecar_data = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {}
                queue_data = sidecar_data.get('queue') or {}
                checks.append(
                    _("Sidecar is online (queue driver: %s, queued: %s, dead: %s).") % (
                        queue_data.get('driver') or sidecar_data.get('redis') or _('unknown'),
                        queue_data.get('queued', 0),
                        queue_data.get('dead', 0),
                    )
                )
                if queue_data.get('dead'):
                    warnings.append(_("Sidecar has %s dead-letter webhook item(s) requiring review.") % queue_data['dead'])
            except Exception as exc:
                message = _("Sidecar health check failed: %s") % (str(exc) or exc.__class__.__name__)
                (errors if realtime_mode == 'socket' else warnings).append(message)
        elif realtime_mode == 'socket':
            errors.append(_("Realtime mode is Sidecar Socket but no sidecar URL is configured."))
        else:
            warnings.append(_("Sidecar URL is not configured; ERP Bus mode remains available."))

        if self.account_id.webhook_status != 'verified':
            warnings.append(_("Webhook is not marked Verified; delivery/read/reply updates may be delayed."))

        state = 'failed' if errors else ('warning' if warnings else 'passed')
        report_lines = (
            ["OK - %s" % line for line in checks]
            + ["CHECK - %s" % line for line in warnings]
            + ["FIX - %s" % line for line in errors]
        )
        self.write({
            'preflight_state': state,
            'preflight_checked_at': fields.Datetime.now(),
            'preflight_report': '\n'.join(report_lines),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Campaign Preflight Passed') if not errors else _('Campaign Preflight Failed'),
                'message': '\n'.join(report_lines),
                'type': 'danger' if errors else ('warning' if warnings else 'success'),
                'sticky': bool(errors or warnings),
            },
        }

    def action_send_campaign(self):
        """Send campaign messages and turn unexpected failures into operator-safe errors."""
        self.ensure_one()
        try:
            return self._action_send_campaign_impl()
        except (UserError, ValidationError):
            raise
        except Exception as e:
            detail = str(e) or e.__class__.__name__
            hint = _(
                "Please check the campaign readiness checklist, template media, recipient phone numbers, "
                "and make sure the WhatsApp module was upgraded on this database."
            )
            if 'UndefinedColumn' in detail or 'does not exist' in detail:
                hint = _(
                    "This usually means the server code was updated but this database schema was not upgraded. "
                    "Upgrade elsx_whatsapp_marketing on the live database, then try again."
                )
            _logger.exception(
                "Unexpected WhatsApp campaign queue failure. campaign_id=%s campaign_name=%s",
                self.id,
                self.name,
            )
            raise UserError(_("Campaign could not be queued.\n\nReason: %s\n\n%s") % (detail, hint))

    def _action_send_campaign_impl(self):
        """Send campaign messages or start drip sequence"""
        self.ensure_one()
        self.lock_for_update()
        scheduled_execution = bool(self.env.context.get('scheduled_campaign_execution'))
        if self.state != 'draft' and not (scheduled_execution and self.state == 'scheduled'):
            raise UserError(_(
                "Only a Draft campaign can be launched. Duplicate campaigns with send history, "
                "or reset an empty copied campaign to Draft first."
            ))
        existing_outbound = self.env['whatsapp.message'].sudo().search_count([
            ('campaign_id', '=', self.id),
            ('direction', '=', 'outbound'),
        ])
        if existing_outbound and not self.env.context.get('allow_campaign_rerun'):
            raise UserError(_(
                "This campaign already has %s outbound message record(s). "
                "It was not queued again; duplicate the campaign to start a new run."
            ) % existing_outbound)
        self._prepare_campaign_for_launch()

        now = fields.Datetime.now()
        scheduled_for_later = (
            self.schedule_type == 'scheduled'
            and self.schedule_date
            and self.schedule_date > now
        )
        target_state = 'scheduled' if scheduled_for_later else 'running'

        if self.campaign_type == 'broadcast':
            messages_to_create = []
            failed_messages_to_create = []
            skipped_without_phone = 0
            Message = self.env['whatsapp.message']

            def failed_message_vals(partner, phone_number, version, template, body, reason):
                phone_hint = phone_number or getattr(partner, 'mobile', False) or partner.phone or f'partner:{partner.id}'
                return {
                    'campaign_id': self.id,
                    'account_id': self.account_id.id,
                    'phone_number': phone_hint,
                    'partner_id': partner.id,
                    'ab_test_version': version if self.is_ab_test else False,
                    'message_type': 'template' if template else 'text',
                    'template_id': template.id if template else False,
                    'template_name': template.display_name if template else False,
                    'template_language': template._get_send_language_code() if template else False,
                    'body': body or '',
                    'status': 'failed',
                    'direction': 'outbound',
                    'flow_id': self.flow_id.id if self.flow_id else False,
                    'error_message': str(reason)[:1000],
                }

            # Safe Sending: Queue messages in draft state, then send or schedule
            # A/B Test Split Logic
            partner_list = list(self.partner_ids)
            if self.is_ab_test:
                import random
                random.shuffle(partner_list)
                split_point = int(len(partner_list) * (self.split_percentage / 100.0))
                part_a = partner_list[:split_point]
                part_b = partner_list[split_point:]
            else:
                part_a = partner_list
                part_b = []

            shared_media_by_version = {}
            if self.template_id:
                shared_media_by_version['a'] = self._prepare_shared_header_media(self.template_id, 'a')
            if self.is_ab_test and self.template_id_b:
                shared_media_by_version['b'] = self._prepare_shared_header_media(self.template_id_b, 'b')

            for i, partner in enumerate(partner_list):
                version = 'a' if partner in part_a else 'b'

                # Determine which template/body to use. For A/B tests, Version B must
                # use its own configured content instead of silently falling back to A.
                if version == 'b':
                    current_template = self.template_id_b
                    current_body = self.message_body_b
                else:
                    current_template = self.template_id
                    current_body = self.message_body

                phone = partner.phone
                if 'mobile' in self.env['res.partner']._fields and partner.mobile:
                    phone = partner.mobile

                if not phone:
                    skipped_without_phone += 1
                    continue

                try:
                    phone = Message._normalize_phone(phone, account=self.account_id)
                    if not phone:
                        failed_messages_to_create.append(failed_message_vals(
                            partner,
                            getattr(partner, 'mobile', False) or partner.phone,
                            version,
                            current_template,
                            current_body,
                            _("Phone number could not be normalized."),
                        ))
                        continue
                    message_body = current_template.body if current_template else current_body
                    raw_data = False
                    message_media_vals = {}

                    if current_template:
                        message_body = self._render_body_for_partner(message_body, partner, current_template)
                        media_kwargs = shared_media_by_version.get(version, {})
                        try:
                            template_payload = self._template_payload_for_partner(
                                current_template,
                                partner,
                                version=version,
                                media_kwargs=media_kwargs,
                            )
                        except (UserError, ValidationError) as e:
                            failed_messages_to_create.append(failed_message_vals(
                                partner, phone, version, current_template, message_body, e,
                            ))
                            continue
                        raw_data = json.dumps(template_payload)
                        if current_template.header_type in ('image', 'video', 'document'):
                            media_file = media_kwargs.get('header_media_file')
                            media_url = media_kwargs.get('header_media_url')
                            media_filename = (
                                media_kwargs.get('header_media_filename')
                                or current_template.header_media_filename
                                or current_template.name
                            )
                            if media_file:
                                message_media_vals.update({
                                    'media_file': media_file,
                                    'media_filename': media_filename,
                                })
                            elif media_url:
                                message_media_vals.update({
                                    'media_url': media_url,
                                    'media_filename': media_filename,
                                })
                    else:
                        message_body = self._render_body_for_partner(message_body, partner)

                    message_vals = {
                        'campaign_id': self.id,
                        'account_id': self.account_id.id,
                        'phone_number': phone,
                        'partner_id': partner.id,
                        'ab_test_version': version if self.is_ab_test else False,
                        'message_type': 'template' if current_template else 'text',
                        'template_id': current_template.id if current_template else False,
                        'template_name': current_template._get_send_template_name() if current_template else False,
                        'template_language': current_template._get_send_language_code() if current_template else False,
                        'body': message_body,
                        'raw_data': raw_data,
                        'status': 'queued',
                        'next_retry_at': self.schedule_date if scheduled_for_later else fields.Datetime.now(),
                        'direction': 'outbound',
                        'flow_id': self.flow_id.id if self.flow_id else False,
                    }
                    message_vals.update(message_media_vals)
                    messages_to_create.append(message_vals)
                except Exception as e:
                    _logger.exception(
                        "Campaign recipient preparation failed. campaign_id=%s partner_id=%s",
                        self.id,
                        partner.id,
                    )
                    failed_messages_to_create.append(failed_message_vals(
                        partner, phone, version, current_template, current_body, e,
                    ))

            if messages_to_create or failed_messages_to_create:
                if messages_to_create:
                    phone_numbers = list({
                        vals['phone_number'] for vals in messages_to_create if vals.get('phone_number')
                    })
                    if phone_numbers:
                        existing_chats = self.env['whatsapp.chat'].sudo().search([
                            ('account_id', '=', self.account_id.id),
                            ('phone_number', 'in', phone_numbers),
                        ])
                        chat_by_phone = {chat.phone_number: chat.id for chat in existing_chats}
                        for vals in messages_to_create:
                            chat_id = chat_by_phone.get(vals.get('phone_number'))
                            if chat_id:
                                vals['chat_id_ref'] = chat_id

                self._create_campaign_messages_safely(
                    Message,
                    messages_to_create + failed_messages_to_create,
                )
                if messages_to_create:
                    self.state = 'scheduled' if scheduled_for_later else 'running'
                    if not scheduled_for_later:
                        self._wake_campaign_queue_cron()
                    _logger.info(
                        "Campaign %s queued %s messages and recorded %s preparation failure(s).",
                        self.name,
                        len(messages_to_create),
                        len(failed_messages_to_create),
                    )
                else:
                    self.state = 'completed'
                    _logger.warning(
                        "Campaign %s had no queueable recipients and recorded %s preparation failure(s).",
                        self.name,
                        len(failed_messages_to_create),
                    )
            else:
                raise UserError('No valid recipients with phone numbers were found.')
                
        elif self.campaign_type == 'drip':
            # Initialize drip campaign for participants
            for partner in self.partner_ids:
                phone = getattr(partner, 'mobile', False) or partner.phone
                if not phone:
                    continue
                existing = self.env['whatsapp.campaign.participant'].search([
                    ('campaign_id', '=', self.id),
                    ('partner_id', '=', partner.id)
                ])
                if not existing:
                    self.env['whatsapp.campaign.participant'].create({
                        'campaign_id': self.id,
                        'partner_id': partner.id,
                        'next_execution_date': self.schedule_date if scheduled_for_later else now,
                        'state': 'running'
                    })
            self.state = target_state
        
        # Log Campaign Launch to Blockchain Ledger
        try:
             self.env['elsx.blockchain.log'].create({
                'model_name': 'whatsapp.campaign',
                'res_id': self.id,
                'operation': 'write',
                'data_snapshot': f"Campaign Queued: {self.name}, Recipients: {len(self.partner_ids)}",
                'previous_hash': 'CAMPAIGN_LAUNCH',
                'current_hash': 'PENDING_VERIFICATION'
            })
        except Exception as e:
            _logger.warning(f"Blockchain logging failed for campaign {self.name}: {e}")
            
        queued_count = len(messages_to_create) if self.campaign_type == 'broadcast' else len(self.partner_ids)
        failed_count = len(failed_messages_to_create) if self.campaign_type == 'broadcast' else 0
        skipped_count = skipped_without_phone if self.campaign_type == 'broadcast' else 0
        launch_message = (
            f'Queued {queued_count} message(s).'
            + (f' Failed {failed_count} recipient(s) with readable errors.' if failed_count else '')
            + (f' Skipped {skipped_count} recipient(s) without phone numbers.' if skipped_count else '')
        )
        auto_dispatch_failed = False
        if self.campaign_type == 'broadcast' and messages_to_create and not scheduled_for_later:
            launch_message += _(
                " Delivery will continue in the background queue now; refresh after a minute to see sent/delivered counts."
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Scheduled' if target_state == 'scheduled' else 'Campaign Started',
                'message': (
                    f'Campaign scheduled for {self.schedule_date}. {launch_message}'
                    if target_state == 'scheduled'
                    else launch_message
                ),
                'type': 'warning' if failed_count or skipped_count or auto_dispatch_failed else 'success',
            }
        }

    def _execute_scheduled_campaign(self):
        """Execute campaign that was scheduled.
        Instead of immediately sending all and hitting rate limits, 
        we move it to running and let the _cron_process_global_queue safely chunk the dispatch.
        """
        for record in self:
            if record.state != 'scheduled':
                continue
                
            record.state = 'running'
            _logger.info(f"Campaign {record.name} execution triggered. Queued for background worker chunking.")

    def action_process_queue(self):
        """Release one safe batch and let the cron worker send it."""
        self.ensure_one()
        if self.state == 'scheduled' and self.schedule_date and self.schedule_date > fields.Datetime.now():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Campaign Not Due Yet',
                    'message': f'This campaign is scheduled for {self.schedule_date}.',
                    'type': 'info',
                }
            }

        if self.state == 'scheduled':
            self.state = 'running'

        now = fields.Datetime.now()
        Message = self.env['whatsapp.message'].sudo()
        pending_domain = [
            ('campaign_id', '=', self.id),
            ('status', 'in', ['draft', 'queued']),
        ]
        pending_count = Message.search_count(pending_domain)

        if not pending_count:
            self.state = 'completed'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Queue Empty',
                    'message': 'All messages have been sent.',
                    'type': 'info',
                }
            }

        batch_size = max(int(self.batch_size or 50), 1)
        due_domain = [
            ('campaign_id', '=', self.id),
            '|',
                ('status', '=', 'draft'),
                '&', ('status', '=', 'queued'), '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
        ]
        released = Message.search(due_domain, order='create_date asc', limit=batch_size)
        if not released:
            released = Message.search(pending_domain, order='next_retry_at asc, create_date asc', limit=batch_size)

        if released:
            released.write({'status': 'queued', 'next_retry_at': now})
            self.last_batch_at = False
            self._wake_campaign_queue_cron()
        else:
            self._schedule_next_campaign_queue_run(default_delay_seconds=60)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Queue Worker Started',
                'message': (
                    f'Released {len(released)} message(s) for background sending. '
                    f'{pending_count} message(s) remain in this campaign queue.'
                ),
                'type': 'success',
            }
        }

    @api.model
    def _cron_process_global_queue(self):
        """
        Enterprise Background Worker: Runs every minute.
        Processes each running campaign by its configured batch size and interval.
        """
        started = time.monotonic()
        now = fields.Datetime.now()
        campaigns = self.search([
            ('state', 'in', ['running', 'scheduled']),
            ('message_ids.status', 'in', ['draft', 'queued']),
        ], limit=20, order='create_date asc')

        if not campaigns:
            _logger.debug("[CRON-CAMPAIGN-QUEUE] processed=0 duration_ms=0")
            return

        Message = self.env['whatsapp.message']
        messages = Message.browse()
        for campaign in campaigns:
            if campaign.state == 'scheduled' and campaign.schedule_date and campaign.schedule_date > now:
                continue
            delay_minutes = max(int(campaign.batch_interval or 1), 1)
            if campaign.last_batch_at and campaign.last_batch_at + timedelta(minutes=delay_minutes) > now:
                continue
            batch_size = max(int(campaign.batch_size or 50), 1)
            campaign_messages = Message.search([
                ('campaign_id', '=', campaign.id),
                '|',
                    ('status', '=', 'draft'),
                    '&', ('status', '=', 'queued'), '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
            ], limit=batch_size, order='create_date asc')
            if campaign_messages:
                campaign.last_batch_at = now
                messages |= campaign_messages

        if not messages:
            _logger.info("[CRON-CAMPAIGN-QUEUE] processed=0 due_or_paced_campaigns=%s", len(campaigns))
            return

        sent_count = 0
        failed_count = 0
        processed_by_campaign = {}
        cron_progress = self.env.context.get('cron_id')
        for msg in messages:
            campaign = msg.campaign_id
            processed_by_campaign[campaign.id] = processed_by_campaign.get(campaign.id, 0) + 1
            try:
                with self.env.cr.savepoint():
                    if campaign and campaign.state == 'scheduled':
                        if campaign.schedule_date and campaign.schedule_date > fields.Datetime.now():
                            continue
                        campaign.state = 'running'

                    msg.action_send()
                    if msg.status in ('sent', 'delivered', 'read'):
                        sent_count += 1
                    flow = msg.flow_id or (campaign.flow_id if campaign else False)
                    if flow and msg.status in ('sent', 'delivered', 'read'):
                        try:
                            flow.sudo().start_flow_for_participant(False, msg)
                        except Exception as flow_err:
                            _logger.error(f"Failed to auto-start flow {flow.name} via cron: {flow_err}")
            except Exception as e:
                try:
                    with self.env.cr.savepoint():
                        vals = {
                            'status': 'failed',
                            'error_message': str(e),
                            'next_retry_at': False,
                        }
                        if not isinstance(e, ValidationError):
                            backoff_seconds = min(3600, 60 * (2 ** min(msg.retry_count, 5)))
                            vals.update({
                                'retry_count': msg.retry_count + 1,
                                'next_retry_at': fields.Datetime.now() + timedelta(seconds=backoff_seconds + random.uniform(0, 10)),
                            })
                        msg.write(vals)
                        failed_count += 1
                except Exception as db_err:
                    _logger.error(f"Could not save failed state for cron message {msg.id}: {db_err}")
                _logger.error(f"Failed to process queued message {msg.id}: {e}")
            finally:
                if cron_progress:
                    # Meta may accept a message before the batch finishes. Persist each
                    # outcome so a worker restart cannot resend already accepted rows.
                    self.env['ir.cron']._commit_progress(1, remaining=0)

        touched_campaigns = messages.mapped('campaign_id')
        for campaign in touched_campaigns:
            campaign.last_batch_at = fields.Datetime.now()
            remaining_count = Message.search_count([
                ('campaign_id', '=', campaign.id),
                '|',
                    ('status', 'in', ['draft', 'queued']),
                    '&', '&', ('status', '=', 'failed'), ('retry_count', '<', 5), ('next_retry_at', '!=', False),
            ])
            if not remaining_count:
                campaign.state = 'completed'
                continue

        total_remaining = Message.search_count([
            ('campaign_id.state', 'in', ['running', 'scheduled']),
            ('status', 'in', ['draft', 'queued']),
        ])
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        _logger.info(
            "[CRON-CAMPAIGN-QUEUE] campaigns=%s processed=%s sent=%s failed=%s total_remaining=%s duration_ms=%s batches=%s",
            len(campaigns), len(messages), sent_count, failed_count, total_remaining, duration_ms, processed_by_campaign,
        )

    @api.model
    def _delivery_cron_specs(self):
        return (
            (
                'elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue',
                'whatsapp.campaign',
                'model._cron_process_global_queue()',
                1,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_process_direct_message_queue',
                'whatsapp.message',
                'model._cron_process_broadcast_queue()',
                1,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_process_scheduled_campaigns',
                'whatsapp.scheduled.campaign',
                'model._cron_process_scheduled_campaigns()',
                5,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_retry_failed_messages',
                'whatsapp.message',
                'model._cron_retry_failed()',
                2,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_process_whatsapp_drip_campaigns',
                'whatsapp.campaign.participant',
                'model.process_drip_campaigns()',
                15,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_resume_delayed_bot_flows',
                'whatsapp.bot.flow.log',
                'model._cron_resume_delayed_flows()',
                1,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_process_scheduled_messages',
                'whatsapp.scheduled.message',
                'model._cron_send_scheduled()',
                5,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_evaluate_ab_tests',
                'whatsapp.campaign',
                'model._cron_evaluate_ab_tests()',
                30,
                'minutes',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_reset_daily_counters',
                'whatsapp.account',
                'model._cron_reset_daily_counters()',
                1,
                'days',
            ),
            (
                'elsx_whatsapp_marketing.ir_cron_recover_received_webhooks',
                'whatsapp.webhook.log',
                'model._cron_recover_received()',
                1,
                'minutes',
            ),
        )

    @api.model
    def _repair_delivery_crons(self):
        repaired = 0
        for xmlid, model_name, code, interval, interval_type in self._delivery_cron_specs():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            model = self.env['ir.model']._get(model_name)
            if not cron or not model:
                continue
            expected = {
                'model_id': model.id,
                'state': 'code',
                'code': code,
                'interval_number': interval,
                'interval_type': interval_type,
                'active': True,
            }
            if xmlid == 'elsx_whatsapp_marketing.ir_cron_process_whatsapp_queue':
                expected['nextcall'] = fields.Datetime.now()
            changes = {}
            for key, value in expected.items():
                current = cron[key].id if key == 'model_id' else cron[key]
                if current != value:
                    changes[key] = value
            if changes:
                cron.sudo().write(changes)
                repaired += 1
        _logger.info('WhatsApp delivery cron repair changed=%s', repaired)
        return repaired

    def action_generate_ai_content(self):
        """Generate auditable campaign draft content without sending it."""
        self.ensure_one()
        if not self.env['elsx.ai.provider']._whatsapp_draft_enabled():
            raise UserError(_("WhatsApp AI drafts are disabled in Settings."))
        job = self.env['elsx.ai.job'].create_job(
            'campaign',
            f"AI campaign draft for {self.name}",
            origin=self,
            input_text=(
                f"Campaign: {self.name}\n"
                f"Target type: {self.target_type}\n"
                f"Recipients loaded: {len(self.partner_ids)}\n"
                f"Existing body: {self.message_body or ''}"
            ),
            prompt_code='whatsapp_campaign_default',
        )
        try:
            job.action_run()
        except UserError as exc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Draft Not Ready',
                    'message': str(exc),
                    'type': 'warning',
                }
            }
        if job.response_text:
            self.message_body = job.response_text
            self.ai_variant_a = job.response_text
            self.ai_variant_b = "%s\n\nReply with Catalogue, Price, or Sales and our team will help." % job.response_text
        recipient_count = len(self.partner_ids)
        body = (self.message_body or '').lower()
        self.ai_audience_warning = (
            "Load recipients before final review." if not recipient_count
            else "Review opt-in, DND, and recent-contact exclusions before sending to %s recipients." % recipient_count
        )
        self.ai_spam_risk = 'high' if any(word in body for word in ('free!!!', 'limited time!!!', 'guaranteed')) else 'medium' if recipient_count > 500 else 'low'
        self.ai_reply_rule_suggestions = (
            "Suggested reply rules: Catalogue -> send catalog flow; Price -> create lead and assign sales; "
            "Stop/Unsubscribe -> opt-out handling; Support -> assign support team."
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'AI Campaign Draft Job',
            'res_model': 'elsx.ai.job',
            'res_id': job.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _stop_pending_delivery(self):
        """Stop queue, retry, drip, and scheduler work without deleting history."""
        Message = self.env['whatsapp.message'].sudo()
        ScheduledCampaign = self.env['whatsapp.scheduled.campaign'].sudo()
        stopped_messages = 0
        stopped_retries = 0
        stopped_participants = 0
        stopped_schedules = 0

        for campaign in self:
            pending = Message.search([
                ('campaign_id', '=', campaign.id),
                ('status', 'in', ['draft', 'queued']),
            ])
            if pending:
                pending.write({
                    'status': 'cancelled',
                    'next_retry_at': False,
                    'error_message': False,
                })
                stopped_messages += len(pending)

            retryable_failed = Message.search([
                ('campaign_id', '=', campaign.id),
                ('status', '=', 'failed'),
                ('next_retry_at', '!=', False),
            ])
            if retryable_failed:
                retryable_failed.write({'next_retry_at': False})
                stopped_retries += len(retryable_failed)

            active_participants = campaign.participant_ids.filtered(
                lambda participant: participant.state in ('running', 'paused')
            )
            if active_participants:
                active_participants.write({'state': 'stopped', 'next_execution_date': False})
                stopped_participants += len(active_participants)

            active_schedules = ScheduledCampaign.search([
                ('campaign_id', '=', campaign.id),
                ('status', 'in', ['draft', 'scheduled', 'running']),
            ])
            if active_schedules:
                active_schedules.write({'status': 'cancelled'})
                stopped_schedules += len(active_schedules)

            campaign.last_batch_at = False

        return {
            'messages': stopped_messages,
            'retries': stopped_retries,
            'participants': stopped_participants,
            'schedules': stopped_schedules,
        }

    def action_cancel(self):
        """Cancel future work while preserving delivered message history."""
        stopped = self._stop_pending_delivery()
        self.write({'state': 'cancelled'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Campaign Cancelled'),
                'message': _(
                    '%(messages)s queued message(s), %(retries)s retry attempt(s), '
                    '%(participants)s drip participant(s), and %(schedules)s schedule(s) were stopped.'
                ) % stopped,
                'type': 'success',
            },
        }

    def action_archive_record(self):
        self._stop_pending_delivery()
        self.write({'state': 'archived'})
        return True

    def action_unarchive_record(self):
        for campaign in self.filtered(lambda item: item.state == 'archived'):
            has_history = bool(campaign.message_ids or campaign.participant_ids)
            campaign.write({'state': 'cancelled' if has_history else 'draft'})
        return True

    def action_reset_to_draft(self):
        """Reopen only empty cancelled copies; sent campaign history is immutable."""
        for campaign in self:
            if campaign.state not in ('cancelled', 'archived'):
                raise UserError(_('Only a Cancelled or Archived campaign can be reset.'))
            if campaign.message_ids or campaign.participant_ids:
                raise UserError(_(
                    'This campaign has delivery history and cannot be reset. '
                    'Duplicate it to create a clean Draft campaign.'
                ))
            active_schedule = self.env['whatsapp.scheduled.campaign'].sudo().search_count([
                ('campaign_id', '=', campaign.id),
                ('status', 'in', ['draft', 'scheduled', 'running']),
            ])
            if active_schedule:
                raise UserError(_('Cancel the active campaign schedule before resetting to Draft.'))
            campaign.write({
                'state': 'draft',
                'schedule_type': 'immediate',
                'schedule_date': False,
                'last_batch_at': False,
                'preflight_state': 'not_run',
                'preflight_checked_at': False,
                'preflight_report': False,
            })
        return True

    def action_retry_failed_messages(self):
        total_retryable = 0
        total_blocked = 0
        for campaign in self:
            if campaign.state in ('cancelled', 'archived'):
                raise UserError(_(
                    'A Cancelled or Archived campaign cannot be restarted with Retry Failed. '
                    'Duplicate it to create a new delivery run.'
                ))
            failed = campaign.message_ids.filtered(lambda msg: msg.status == 'failed')
            retryable = failed.filtered(lambda msg: not msg._is_non_retryable_failure())
            blocked = failed - retryable
            total_retryable += len(retryable)
            total_blocked += len(blocked)
            if not retryable:
                continue
            retryable.write({
                'status': 'queued',
                'retry_count': 0,
                'next_retry_at': fields.Datetime.now(),
                'error_message': False,
            })
            campaign.write({'state': 'running', 'last_batch_at': False})
        if total_retryable:
            self._wake_campaign_queue_cron()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Failed Messages Requeued',
                'message': _(
                    '%(retryable)s retryable message(s) were queued. '
                    '%(blocked)s permanent failure(s) were left unchanged.'
                ) % {'retryable': total_retryable, 'blocked': total_blocked},
                'type': 'success' if total_retryable else 'warning',
            },
        }

    def action_view_failed_recipients(self):
        self.ensure_one()
        outbound = self.message_ids.filtered(lambda message: message.direction == 'outbound')
        outcomes = {}
        for message in outbound:
            key = self._message_recipient_key(message)
            outcome = outcomes.setdefault(key, {
                'failed': False,
                'successful': False,
                'pending': False,
            })
            outcome['failed'] |= message.status == 'failed'
            outcome['successful'] |= message.status in ('sent', 'delivered', 'read')
            outcome['pending'] |= message.status in ('draft', 'queued')

        final_failed_keys = {
            key for key, outcome in outcomes.items()
            if outcome['failed'] and not outcome['successful'] and not outcome['pending']
        }
        failed_message_ids = []
        selected_keys = set()
        for message in outbound.sorted('id', reverse=True):
            key = self._message_recipient_key(message)
            if message.status == 'failed' and key in final_failed_keys and key not in selected_keys:
                failed_message_ids.append(message.id)
                selected_keys.add(key)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Failed Recipients',
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', failed_message_ids)],
            'target': 'current',
        }

    def process_inbound_reply(self, message):
        """Apply campaign reply rules to an inbound reply when it references a campaign send."""
        parent = message.parent_id
        campaign = parent.campaign_id if parent and parent.campaign_id else False
        if not campaign:
            campaign = self.search([
                ('account_id', '=', message.account_id.id),
                ('message_ids.phone_number', '=', message.phone_number),
                ('message_ids.direction', '=', 'outbound'),
                ('message_ids.create_date', '>=', fields.Datetime.now() - timedelta(days=14)),
            ], order='write_date desc', limit=1)
        if not campaign:
            return False
        if message.campaign_id != campaign:
            message.sudo().write({'campaign_id': campaign.id})
        campaign._mark_chat_source(message)
        return campaign._apply_reply_rules(message)

    @api.model
    def track_entry_message(self, message):
        body = (message.body or message.button_text or '').strip()
        if not body:
            return False
        campaign = self.sudo().search([
            ('account_id', '=', message.account_id.id),
            ('tracking_entry_keyword', '!=', False),
        ]).filtered(lambda c: (c.tracking_entry_keyword or '').strip().lower() == body.lower())[:1]
        if not campaign:
            return False
        campaign._mark_chat_source(message)
        return campaign

    def _mark_chat_source(self, message):
        self.ensure_one()
        chat = message.chat_id_ref
        if chat and not chat.source_campaign_id:
            chat.sudo().write({
                'source_campaign_id': self.id,
                'source_keyword': self.tracking_entry_keyword or message.body or message.button_text,
                'source_medium': self.tracking_medium or 'campaign',
                'source_first_message_id': message.id,
            })
        return True

    def _apply_reply_rules(self, message):
        self.ensure_one()
        rules = self.reply_rule_ids.filtered('active').sorted('sequence')
        for rule in rules:
            if rule._matches_message(message):
                rule._execute_reply_action(message)
                return rule
        if self.default_reply_action and self.default_reply_action != 'none':
            rule = self.env['whatsapp.campaign.reply.rule'].new({
                'campaign_id': self.id,
                'name': 'Default Reply Action',
                'match_type': 'any_reply',
                'action_type': self.default_reply_action,
                'flow_id': self.reply_flow_id.id if self.reply_flow_id else False,
                'response_message': self.reply_response_message or False,
                'assign_user_id': self.reply_assign_user_id.id if self.reply_assign_user_id else False,
                'assign_team_member_id': self.reply_assign_team_member_id.id if self.reply_assign_team_member_id else False,
                'assign_tag_id': self.reply_assign_tag_id.id if self.reply_assign_tag_id else False,
                'form_id': self.reply_form_id.id if self.reply_form_id else False,
                'chat_status': self.reply_chat_status or False,
                'lead_note': self.reply_lead_note or False,
            })
            rule._execute_reply_action(message)
            return rule
        return False

    # =========================================================
    # A/B TEST WINNER SELECTION
    # =========================================================
    def action_determine_ab_winner(self):
        """Manually trigger A/B test winner evaluation."""
        self.ensure_one()
        if not self.is_ab_test:
            return
        winner = self._evaluate_ab_winner()
        if winner:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'A/B Test Result',
                    'message': f'Winner: Version {winner.upper()} based on read rate.',
                    'type': 'success',
                }
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'A/B Test',
                'message': 'Not enough data yet to determine a winner.',
                'type': 'info',
            }
        }

    def _evaluate_ab_winner(self):
        """Compare read rates between A and B versions and declare a winner.
        
        Returns 'a', 'b', or False if insufficient data.
        """
        self.ensure_one()
        if not self.is_ab_test or self.ab_test_winner:
            return self.ab_test_winner

        msgs_a = self.message_ids.filtered(lambda m: m.ab_test_version == 'a')
        msgs_b = self.message_ids.filtered(lambda m: m.ab_test_version == 'b')

        # Need at least 5 messages in each group for a meaningful comparison
        if len(msgs_a) < 5 or len(msgs_b) < 5:
            return False

        sent_a = len(msgs_a.filtered(lambda m: m.status in ('sent', 'delivered', 'read')))
        read_a = len(msgs_a.filtered(lambda m: m.status == 'read'))
        delivered_a = len(msgs_a.filtered(lambda m: m.status in ('delivered', 'read')))
        
        sent_b = len(msgs_b.filtered(lambda m: m.status in ('sent', 'delivered', 'read')))
        read_b = len(msgs_b.filtered(lambda m: m.status == 'read'))
        delivered_b = len(msgs_b.filtered(lambda m: m.status in ('delivered', 'read')))

        read_rate_a = (read_a / sent_a * 100) if sent_a > 0 else 0
        read_rate_b = (read_b / sent_b * 100) if sent_b > 0 else 0
        
        deliv_rate_a = (delivered_a / sent_a * 100) if sent_a > 0 else 0
        deliv_rate_b = (delivered_b / sent_b * 100) if sent_b > 0 else 0

        _logger.info(
            f"[A/B] Campaign {self.name}: A={read_rate_a:.1f}% read ({read_a}/{sent_a}), "
            f"B={read_rate_b:.1f}% read ({read_b}/{sent_b})"
        )

        # Primary metric: Read rate
        if abs(read_rate_a - read_rate_b) >= 2.0:
            winner = 'a' if read_rate_a >= read_rate_b else 'b'
        # Fallback metric: Delivered rate (if read receipts are disabled by recipients)
        elif abs(deliv_rate_a - deliv_rate_b) >= 2.0:
            winner = 'a' if deliv_rate_a >= deliv_rate_b else 'b'
        else:
            return False

        self.write({'ab_test_winner': winner})
        return winner

    @api.model
    def _cron_evaluate_ab_tests(self):
        """Cron: Auto-evaluate completed A/B test campaigns."""
        campaigns = self.search([
            ('is_ab_test', '=', True),
            ('ab_test_winner', '=', False),
            ('state', 'in', ['running', 'completed']),
        ])
        for campaign in campaigns:
            try:
                campaign._evaluate_ab_winner()
            except Exception as e:
                _logger.error(f"[A/B] Failed to evaluate campaign {campaign.id}: {e}")


class WhatsAppCampaignReplyRule(models.Model):
    _name = 'whatsapp.campaign.reply.rule'
    _description = 'WhatsApp Campaign Reply Action'
    _order = 'campaign_id, sequence, id'

    campaign_id = fields.Many2one('whatsapp.campaign', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(required=True)
    match_type = fields.Selection([
        ('button_payload', 'Button Payload'),
        ('button_text', 'Button Text'),
        ('list_item_id', 'List Item ID'),
        ('free_text_contains', 'Free Text Contains'),
        ('any_reply', 'Any Reply'),
    ], default='button_text', required=True)
    match_value = fields.Char('Match Value')
    action_type = fields.Selection([
        ('none', 'No Action'),
        ('start_flow', 'Start Flow'),
        ('send_message', 'Send Message'),
        ('send_form_link', 'Send Form Link'),
        ('send_payment_link', 'Send Payment Link'),
        ('assign_user', 'Assign Agent'),
        ('assign_team_member', 'Assign Team Member'),
        ('assign_tag', 'Assign Tag'),
        ('create_lead', 'Create Lead'),
        ('update_lead_note', 'Create / Update Lead Note'),
        ('set_chat_status', 'Set Chat Status'),
        ('resolve_chat', 'Resolve Chat'),
        ('reopen_chat', 'Reopen Chat'),
    ], default='none', required=True)
    flow_id = fields.Many2one('whatsapp.bot.flow', string='Flow')
    form_id = fields.Many2one('whatsapp.form', string='Form', domain="[('active', '=', True)]")
    response_message = fields.Text('Response Message')
    assign_user_id = fields.Many2one('res.users', string='Agent')
    assign_team_member_id = fields.Many2one('whatsapp.team.member', string='Team Member')
    assign_tag_id = fields.Many2one('res.partner.category', string='Tag')
    chat_status = fields.Selection([
        ('open', 'Open / Pending'),
        ('snoozed', 'Snoozed'),
        ('resolved', 'Resolved'),
    ], string='Chat Status')
    lead_note = fields.Text('Lead Note')
    handled_count = fields.Integer('Handled Replies', default=0, readonly=True)

    @api.constrains(
        'active', 'match_type', 'match_value', 'action_type', 'flow_id',
        'form_id', 'response_message', 'assign_user_id', 'assign_team_member_id',
        'assign_tag_id', 'chat_status', 'lead_note',
    )
    def _check_configuration(self):
        for rule in self.filtered('active'):
            rule._validate_configuration()

    def _validate_configuration(self):
        self.ensure_one()
        if self.match_type != 'any_reply' and not (self.match_value or '').strip():
            raise ValidationError(f'Reply rule "{self.name}" needs a match value.')
        required = {
            'start_flow': (self.flow_id, f'Reply rule "{self.name}" needs a flow.'),
            'send_message': ((self.response_message or '').strip(), f'Reply rule "{self.name}" needs a response message.'),
            'send_form_link': (self.form_id or self.campaign_id.form_id or self.campaign_id.account_id.default_form_id, f'Reply rule "{self.name}" needs a form.'),
            'send_payment_link': (self.campaign_id.account_id and self.campaign_id.account_id.payment_link_mode != 'disabled', f'Reply rule "{self.name}" needs payment links enabled on the account.'),
            'assign_user': (self.assign_user_id, f'Reply rule "{self.name}" needs an agent.'),
            'assign_team_member': (self.assign_team_member_id, f'Reply rule "{self.name}" needs a team member.'),
            'assign_tag': (self.assign_tag_id, f'Reply rule "{self.name}" needs a tag.'),
            'set_chat_status': (self.chat_status, f'Reply rule "{self.name}" needs a chat status.'),
            'update_lead_note': ((self.lead_note or '').strip(), f'Reply rule "{self.name}" needs a lead note.'),
        }
        value, message = required.get(self.action_type or 'none', (True, ''))
        if not value:
            raise ValidationError(message)
        return True

    def _matches_message(self, message):
        self.ensure_one()
        match_type = self.match_type
        expected = (self.match_value or '').strip().lower()
        if match_type == 'any_reply':
            return True
        if not expected:
            return False
        if match_type == 'button_payload':
            actual = (message.button_payload or '').strip().lower()
        elif match_type == 'button_text':
            actual = (message.button_text or message.body or '').strip().lower()
        elif match_type == 'list_item_id':
            actual = (message.list_item_id or '').strip().lower()
        else:
            actual = (message.body or '').strip().lower()
            return expected in actual
        return actual == expected

    def _render_text(self, text, message):
        partner = message.partner_id
        value = text or ''
        value = value.replace('{{name}}', partner.name if partner else '')
        value = value.replace('{{phone}}', message.phone_number or '')
        value = value.replace('{{last_reply}}', message.body or '')
        return value

    def _execute_reply_action(self, message):
        self.ensure_one()
        campaign = self.campaign_id
        chat = message.chat_id_ref
        partner = message.partner_id
        if partner:
            partner.sudo().write({'whatsapp_last_reply_action': f'{campaign.name}: {self.name}'})
        if self.action_type == 'start_flow' and self.flow_id:
            self.flow_id.sudo()._execute_flow(message, source='campaign_reply')
        elif self.action_type == 'send_message' and self.response_message:
            self.env['whatsapp.message'].sudo().create({
                'account_id': message.account_id.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'text',
                'body': self._render_text(self.response_message, message),
                'direction': 'outbound',
                'campaign_id': campaign.id,
                'is_automated': True,
            }).action_send()
        elif self.action_type == 'send_form_link':
            form = self.form_id or campaign.form_id or campaign.account_id.default_form_id
            if form and form.public_url:
                form_url = "%s?campaign_id=%s" % (form.public_url, campaign.id)
                body = _(
                    "Hi %(name)s, please fill this short form so our team can help you faster:\n%(url)s"
                ) % {
                    'name': partner.display_name if partner else 'there',
                    'url': form_url,
                }
                self.env['whatsapp.message'].sudo().create({
                    'account_id': message.account_id.id,
                    'phone_number': message.phone_number,
                    'partner_id': partner.id if partner else False,
                    'chat_id_ref': chat.id if chat else False,
                    'direction': 'outbound',
                    'message_type': 'text',
                    'body': body,
                    'campaign_id': campaign.id,
                    'is_automated': True,
                }).action_send()
        elif self.action_type == 'send_payment_link':
            if partner:
                body = campaign.account_id._build_payment_link_message(partner=partner)
                self.env['whatsapp.message'].sudo().create({
                    'account_id': message.account_id.id,
                    'phone_number': message.phone_number,
                    'partner_id': partner.id,
                    'chat_id_ref': chat.id if chat else False,
                    'direction': 'outbound',
                    'message_type': 'text',
                    'body': body,
                    'campaign_id': campaign.id,
                    'is_automated': True,
                }).action_send()
        elif self.action_type == 'assign_user' and chat and self.assign_user_id:
            chat.sudo().write({'assigned_user_id': self.assign_user_id.id, 'state': 'open'})
        elif self.action_type == 'assign_team_member' and chat and self.assign_team_member_id:
            user = self.assign_team_member_id.user_id
            chat.sudo().write({'assigned_user_id': user.id, 'state': 'open'})
        elif self.action_type == 'assign_tag' and self.assign_tag_id:
            if chat:
                chat.sudo().write({'tag_ids': [(4, self.assign_tag_id.id)]})
            if partner:
                partner.sudo().write({'category_id': [(4, self.assign_tag_id.id)]})
        elif self.action_type == 'create_lead':
            self.env['crm.lead'].sudo().create({
                'name': f'Campaign Reply: {campaign.name}',
                'partner_id': partner.id if partner else False,
                'phone': message.phone_number,
                'type': 'lead',
                'description': f'Reply matched rule "{self.name}".\n\n{message.body or ""}',
            })
        elif self.action_type == 'update_lead_note':
            lead = chat.lead_id if chat and chat.lead_id else False
            if not lead and partner:
                lead = self.env['crm.lead'].sudo().search([('partner_id', '=', partner.id)], limit=1)
            if not lead:
                lead = self.env['crm.lead'].sudo().create({
                    'name': f'Campaign Reply: {campaign.name}',
                    'partner_id': partner.id if partner else False,
                    'phone': message.phone_number,
                    'type': 'lead',
                })
            lead.message_post(body=self._render_text(self.lead_note, message))
        elif self.action_type == 'set_chat_status' and chat and self.chat_status:
            chat_vals = {'state': self.chat_status}
            if self.chat_status == 'open':
                chat_vals['is_archived'] = False
            chat.sudo().write(chat_vals)
        elif self.action_type == 'resolve_chat' and chat:
            chat.sudo().write({'state': 'resolved'})
        elif self.action_type == 'reopen_chat' and chat:
            chat.sudo().write({'state': 'open', 'is_archived': False})
        if self.id:
            self.sudo().write({'handled_count': self.handled_count + 1})
        return True
