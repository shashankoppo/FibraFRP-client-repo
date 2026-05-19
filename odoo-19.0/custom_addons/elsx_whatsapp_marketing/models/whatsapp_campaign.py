# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
import logging
import json
import random
from datetime import timedelta

_logger = logging.getLogger(__name__)


class WhatsAppCampaign(models.Model):
    _name = 'whatsapp.campaign'
    _description = 'WhatsApp Marketing Campaign'
    _order = 'create_date desc'

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
    message_body = fields.Text('Message Body')
    
    # A/B Testing
    is_ab_test = fields.Boolean('Enable A/B Testing')
    split_percentage = fields.Float('Split Percentage', default=50.0)
    split_percentage_b = fields.Float('Split Percentage (B)', compute='_compute_split_b', store=True)
    template_id_b = fields.Many2one('whatsapp.template', string='Message Template (B)')
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
    
    @api.depends('partner_ids', 'message_ids.status')
    def _compute_statistics(self):
        for record in self:
            record.total_recipients = len(record.partner_ids)
            record.queued_count = len(record.message_ids.filtered(lambda m: m.status in ['draft', 'queued']))
            record.sent_count = len(record.message_ids.filtered(lambda m: m.status in ['sent', 'delivered', 'read']))
            record.delivered_count = len(record.message_ids.filtered(lambda m: m.status in ['delivered', 'read']))
            record.read_count = len(record.message_ids.filtered(lambda m: m.status == 'read'))
            record.failed_count = len(record.message_ids.filtered(lambda m: m.status == 'failed'))
            
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

    @api.constrains('split_percentage', 'schedule_type', 'schedule_date', 'campaign_type', 'step_ids', 'template_id', 'message_body')
    def _check_campaign_configuration(self):
        for record in self:
            if record.split_percentage < 0 or record.split_percentage > 100:
                raise ValidationError("A/B split percentage must be between 0 and 100.")
            if record.schedule_type == 'scheduled' and not record.schedule_date:
                raise ValidationError("Scheduled campaigns require a schedule date.")
            if record.campaign_type == 'drip' and not record.step_ids:
                raise ValidationError("Drip campaigns require at least one step.")
            if record.campaign_type == 'broadcast' and not (record.template_id or (record.message_body or '').strip()):
                raise ValidationError("Broadcast campaigns require a template or message body.")

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

    def _template_payload_for_partner(self, template, partner):
        return template._prepare_send_payload(partner=partner)

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
        """Send campaign messages or start drip sequence"""
        self.ensure_one()
        
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

        if self.campaign_type == 'broadcast' and not (self.template_id or (self.message_body or '').strip()):
            raise UserError('Please set a message template or message body before queuing this campaign.')
        if self.campaign_type == 'drip' and not self.step_ids:
            raise UserError('Please configure at least one drip step before launching this campaign.')
        
        if self.campaign_type == 'broadcast':
            messages_to_create = []
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
                
                # Determine which template/body to use
                current_template = self.template_id if version == 'a' else (self.template_id_b or self.template_id)
                current_body = self.message_body if version == 'a' else (self.message_body_b or self.message_body)
                
                phone = partner.phone
                if 'mobile' in self.env['res.partner']._fields and partner.mobile:
                    phone = partner.mobile
                
                if not phone: continue
                phone = self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id)
                
                message_body = current_body or (current_template.body if current_template else '')
                raw_data = False

                if current_template:
                    message_body = self._render_body_for_partner(message_body, partner, current_template)
                    raw_data = json.dumps(self._template_payload_for_partner(current_template, partner))
                else:
                    message_body = self._render_body_for_partner(message_body, partner)

                messages_to_create.append({
                    'campaign_id': self.id,
                    'account_id': self.account_id.id,
                    'phone_number': phone,
                    'partner_id': partner.id,
                    'ab_test_version': version if self.is_ab_test else False,
                    'message_type': 'template' if current_template else 'text',
                    'template_name': current_template._get_send_template_name() if current_template else False,
                    'template_language': current_template._get_send_language_code() if current_template else False,
                    'body': message_body,
                    'raw_data': raw_data,
                    'status': 'queued',
                    'next_retry_at': self.schedule_date if scheduled_for_later else fields.Datetime.now(),
                    'direction': 'outbound',
                    'flow_id': self.flow_id.id if self.flow_id else False,
                })
            
            if messages_to_create:
                self.env['whatsapp.message'].create(messages_to_create)
                self.state = 'scheduled' if scheduled_for_later else 'running'
                _logger.info(f"Campaign {self.name} queued {len(messages_to_create)} messages for background processing.")
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
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Scheduled' if target_state == 'scheduled' else 'Campaign Queued',
                'message': (
                    f'Campaign scheduled for {self.schedule_date}.'
                    if target_state == 'scheduled'
                    else f'Campaign queued {len(self.partner_ids)} messages for Safe Sending.'
                ),
                'type': 'success',
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
        now = fields.Datetime.now()
        messages = self.env['whatsapp.message'].search([
            ('campaign_id.state', 'in', ['running', 'scheduled']),
            '|',
                ('status', '=', 'draft'),
                '&', ('status', '=', 'queued'), '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
        ], limit=500, order='create_date asc')
        
        if not messages:
            return

        for msg in messages:
            try:
                with self.env.cr.savepoint():
                    campaign = msg.campaign_id
                    if campaign and campaign.state == 'scheduled':
                        if campaign.schedule_date and campaign.schedule_date > fields.Datetime.now():
                            continue
                        campaign.state = 'running'

                    msg.action_send()
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

    def action_generate_ai_content(self):
        """Generate content using ELSX AI Marketing"""
        self.ensure_one()
        if 'elsx.marketing.ai' in self.env.registry.models:
            ai_suggestion = self.env['elsx.marketing.ai'].create({
                'name': f"AI Draft for {self.name}",
                'target_audience': self.target_type,
                'platform': 'whatsapp',
            })
            ai_suggestion.action_generate_content()
            if ai_suggestion.generated_content:
                self.message_body = ai_suggestion.generated_content
        elif not self.message_body:
            self.message_body = (
                "Hi {{name}},\n\n"
                "We have an update for you from our team. Reply here and we will help you right away."
            )
             
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Content Drafted',
                'message': 'Campaign message content is ready to review.',
                'type': 'success',
            }
        }
    
    def action_cancel(self):
        """Cancel the campaign"""
        self.state = 'cancelled'

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
