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
    
    def action_schedule(self):
        """Schedule the message"""
        if any(record.schedule_type == 'recurring' for record in self):
            raise UserError("Recurring scheduled messages are not implemented yet.")
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
            ('schedule_type', '=', 'once'),
            ('scheduled_date', '<=', now)
        ])
        
        sent_count = 0
        for msg in scheduled_msgs:
            try:
                msg._execute_send()
                msg.write({'status': 'completed', 'last_execution_date': now})
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
    ], default='draft')
    
    def action_schedule(self):
        """Schedule the campaign"""
        self.write({'status': 'scheduled'})
    
    def action_send(self):
        """Execute the campaign"""
        if self.campaign_id.state not in ['draft', 'scheduled']:
            raise Exception('Campaign must be in draft or scheduled state')
        
        self.campaign_id.action_send_campaign()
        self.write({'status': 'completed'})


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
    
    def action_schedule(self):
        """Apply the schedule"""
        self.ensure_one()
        
        if self.schedule_type == 'immediate':
            self.campaign_id.action_send_campaign()
        elif self.schedule_type == 'scheduled':
            if not self.scheduled_date:
                raise UserError("Please select a scheduled date.")
            self.campaign_id.write({
                'schedule_type': 'scheduled',
                'schedule_date': self.scheduled_date,
            })
            self.campaign_id.action_send_campaign()
        elif self.schedule_type == 'recurring':
            raise UserError("Recurring campaigns are not implemented yet.")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Scheduled',
                'message': 'Campaign scheduled successfully',
                'type': 'success',
            }
        }
