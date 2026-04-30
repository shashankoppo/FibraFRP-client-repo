# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta

class WhatsAppCampaignParticipant(models.Model):
    _name = 'whatsapp.campaign.participant'
    _description = 'WhatsApp Campaign Participant'
    
    print("DEBUG: Loading WhatsAppCampaignParticipant model")

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
        """Cron job to process drip campaigns"""
        participants = self.search([
            ('state', '=', 'running'),
            ('next_execution_date', '<=', fields.Datetime.now())
        ])
        
        for participant in participants:
            # Find next step
            next_step = self.env['whatsapp.campaign.step'].search([
                ('campaign_id', '=', participant.campaign_id.id),
                ('sequence', '>', participant.current_step_id.sequence if participant.current_step_id else -1)
            ], order='sequence', limit=1)
            
            if next_step:
                # Send message
                participant.campaign_id.account_id.send_message(
                    to_number=participant.partner_id.mobile or participant.partner_id.phone,
                    message_type='template' if next_step.template_id else 'text',
                    body=next_step.message_body,
                    template=next_step.template_id.name if next_step.template_id else False,
                    partner_id=participant.partner_id.id
                )
                
                # Calculate next execution
                delay = participant._get_delay_timedelta(next_step)
                participant.write({
                    'current_step_id': next_step.id,
                    'next_execution_date': fields.Datetime.now() + delay
                })
            else:
                participant.state = 'completed'

    def _get_delay_timedelta(self, step):
        if step.delay_type == 'minutes':
            return timedelta(minutes=step.delay_unit)
        elif step.delay_type == 'hours':
            return timedelta(hours=step.delay_unit)
        else:
            return timedelta(days=step.delay_unit)
