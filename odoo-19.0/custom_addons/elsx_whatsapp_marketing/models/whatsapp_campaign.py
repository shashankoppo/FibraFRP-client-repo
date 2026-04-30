# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

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
    ], string='Target Type', default='segment', required=True)
    
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    domain_filter = fields.Char('Domain Filter', help='Technical domain for filtering contacts')
    
    # Message content
    template_id = fields.Many2one('whatsapp.template', string='Message Template')
    message_body = fields.Text('Message Body', required=True)
    
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
    sent_count = fields.Integer('Sent', compute='_compute_statistics', store=True)
    delivered_count = fields.Integer('Delivered', compute='_compute_statistics', store=True)
    read_count = fields.Integer('Read', compute='_compute_statistics', store=True)
    failed_count = fields.Integer('Failed', compute='_compute_statistics', store=True)
    
    # Relations
    message_ids = fields.One2many('whatsapp.message', 'campaign_id', string='Messages')
    step_ids = fields.One2many('whatsapp.campaign.step', 'campaign_id', string='Drip Steps')
    
    # Analytics
    click_count = fields.Integer('Clicks', default=0)
    conversion_count = fields.Integer('Conversions', default=0)
    roi = fields.Float('ROI %', compute='_compute_roi')
    
    @api.depends('partner_ids')
    def _compute_statistics(self):
        for record in self:
            record.total_recipients = len(record.partner_ids)
            record.sent_count = len(record.message_ids.filtered(lambda m: m.status in ['sent', 'delivered', 'read']))
            record.delivered_count = len(record.message_ids.filtered(lambda m: m.status in ['delivered', 'read']))
            record.read_count = len(record.message_ids.filtered(lambda m: m.status == 'read'))
            record.failed_count = len(record.message_ids.filtered(lambda m: m.status == 'failed'))
    
    def _compute_roi(self):
        for record in self:
            if record.sent_count > 0:
                record.roi = (record.conversion_count / record.sent_count) * 100
            else:
                record.roi = 0.0
    
    def action_load_recipients(self):
        """Load recipients based on target type"""
        self.ensure_one()
        
        if self.target_type == 'all':
            partners = self.env['res.partner'].search([('mobile', '!=', False)])
        elif self.target_type == 'segment' and self.domain_filter:
            partners = self.env['res.partner'].search(eval(self.domain_filter))
        else:
            return
        
        self.partner_ids = [(6, 0, partners.ids)]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recipients Loaded',
                'message': f'{len(partners)} recipients loaded successfully',
                'type': 'success',
            }
        }
    
    def action_send_campaign(self):
        """Send campaign messages or start drip sequence"""
        self.ensure_one()
        
        if not self.partner_ids:
            raise ValueError('No recipients selected')
        
        self.state = 'running'
        
        if self.campaign_type == 'broadcast':
            # Create messages for each recipient
            for partner in self.partner_ids:
                phone = partner.mobile or partner.phone
                if not phone:
                    continue
                
                # Personalize message
                message_body = self.message_body
                message_body = message_body.replace('{{name}}', partner.name or '')
                message_body = message_body.replace('{{company}}', partner.company_name or '')
                
                # Create and send message
                message = self.env['whatsapp.message'].create({
                    'account_id': self.account_id.id,
                    'partner_id': partner.id,
                    'phone_number': phone,
                    'message_type': 'template' if self.template_id else 'text',
                    'body': message_body,
                    'campaign_id': self.id,
                    'direction': 'outbound',
                })
                try:
                    message.action_send()
                except Exception as e:
                    _logger.error(f"Failed to send campaign message to {partner.name}: {str(e)}")
        
        elif self.campaign_type == 'drip':
            # Initialize drip campaign for participants
            for partner in self.partner_ids:
                existing = self.env['whatsapp.campaign.participant'].search([
                    ('campaign_id', '=', self.id),
                    ('partner_id', '=', partner.id)
                ])
                if not existing:
                    self.env['whatsapp.campaign.participant'].create({
                        'campaign_id': self.id,
                        'partner_id': partner.id,
                        'next_execution_date': fields.Datetime.now(),
                        'state': 'running'
                    })
        
        self.state = 'completed'
        
        # Log Campaign Launch to Blockchain Ledger
        try:
             self.env['elsx.blockchain.log'].create({
                'model_name': 'whatsapp.campaign',
                'res_id': self.id,
                'operation': 'write',
                'data_snapshot': f"Campaign Sent: {self.name}, Recipients: {len(self.partner_ids)}, Template: {self.template_id.name if self.template_id else 'None'}",
                'previous_hash': 'CAMPAIGN_LAUNCH',
                'current_hash': 'PENDING_VERIFICATION'
            })
        except Exception as e:
            _logger.warning(f"Blockchain logging failed for campaign {self.name}: {e}")
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Sent',
                'message': f'Campaign sent to {len(self.partner_ids)} recipients',
                'type': 'success',
            }
        }

    def action_generate_ai_content(self):
        """Generate content using ELSX AI Marketing"""
        self.ensure_one()
        # Mocking AI generation call
        ai_suggestion = self.env['elsx.marketing.ai'].create({
            'name': f"AI Draft for {self.name}",
            'target_audience': self.target_type,
            'platform': 'email', # WhatsApp is similar text
        })
        ai_suggestion.action_generate_content()
        if ai_suggestion.generated_content:
             self.message_body = ai_suggestion.generated_content
             
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'AI Content Generated',
                'message': 'AI has drafted your message based. Please review.',
                'type': 'success',
            }
        }
    
    def action_cancel(self):
        """Cancel the campaign"""
        self.state = 'cancelled'
