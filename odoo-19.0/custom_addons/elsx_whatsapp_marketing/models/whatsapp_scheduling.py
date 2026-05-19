# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import pytz
import logging
import json

_logger = logging.getLogger(__name__)


def _timezone_selection(self):
    return [(tz, tz) for tz in pytz.all_timezones]


class WhatsAppScheduledMessage(models.Model):
    """Advanced Message Scheduling with Timezone Support"""
    _name = 'whatsapp.scheduled.message'
    _description = 'Scheduled WhatsApp Message'
    _rec_name = 'name'
    _order = 'scheduled_date'

    name = fields.Char('Message Name', compute='_compute_name', store=True)
    account_id = fields.Many2one('whatsapp.account', required=True, ondelete='cascade')
    
    # Recipients
    recipient_type = fields.Selection([
        ('single', 'Single Contact'),
        ('multiple', 'Multiple Contacts'),
        ('segment', 'Segment'),
        ('campaign', 'Campaign'),
    ], default='single')
    
    partner_id = fields.Many2one('res.partner', string='Recipient')
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    segment_id = fields.Many2one('whatsapp.contact.segment', string='Segment')
    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign')
    
    # Message content
    message_type = fields.Selection([
        ('text', 'Text'),
        ('template', 'Template'),
        ('media', 'Media'),
    ], default='text')
    
    message_body = fields.Text('Message')
    template_id = fields.Many2one('whatsapp.template', string='Template',
                                 domain="[('status', '=', 'approved')]")
    media_id = fields.Many2one('whatsapp.media.library', string='Media')
    
    # Scheduling
    schedule_type = fields.Selection([
        ('once', 'Send Once'),
        ('recurring', 'Recurring'),
    ], default='once')
    
    scheduled_date = fields.Datetime('Scheduled Date/Time', required=True)
    timezone_id = fields.Selection(
        selection=_timezone_selection,
        string='Timezone',
        required=True,
        default=lambda self: self.env.user.tz or 'UTC',
    )
    
    # Recurring options
    recurring_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom (Cron)'),
    ], string='Repeat')
    
    recurring_interval = fields.Integer('Every (days/weeks/months)', default=1)
    recurrence_end_date = fields.Datetime('Recurrence End Date')
    cron_expression = fields.Char('Cron Expression', help='e.g. 0 9 * * 1 for 9 AM every Monday')
    
    # Execution
    status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='draft')
    
    last_execution_date = fields.Datetime('Last Execution', readonly=True)
    next_execution_date = fields.Datetime('Next Execution', compute='_compute_next_execution', store=True)
    execution_count = fields.Integer('Times Executed', readonly=True, default=0)
    
    # Settings
    send_immediately_if_past = fields.Boolean('Send Immediately if Time Passed', default=True,
                                             help='If scheduled time is in past, send right away')
    use_contact_timezone = fields.Boolean('Use Contact Timezone', default=True,
                                         help='Send at same local time across different timezones')
    
    # Timezone override per contact (for recurring messages)
    send_at_hour = fields.Integer('Send at Hour (24h)', help='Hour to send recurring message')
    send_at_minute = fields.Integer('Send at Minute', default=0)
    
    @api.depends('scheduled_date', 'timezone_id')
    def _compute_name(self):
        for record in self:
            tz = pytz.timezone(record.timezone_id or 'UTC')
            date_str = record.scheduled_date.strftime('%Y-%m-%d %H:%M') if record.scheduled_date else ''
            record.name = f"Scheduled: {date_str} ({tz.zone})" if date_str else "Scheduled Message"
    
    @api.depends('scheduled_date', 'recurring_type', 'recurrence_end_date')
    def _compute_next_execution(self):
        for record in self:
            if record.status in ['completed', 'cancelled', 'failed']:
                record.next_execution_date = False
            elif record.status == 'scheduled':
                record.next_execution_date = record.scheduled_date
            else:
                record.next_execution_date = False
    
    def _get_next_recurring_date(self, base_date):
        self.ensure_one()
        interval = self.recurring_interval or 1
        if self.recurring_type == 'daily':
            return base_date + timedelta(days=interval)
        elif self.recurring_type == 'weekly':
            return base_date + timedelta(weeks=interval)
        elif self.recurring_type == 'monthly':
            year = base_date.year
            month = base_date.month + interval
            day = base_date.day
            while month > 12:
                month -= 12
                year += 1
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            if day > max_day:
                day = max_day
            return base_date.replace(year=year, month=month, day=day)
        elif self.recurring_type == 'custom':
            if self.cron_expression:
                try:
                    from croniter import croniter
                    cron = croniter(self.cron_expression, base_date)
                    return cron.get_next(datetime)
                except Exception:
                    pass
            return base_date + timedelta(days=1)
        return False

    def action_schedule(self):
        """Schedule the message"""
        for record in self:
            if record.schedule_type == 'recurring':
                if not record.recurring_type:
                    raise UserError("Please select a recurrence type for recurring scheduled messages.")
                if record.recurring_interval <= 0:
                    raise UserError("Recurrence interval must be greater than zero.")
                if record.recurring_type == 'custom' and not record.cron_expression:
                    raise UserError("Please provide a cron expression for custom recurrence.")
            if not record.scheduled_date:
                raise UserError("Please specify a scheduled date/time.")
        self.write({'status': 'scheduled'})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Message Scheduled',
                'message': f'Message scheduled for {self.scheduled_date}',
                'type': 'success',
            }
        }
    
    def action_send_now(self):
        """Send the message immediately"""
        self.ensure_one()
        
        try:
            self._execute_send()
            self.write({'status': 'completed', 'last_execution_date': fields.Datetime.now()})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Message Sent',
                    'message': 'Message sent successfully',
                    'type': 'success',
                }
            }
        except Exception as e:
            self.write({'status': 'failed'})
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Send Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    def _execute_send(self):
        """Send the message to recipients"""
        # Determine recipients
        if self.recipient_type == 'single':
            recipients = self.partner_id
        elif self.recipient_type == 'multiple':
            recipients = self.partner_ids
        elif self.recipient_type == 'segment':
            recipients = self.segment_id.contact_ids
        elif self.recipient_type == 'campaign':
            recipients = self.campaign_id.partner_ids
        else:
            return

        recipients = recipients.filtered(lambda partner: partner)
        if not recipients:
            raise UserError("Please select at least one scheduled recipient.")

        for partner in recipients:
            phone = getattr(partner, 'mobile', False) or partner.phone
            if not phone:
                continue

            if self.message_type == 'text':
                vals = {
                    'account_id': self.account_id.id,
                    'phone_number': phone,
                    'partner_id': partner.id,
                    'message_type': 'text',
                    'body': self.message_body,
                    'direction': 'outbound',
                    'is_automated': True,
                }
            elif self.message_type == 'template':
                if not self.template_id:
                    raise UserError("Please select a template for scheduled template messages.")
                payload = self.template_id._prepare_send_payload(partner=partner)
                vals = {
                    'account_id': self.account_id.id,
                    'phone_number': phone,
                    'partner_id': partner.id,
                    'message_type': 'template',
                    'body': self.template_id.body,
                    'template_id': self.template_id.id,
                    'template_name': self.template_id._get_send_template_name(),
                    'template_language': self.template_id._get_send_language_code(),
                    'raw_data': json.dumps(payload),
                    'direction': 'outbound',
                    'is_automated': True,
                }
            elif self.message_type == 'media':
                if not self.media_id:
                    raise UserError("Please select media for scheduled media messages.")
                vals = {
                    'account_id': self.account_id.id,
                    'phone_number': phone,
                    'partner_id': partner.id,
                    'message_type': self.media_id.media_type,
                    'body': self.message_body,
                    'caption': self.message_body,
                    'media_file': self.media_id.media_file,
                    'media_filename': self.media_id.media_filename,
                    'direction': 'outbound',
                    'is_automated': True,
                }
            else:
                continue

            message = self.env['whatsapp.message'].create(vals)
            message.action_send()
    
    def action_cancel(self):
        """Cancel scheduled message"""
        self.write({'status': 'cancelled'})

    @api.model
    def _cron_send_scheduled(self):
        """Cron job to process scheduled messages that are due"""
        now = fields.Datetime.now()
        
        # Find scheduled messages that are ready to send
        scheduled_msgs = self.search([
            ('status', '=', 'scheduled'),

            ('scheduled_date', '<=', now)
        ])
        
        sent_count = 0
        for msg in scheduled_msgs:
            try:
                with self.env.cr.savepoint():
                    msg._execute_send()
                    if msg.schedule_type == 'recurring' and msg.recurring_type:
                        next_date = msg._get_next_recurring_date(msg.scheduled_date)
                        if next_date and (not msg.recurrence_end_date or next_date <= msg.recurrence_end_date):
                            msg.write({
                                'scheduled_date': next_date,
                                'last_execution_date': now,
                                'execution_count': msg.execution_count + 1,
                            })
                        else:
                            msg.write({
                                'status': 'completed',
                                'last_execution_date': now,
                                'execution_count': msg.execution_count + 1,
                            })
                    else:
                        msg.write({
                            'status': 'completed',
                            'last_execution_date': now,
                            'execution_count': msg.execution_count + 1,
                        })
                    sent_count += 1
            except Exception as e:
                _logger.error(f"Failed to send scheduled message {msg.id}: {e}")
                msg.write({'status': 'failed'})
        
        if sent_count > 0:
            _logger.info(f"[CRON] Processed {sent_count} scheduled messages")


