# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class WhatsAppCampaignParticipant(models.Model):
    _name = 'whatsapp.campaign.participant'
    _description = 'WhatsApp Campaign Participant'
    
    _campaign_partner_unique = models.Constraint(
        'unique(campaign_id, partner_id)',
        'A contact can only be added once per campaign.',
    )
    
    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Contact', required=True)
    current_step_id = fields.Many2one('whatsapp.campaign.step', string='Current Step')
    next_execution_date = fields.Datetime('Next Execution')
    state = fields.Selection([
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
        ('stopped', 'Stopped'),
    ], string='Status', default='running')
    def process_drip_campaigns(self):
        """Cron job to process drip campaigns for all participants"""
        participants = self.search([
            ('state', '=', 'running'),
            ('next_execution_date', '<=', fields.Datetime.now())
        ])
        
        for participant in participants:
            # Check opt-in status dynamically before executing any steps
            contact = self.env['whatsapp.contact'].sudo().search([('partner_id', '=', participant.partner_id.id)], limit=1)
            partner_opted_in = getattr(participant.partner_id, 'whatsapp_opt_in', True)
            is_opted_out = (contact and not contact.opt_in) or (not partner_opted_in)
            if is_opted_out:
                participant.write({'state': 'stopped'})
                _logger.info(f"Drip Campaign stopped for {participant.partner_id.name} due to opt-out.")
                continue

            # Find next step based on sequence
            next_step = self.env['whatsapp.campaign.step'].search([
                ('campaign_id', '=', participant.campaign_id.id),

                ('sequence', '>', participant.current_step_id.sequence if participant.current_step_id else -1)
            ], order='sequence', limit=1)
            
            if next_step:
                if not participant._condition_matches_step(next_step):
                    participant.write({
                        'next_execution_date': fields.Datetime.now() + timedelta(minutes=15),
                    })
                    continue

                # Resolve attributes/variables for template if needed
                body = next_step.message_body
                
                # Send message via the account's standard send method
                try:
                    phone = getattr(participant.partner_id, 'mobile', False) or participant.partner_id.phone
                    if not phone:
                        raise ValueError("Participant has no phone number")
                    send_vals = {
                        'to_number': phone,
                        'message_type': 'template' if next_step.template_id else 'text',
                        'body': body,
                        'partner_id': participant.partner_id.id,
                        'campaign_id': participant.campaign_id.id,
                    }
                    if next_step.template_id:
                        send_vals['template_record'] = next_step.template_id
                    participant.campaign_id.account_id.send_message(**send_vals)
                except Exception as e:
                    _logger.error(f"Drip Campaign step failed for {participant.partner_id.name}: {e}")
                    participant.write({
                        'next_execution_date': fields.Datetime.now() + timedelta(minutes=15),
                    })
                    continue
                
                # Calculate next execution date based on step delay
                delay = participant._get_delay_timedelta(next_step)
                participant.write({
                    'current_step_id': next_step.id,
                    'next_execution_date': fields.Datetime.now() + delay
                })
            else:
                # No more steps found, mark as completed
                participant.state = 'completed'

    def _get_delay_timedelta(self, step):
        if step.delay_type == 'minutes':
            return timedelta(minutes=step.delay_unit)
        elif step.delay_type == 'hours':
            return timedelta(hours=step.delay_unit)
        else:
            return timedelta(days=step.delay_unit)

    def _condition_matches_step(self, step):
        self.ensure_one()
        if not step or step.condition_type in (False, 'none'):
            return True

        last_campaign_message = self.env['whatsapp.message'].search([
            ('campaign_id', '=', self.campaign_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('direction', '=', 'outbound'),
        ], order='create_date desc', limit=1)

        if step.condition_type == 'last_read':
            return bool(last_campaign_message and last_campaign_message.status == 'read')
        if step.condition_type == 'last_not_read':
            return bool(last_campaign_message and last_campaign_message.status != 'read')
        if step.condition_type == 'last_delivered':
            return bool(last_campaign_message and last_campaign_message.status in ('delivered', 'read'))
        if step.condition_type == 'last_failed':
            return bool(last_campaign_message and last_campaign_message.status == 'failed')

        last_inbound = self.env['whatsapp.message'].search([
            ('campaign_id', '=', self.campaign_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('direction', '=', 'inbound'),
        ], order='create_date desc', limit=1)
        if step.condition_type in ('replied', 'clicked'):
            if not last_inbound:
                return False
            if not last_campaign_message:
                return True
            if last_inbound.create_date < last_campaign_message.create_date:
                return False
            if step.condition_type == 'clicked':
                return bool(last_inbound.button_payload or last_inbound.list_item_id)
            return True
        if step.condition_type in ('not_replied', 'no_reply'):
            if not last_campaign_message:
                return False
            return not last_inbound or last_inbound.create_date < last_campaign_message.create_date
        return True
