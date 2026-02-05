# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WhatsAppTemplate(models.Model):
    _name = 'whatsapp.template'
    _description = 'WhatsApp Message Template'
    _rec_name = 'name'

    name = fields.Char('Template Name', required=True)
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=False)
    
    # Template details
    template_id = fields.Char('Template ID', help='WhatsApp approved template ID')
    language = fields.Selection([
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('pt', 'Portuguese'),
        ('hi', 'Hindi'),
    ], string='Language', default='en', required=True)
    
    category = fields.Selection([
        ('marketing', 'Marketing'),
        ('utility', 'Utility'),
        ('authentication', 'Authentication'),
    ], string='Category', default='marketing', required=True)
    
    # Content
    header_type = fields.Selection([
        ('none', 'None'),
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
    ], string='Header Type', default='none')
    
    header_text = fields.Char('Header Text')
    header_media_url = fields.Char('Header Media URL')
    
    body = fields.Text('Body', required=True, help='Use {{1}}, {{2}} for variables')
    footer = fields.Char('Footer')
    
    # Buttons
    has_buttons = fields.Boolean('Has Buttons', default=False)
    button_type = fields.Selection([
        ('quick_reply', 'Quick Reply'),
        ('call_to_action', 'Call to Action'),
    ], string='Button Type')
    
    button_text_1 = fields.Char('Button 1 Text')
    button_text_2 = fields.Char('Button 2 Text')
    button_text_3 = fields.Char('Button 3 Text')
    
    # Status
    status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', required=True)
    
    active = fields.Boolean('Active', default=True)
    
    # Usage statistics
    usage_count = fields.Integer('Times Used', default=0)
    
    def action_preview(self):
        """Preview the template"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Template Preview',
            'res_model': 'whatsapp.template',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