class WhatsAppScheduledCampaign(models.Model):
    """Advanced Campaign Scheduling"""
    _name = 'whatsapp.scheduled.campaign'
    _description = 'Scheduled Campaign'

    campaign_id = fields.Many2one('whatsapp.campaign', required=True, ondelete='cascade')
    scheduled_date = fields.Datetime('Send Date/Time', required=True)
    timezone_id = fields.Selection(selection=_timezone_selection, required=True,
                                   default=lambda self: self.env.user.tz or 'UTC')
    
    # A/B Testing
    variant_a_template = fields.Many2one('whatsapp.template', string='Variant A')
    variant_b_template = fields.Many2one('whatsapp.template', string='Variant B')
    split_percentage = fields.Float('Variant B %', default=50.0, help='Percentage for variant B')
    
    # Scheduling options
    send_immediately_if_past = fields.Boolean('Send Immediately if Past', default=True)
    confirm_before_send = fields.Boolean('Require Confirmation', default=True)
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ], default='draft')

    # Recurrence options
    schedule_type = fields.Selection([
        ('once', 'Send Once'),
        ('recurring', 'Recurring'),
    ], default='once')
    
    recurring_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom (Cron)'),
    ], string='Repeat')
    
    recurring_interval = fields.Integer('Every (days/weeks/months)', default=1)
    recurrence_end_date = fields.Datetime('Recurrence End Date')
    cron_expression = fields.Char('Cron Expression', help='e.g. 0 9 * * 1 for 9 AM every Monday')
    
    last_execution_date = fields.Datetime('Last Execution', readonly=True)
    next_execution_date = fields.Datetime('Next Execution', compute='_compute_next_execution', store=True)
    execution_count = fields.Integer('Times Executed', readonly=True, default=0)

    @api.depends('scheduled_date', 'recurring_type', 'recurrence_end_date')
    def _compute_next_execution(self):
        for record in self:
            if record.status in ['completed', 'cancelled', 'failed']:
                record.next_execution_date = False
            elif record.status == 'scheduled':
                record.next_execution_date = record.scheduled_date
            else:
                record.next_execution_date = False
    
    def _get_next_recurring_date(self, base_date):
        self.ensure_one()
        interval = self.recurring_interval or 1
        if self.recurring_type == 'daily':
            return base_date + timedelta(days=interval)
        elif self.recurring_type == 'weekly':
            return base_date + timedelta(weeks=interval)
        elif self.recurring_type == 'monthly':
            year = base_date.year
            month = base_date.month + interval
            day = base_date.day
            while month > 12:
                month -= 12
                year += 1
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            if day > max_day:
                day = max_day
            return base_date.replace(year=year, month=month, day=day)
        elif self.recurring_type == 'custom':
            if self.cron_expression:
                try:
                    from croniter import croniter
                    cron = croniter(self.cron_expression, base_date)
                    return cron.get_next(datetime)
                except Exception:
                    pass
            return base_date + timedelta(days=1)
        return False

    def action_schedule(self):
        """Schedule the campaign"""
        for record in self:
            if record.schedule_type == 'recurring':
                if not record.recurring_type:
                    raise UserError("Please select a recurrence type for recurring scheduled campaigns.")
                if record.recurring_interval <= 0:
                    raise UserError("Recurrence interval must be greater than zero.")
                if record.recurring_type == 'custom' and not record.cron_expression:
                    raise UserError("Please provide a cron expression for custom recurrence.")
            if not record.scheduled_date:
                raise UserError("Please specify a scheduled date/time.")
        self.write({'status': 'scheduled'})
    
    def action_send(self):
        """Execute the campaign"""
        # Force reload recipients to capture any dynamic updates
        self.campaign_id.action_load_recipients()
        
        # Reset campaign state to draft temporarily to bypass state checks
        if self.campaign_id.state in ['running', 'completed', 'scheduled']:
            self.campaign_id.state = 'draft'
            
        self.campaign_id.action_send_campaign()

    @api.model
    def _cron_process_scheduled_campaigns(self):
        """Cron job to process scheduled campaigns that are due"""
        now = fields.Datetime.now()
        scheduled_campaigns = self.search([
            ('status', '=', 'scheduled'),
            ('scheduled_date', '<=', now)
        ])
        
        processed_count = 0
        for sc in scheduled_campaigns:
            try:
                with self.env.cr.savepoint():
                    sc.action_send()
                    
                    if sc.schedule_type == 'recurring' and sc.recurring_type:
                        next_date = sc._get_next_recurring_date(sc.scheduled_date)
                        if next_date and (not sc.recurrence_end_date or next_date <= sc.recurrence_end_date):
                            sc.write({
                                'scheduled_date': next_date,
                                'last_execution_date': now,
                                'execution_count': sc.execution_count + 1,
                                'status': 'scheduled',
                            })
                        else:
                            sc.write({
                                'status': 'completed',
                                'last_execution_date': now,
                                'execution_count': sc.execution_count + 1,
                            })
                    else:
                        sc.write({
                            'status': 'completed',
                            'last_execution_date': now,
                            'execution_count': sc.execution_count + 1,
                        })
                    processed_count += 1
            except Exception as e:
                _logger.error(f"Failed to process scheduled campaign {sc.id}: {e}")
                sc.write({'status': 'failed'})
                
        if processed_count > 0:
            _logger.info(f"[CRON] Processed {processed_count} scheduled campaigns")


