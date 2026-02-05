# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WhatsAppMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'create_date desc'
    _rec_name = 'phone_number'

    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Contact')
    phone_number = fields.Char('Phone Number', required=True)
    
    # Message details
    message_id = fields.Char('Message ID', help='WhatsApp Cloud API Message ID')
    message_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('template', 'Template'),
        ('interactive', 'Interactive'),
    ], string='Type', default='text', required=True)
    
    direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Direction', required=True, default='outbound')
    
    body = fields.Text('Message Body')
    media_url = fields.Char('Media URL')
    caption = fields.Text('Caption')
    
    # Status tracking
    status = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    ], string='Status', default='draft', required=True)
    
    error_message = fields.Text('Error Message')
    
    # Campaign relation
    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign', ondelete='set null')
    
    # Timestamps
    sent_date = fields.Datetime('Sent Date')
    delivered_date = fields.Datetime('Delivered Date')
    read_date = fields.Datetime('Read Date')
    
    # Automation
    is_automated = fields.Boolean('Automated Message', default=False)
    trigger_event = fields.Char('Trigger Event')
    
    def action_send(self):
        """Send the message via WhatsApp"""
        for record in self:
            if record.status != 'draft':
                continue
            
            try:
                record.account_id.send_message(
                    to_number=record.phone_number,
                    message_type=record.message_type,
                    body=record.body,
                )
                record.write({
                    'status': 'sent',
                    'sent_date': fields.Datetime.now(),
                })
            except Exception as e:
                record.write({
                    'status': 'failed',
                    'error_message': str(e),
                })
    
    def action_retry(self):
        """Retry sending failed message"""
        self.write({'status': 'draft', 'error_message': False})
        return self.action_send()
