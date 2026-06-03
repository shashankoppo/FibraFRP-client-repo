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

_logger = logging.getLogger(__name__)


class WhatsAppCampaign(models.Model):
    _name = 'whatsapp.campaign'
    _description = 'WhatsApp Marketing Campaign'
    _order = 'create_date desc'

    _campaign_state_schedule_idx = models.Index("(state, schedule_date, create_date)")

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
    ], string='Winner', readonly=True)

    @api.depends('split_percentage')
    def _compute_split_b(self):
        for rec in self:
            rec.split_percentage_b = 100.0 - (rec.split_percentage or 50.0)

    # Scheduling
    schedule_type = fields.Selection([
        ('immediate', 'Send Immediately'),
        ('scheduled', 'Schedule'),
    ], string='Schedule', default='immediate')
    
    schedule_date = fields.Datetime('Scheduled Date')
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', required=True)
    
    # Statistics
    total_recipients = fields.Integer('Total Recipients', compute='_compute_statistics', store=True)
    queued_count = fields.Integer('Queued', compute='_compute_statistics', store=True)
    sent_count = fields.Integer('Sent', compute='_compute_statistics', store=True)
    delivered_count = fields.Integer('Delivered', compute='_compute_statistics', store=True)
    read_count = fields.Integer('Read', compute='_compute_statistics', store=True)
    failed_count = fields.Integer('Failed', compute='_compute_statistics', store=True)
    
    delivery_rate = fields.Float('Delivery Rate', compute='_compute_statistics', store=True)
    read_rate = fields.Float('Read Rate', compute='_compute_statistics', store=True)
    
    # Relations
    message_ids = fields.One2many('whatsapp.message', 'campaign_id', string='Messages')
    step_ids = fields.One2many('whatsapp.campaign.step', 'campaign_id', string='Drip Steps')
    participant_ids = fields.One2many('whatsapp.campaign.participant', 'campaign_id', string='Participants')
    
    # Analytics
    click_count = fields.Integer('Clicks', default=0)
    conversion_count = fields.Integer('Conversions', default=0)
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
    tracking_campaign_code = fields.Char('Campaign Code')
    tracking_entry_keyword = fields.Char('Entry Keyword')
    tracking_wa_link = fields.Char('wa.me Tracking Link', compute='_compute_tracking_wa_link')
    form_submission_count = fields.Integer('Form Submissions', compute='_compute_conversion_counters')
    payment_action_count = fields.Integer('Payment Actions', compute='_compute_conversion_counters')
    tracked_reply_count = fields.Integer('Tracked Replies', compute='_compute_conversion_counters')

    # Reply handling and audience safety
    reply_rule_ids = fields.One2many('whatsapp.campaign.reply.rule', 'campaign_id', string='Reply Actions')
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
    excluded_count = fields.Integer('Excluded', readonly=True, default=0)
    exclusion_notes = fields.Text('Audience Exclusion Notes', readonly=True)
    preview_partner_id = fields.Many2one('res.partner', string='Preview Recipient')
    recipient_preview_html = fields.Html('Recipient Preview', compute='_compute_recipient_preview_html')
    recipient_preview_text = fields.Text('Recipient Preview Text', compute='_compute_recipient_preview_html')
    pre_send_checklist_html = fields.Html('Pre-send Checklist', compute='_compute_pre_send_checklist_html')
    pre_send_checklist_text = fields.Text('Pre-send Checklist Text', compute='_compute_pre_send_checklist_html')
    
    @api.depends('partner_ids', 'message_ids.status', 'message_ids.direction')
    def _compute_statistics(self):
        for record in self:
            outbound_messages = record.message_ids.filtered(lambda m: m.direction == 'outbound')
            record.total_recipients = len(record.partner_ids)
            record.queued_count = len(outbound_messages.filtered(lambda m: m.status in ['draft', 'queued']))
            record.sent_count = len(outbound_messages.filtered(lambda m: m.status in ['sent', 'delivered', 'read']))
            record.delivered_count = len(outbound_messages.filtered(lambda m: m.status in ['delivered', 'read']))
            record.read_count = len(outbound_messages.filtered(lambda m: m.status == 'read'))
            record.failed_count = len(outbound_messages.filtered(lambda m: m.status == 'failed'))
            
            # Rates
            if record.total_recipients > 0:
                record.delivery_rate = (record.delivered_count / record.total_recipients) * 100
                record.read_rate = (record.read_count / record.total_recipients) * 100
            else:
                record.delivery_rate = 0.0
                record.read_rate = 0.0
    
    @api.depends('conversion_count', 'sent_count')
    def _compute_roi(self):
        for record in self:
            if record.sent_count > 0:
                record.roi = (record.conversion_count / record.sent_count) * 100
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
                add(bool((record.message_body or '').strip()), 'Message content', 'Plain text campaign body is configured.' if record.message_body else 'Add a template or message body.')

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

    def _template_media_ready(self, template, version='a'):
        self.ensure_one()
        if not template or template.header_type not in ('image', 'video', 'document'):
            return True
        media_kwargs = self._campaign_header_media_kwargs(version)
        return bool(
            template.header_media_url
            or template.header_media_file
            or media_kwargs.get('header_media_url')
            or media_kwargs.get('header_media_file')
        )

    def _check_template_ready_for_campaign(self, template, label, version='a'):
        if not template:
            return
        if template.account_id and self.account_id and template.account_id != self.account_id:
            raise ValidationError(f"{label} template must belong to the selected WhatsApp account.")
        if template.status != 'approved':
            raise ValidationError(f"{label} template must be approved before it can be used in a campaign.")
        if not self._template_media_ready(template, version):
            tab_hint = (
                "A/B Testing tab under %s > Header Media Override" % label
                if self.is_ab_test
                else "Message tab > Template Header Media Override"
            )
            raise ValidationError(
                f"{label} template has a {template.header_type} header. "
                "Set a default Header Media File/URL on the template, or upload this campaign's header media in "
                f"{tab_hint}."
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

    def _template_payload_for_partner(self, template, partner, version='a'):
        media_kwargs = self._campaign_header_media_kwargs(version)
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

    def action_load_recipients(self):
        """Load recipients based on target type"""
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        
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
            partners = Partner.search(self._partner_phone_domain() + [('category_id', 'in', self.tag_ids.ids)])
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

        partners = partners.filtered(lambda p: p.phone or getattr(p, 'mobile', False))
        
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
            recent_partner_ids = self.env['whatsapp.message'].sudo().search([
                ('partner_id', 'in', partners.ids),
                ('direction', '=', 'outbound'),
                ('create_date', '>=', cutoff),
                ('campaign_id', '!=', self.id),
            ]).mapped('partner_id')
            if recent_partner_ids:
                partners = partners - recent_partner_ids
                exclusion_notes.append(f'Recently contacted ({self.recent_contact_days}d): {len(recent_partner_ids)}')
        if self.frequency_cap_days > 0 and partners:
            cutoff = fields.Datetime.now() - timedelta(days=self.frequency_cap_days)
            capped_partner_ids = self.env['whatsapp.message'].sudo().search([
                ('partner_id', 'in', partners.ids),
                ('direction', '=', 'outbound'),
                ('campaign_id', '!=', False),
                ('create_date', '>=', cutoff),
            ]).mapped('partner_id')
            if capped_partner_ids:
                partners = partners - capped_partner_ids
                exclusion_notes.append(f'Campaign frequency cap ({self.frequency_cap_days}d): {len(capped_partner_ids)}')

        excluded_partners = original_partners - partners
        if excluded_partners:
            excluded_partners.write({
                'whatsapp_last_exclusion_reason': '; '.join(exclusion_notes) or 'Excluded by campaign audience rules',
            })
        self.excluded_count = len(excluded_partners)
        self.exclusion_notes = '\n'.join(exclusion_notes)

        self.partner_ids = [(6, 0, partners.ids)]
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
                'message': f'Successfully loaded {len(partners)} recipients.',
                'type': 'success',
            }
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
        if self.campaign_type not in ('broadcast', 'drip'):
            raise UserError(_(
                "Campaign type '%s' is not wired to a sender yet. "
                "Use Broadcast or Drip Campaign for production sends."
            ) % dict(self._fields['campaign_type'].selection).get(self.campaign_type, self.campaign_type))
        if self.campaign_type == 'broadcast':
            self._check_recipient_configuration()
            self._check_message_configuration()
        
        if not self.partner_ids:
            self.action_load_recipients()
        if not self.partner_ids:
            from odoo.exceptions import UserError
            raise UserError('No recipients selected.')

        now = fields.Datetime.now()
        scheduled_for_later = (
            self.schedule_type == 'scheduled'
            and self.schedule_date
            and self.schedule_date > now
        )
        target_state = 'scheduled' if scheduled_for_later else 'running'

        if self.campaign_type == 'drip' and not self.step_ids:
            raise UserError('Please configure at least one drip step before launching this campaign.')
        
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
                    'template_language': template.exact_language_code if template else False,
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
                        media_kwargs = self._campaign_header_media_kwargs(version)
                        try:
                            template_payload = self._template_payload_for_partner(current_template, partner, version=version)
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
                    existing_chat = self.env['whatsapp.chat'].sudo().search([
                        ('account_id', '=', self.account_id.id),
                        ('phone_number', '=', phone),
                    ], limit=1)
                    if existing_chat:
                        message_vals['chat_id_ref'] = existing_chat.id
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
                Message.create(messages_to_create + failed_messages_to_create)
                if messages_to_create:
                    self.state = 'scheduled' if scheduled_for_later else 'running'
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

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Scheduled' if target_state == 'scheduled' else 'Campaign Queued',
                'message': (
                    f'Campaign scheduled for {self.schedule_date}. {launch_message}'
                    if target_state == 'scheduled'
                    else launch_message
                ),
                'type': 'warning' if failed_count or skipped_count else 'success',
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
        """Safe Sending Rate Limiter: Processes 50 draft messages at a time"""
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
        batch_size = self.batch_size or 50
        draft_messages = self.message_ids.filtered(
            lambda m: m.status == 'draft' or (
                m.status == 'queued' and (not m.next_retry_at or m.next_retry_at <= now)
            )
        )[:batch_size]
        
        if not draft_messages:
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
            
        sent = 0
        queued = 0
        for msg in draft_messages:
            try:
                with self.env.cr.savepoint():
                    msg.action_send()
                    if msg.status in ('sent', 'delivered', 'read'):
                        sent += 1
                        # Enterprise Logic: Auto-Start Bot Flow
                        flow = msg.flow_id or self.flow_id
                        if flow:
                            try:
                                flow.sudo().start_flow_for_participant(False, msg)
                            except Exception as flow_err:
                                _logger.error(f"Failed to auto-start flow {flow.name}: {flow_err}")
                    elif msg.status == 'queued':
                        queued += 1
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
                except Exception as db_err:
                    _logger.error(f"Could not save failed state for message {msg.id}: {db_err}")
                _logger.error(f"Failed to process queued message: {e}")
                
        # Optional: update state to completed if done
        if not self.env['whatsapp.message'].search_count([
            ('campaign_id', '=', self.id),
            '|',
                ('status', 'in', ['draft', 'queued']),
                '&', '&', ('status', '=', 'failed'), ('retry_count', '<', 5), ('next_retry_at', '!=', False),
        ]):
            self.state = 'completed'
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Queue Processed',
                'message': f'Safely dispatched {sent} messages. {queued} remain queued.',
                'type': 'success',
            }
        }

    @api.model
    def _cron_process_global_queue(self):
        """
        Enterprise Background Worker: Runs every minute.
        Fetches up to 500 draft messages and sends them to respect Meta API TPS limits.
        Commits after each chunk to prevent massive rollbacks.
        """
        started = time.monotonic()
        now = fields.Datetime.now()
        messages = self.env['whatsapp.message'].search([
            ('campaign_id.state', 'in', ['running', 'scheduled']),
            '|',
                ('status', '=', 'draft'),
                '&', ('status', '=', 'queued'), '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
        ], limit=500, order='create_date asc')
        
        if not messages:
            _logger.debug("[CRON-CAMPAIGN-QUEUE] processed=0 duration_ms=0")
            return

        sent_count = 0
        failed_count = 0
        for msg in messages:
            try:
                with self.env.cr.savepoint():
                    campaign = msg.campaign_id
                    if campaign and campaign.state == 'scheduled':
                        if campaign.schedule_date and campaign.schedule_date > fields.Datetime.now():
                            continue
                        campaign.state = 'running'

                    msg.action_send()
                    if msg.status in ('sent', 'delivered', 'read'):
                        sent_count += 1
                    # Enterprise Logic: Auto-Start Bot Flow
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
                
        # Check if campaigns have finished their drafts
        campaigns = messages.mapped('campaign_id')
        for campaign in campaigns:
            if not self.env['whatsapp.message'].search_count([
                ('campaign_id', '=', campaign.id),
                '|',
                    ('status', 'in', ['draft', 'queued']),
                    '&', '&', ('status', '=', 'failed'), ('retry_count', '<', 5), ('next_retry_at', '!=', False),
            ]):
                campaign.state = 'completed'
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        remaining = self.env['whatsapp.message'].search_count([
            ('campaign_id.state', 'in', ['running', 'scheduled']),
            ('status', 'in', ['draft', 'queued']),
        ])
        _logger.info(
            "[CRON-CAMPAIGN-QUEUE] processed=%s sent=%s failed=%s remaining=%s duration_ms=%s",
            len(messages), sent_count, failed_count, remaining, duration_ms,
        )

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

    def action_cancel(self):
        """Cancel the campaign"""
        self.state = 'cancelled'

    def action_archive_record(self):
        self.write({'state': 'archived'})
        return True

    def action_unarchive_record(self):
        self.filtered(lambda campaign: campaign.state == 'archived').write({'state': 'draft'})
        return True

    def action_retry_failed_messages(self):
        for campaign in self:
            failed = campaign.message_ids.filtered(lambda msg: msg.status == 'failed')
            failed.write({
                'status': 'queued',
                'retry_count': 0,
                'next_retry_at': fields.Datetime.now(),
                'error_message': False,
            })
            if failed and campaign.state in ('completed', 'cancelled'):
                campaign.state = 'running'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Failed Messages Requeued',
                'message': 'Failed campaign messages were placed back into the safe sending queue.',
                'type': 'success',
            },
        }

    def action_view_failed_recipients(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Failed Recipients',
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('campaign_id', '=', self.id), ('status', '=', 'failed')],
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