class WhatsAppCampaignScheduleWizard(models.TransientModel):
    """Wizard for advanced campaign scheduling"""
    _name = 'whatsapp.campaign.schedule.wizard'
    _description = 'Schedule Campaign Wizard'

    campaign_id = fields.Many2one('whatsapp.campaign', required=True)
    schedule_type = fields.Selection([
        ('immediate', 'Send Immediately'),
        ('scheduled', 'Schedule for Later'),
        ('recurring', 'Recurring Campaign'),
    ], default='immediate')
    
    scheduled_date = fields.Datetime('Send Date')
    timezone_id = fields.Selection(selection=_timezone_selection, required=True,
                                   default=lambda self: self.env.user.tz or 'UTC')
    
    # Time zone considerations
    respect_contact_timezone = fields.Boolean('Respect Contact Timezone', default=True,
                                            help='Send to each contact at the same local time')
                                            
    recurring_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom (Cron)'),
    ], string='Repeat')
    
    recurring_interval = fields.Integer('Every (days/weeks/months)', default=1)
    recurrence_end_date = fields.Datetime('Recurrence End Date')
    cron_expression = fields.Char('Cron Expression', help='e.g. 0 9 * * 1 for 9 AM every Monday')
    
    def action_schedule(self):
        """Apply the schedule"""
        self.ensure_one()
        
        if self.schedule_type == 'immediate':
            self.campaign_id.action_send_campaign()
        elif self.schedule_type == 'scheduled':
            if not self.scheduled_date:
                raise UserError("Please select a scheduled date.")
            
            # Create a once-off scheduled campaign record
            self.env['whatsapp.scheduled.campaign'].create({
                'campaign_id': self.campaign_id.id,
                'scheduled_date': self.scheduled_date,
                'timezone_id': self.timezone_id,
                'status': 'scheduled',
                'schedule_type': 'once',
            })
            # Mark campaign state as scheduled
            self.campaign_id.write({
                'schedule_type': 'scheduled',
                'schedule_date': self.scheduled_date,
                'state': 'scheduled',
            })
        elif self.schedule_type == 'recurring':
            if not self.scheduled_date:
                raise UserError("Please select a scheduled date (start date).")
            if not self.recurring_type:
                raise UserError("Please select a recurrence type.")
            if self.recurring_interval <= 0:
                raise UserError("Recurrence interval must be greater than zero.")
            if self.recurring_type == 'custom' and not self.cron_expression:
                raise UserError("Please specify a cron expression.")
                
            # Create a recurring scheduled campaign record
            self.env['whatsapp.scheduled.campaign'].create({
                'campaign_id': self.campaign_id.id,
                'scheduled_date': self.scheduled_date,
                'timezone_id': self.timezone_id,
                'status': 'scheduled',
                'schedule_type': 'recurring',
                'recurring_type': self.recurring_type,
                'recurring_interval': self.recurring_interval,
                'recurrence_end_date': self.recurrence_end_date,
                'cron_expression': self.cron_expression,
            })
            # Mark campaign state as scheduled
            self.campaign_id.write({
                'schedule_type': 'scheduled',
                'schedule_date': self.scheduled_date,
                'state': 'scheduled',
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Scheduled',
                'message': 'Campaign scheduled successfully',
                'type': 'success',
            }
        }
