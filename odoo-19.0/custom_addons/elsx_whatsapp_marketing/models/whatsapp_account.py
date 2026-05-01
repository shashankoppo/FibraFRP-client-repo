# -*- coding: utf-8 -*-
from odoo import models, fields, api
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class WhatsAppAccount(models.Model):
    _name = 'whatsapp.account'
    _description = 'WhatsApp Business Account'
    _rec_name = 'name'

    name = fields.Char('Account Name', required=True)
    phone_number = fields.Char('Phone Number', required=True, help='WhatsApp Business phone number with country code')
    phone_number_id = fields.Char('Phone Number ID', required=True, help='WhatsApp Cloud API Phone Number ID')
    business_account_id = fields.Char('Business Account ID', required=True)
    access_token = fields.Char('Access Token', required=True, help='WhatsApp Cloud API Access Token')
    api_version = fields.Char('API Version', default='v18.0')
    
    # Status
    active = fields.Boolean('Active', default=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
        ('error', 'Error'),
    ], string='Status', default='draft')
    
    # Statistics
    message_count = fields.Integer('Total Messages', compute='_compute_statistics')
    campaign_count = fields.Integer('Total Campaigns', compute='_compute_statistics')
    
    # Relations
    message_ids = fields.One2many('whatsapp.message', 'account_id', string='Messages')
    campaign_ids = fields.One2many('whatsapp.campaign', 'account_id', string='Campaigns')
    template_ids = fields.One2many('whatsapp.template', 'account_id', string='Templates')
    
    # Settings
    auto_reply_enabled = fields.Boolean('Auto Reply Enabled', default=False)
    auto_reply_message = fields.Text('Auto Reply Message')
    webhook_url = fields.Char('Webhook URL', compute='_compute_webhook_url')
    webhook_verify_token = fields.Char('Webhook Verify Token', default='elsx_verify_2024')
    two_factor_pin = fields.Char('2FA PIN (for Registration)', help='6-digit PIN for two-step verification registration')

    # AI & Automation
    ai_enabled = fields.Boolean('AI Automation Enabled', default=True)
    ai_model = fields.Selection([
        ('gpt-4o', 'GPT-4o (Premium)'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('claude-3-5-sonnet', 'Claude 3.5 Sonnet'),
    ], string='AI Model', default='gpt-4o')
    ai_context = fields.Text('AI Business Context', help='Tell the AI about your business to generate better replies.')
    
    # Template Sync
    last_sync_date = fields.Datetime('Last Template Sync')
    
    @api.depends('message_ids', 'campaign_ids')
    def _compute_statistics(self):
        for record in self:
            record.message_count = len(record.message_ids)
            record.campaign_count = len(record.campaign_ids)
    
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.webhook_url = f"{base_url}/whatsapp/webhook/{record.id}"
    
    def action_test_connection(self):
        """Test WhatsApp Cloud API connection"""
        self.ensure_one()
        try:
            url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.status = 'connected'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success!',
                        'message': 'WhatsApp account connected successfully',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.status = 'error'
                raise Exception(f"API Error: {response.text}")
                
        except Exception as e:
            self.status = 'error'
            _logger.error(f"WhatsApp connection test failed: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Failed',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_register_phone(self):
        """
        Finalize registration to move phone number from 'Pending' to 'Connected'.
        Requires a 6-digit PIN to be set on the account.
        """
        self.ensure_one()
        if not self.two_factor_pin or len(self.two_factor_pin) != 6:
            from odoo.exceptions import UserError
            raise UserError("Please enter a valid 6-digit 2FA PIN.")

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/register"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'messaging_product': 'whatsapp',
            'pin': self.two_factor_pin,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response_data = response.json()

            if response.status_code == 200:
                self.status = 'connected'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Registration Successful',
                        'message': 'Your phone number is now registered and connected.',
                        'type': 'success',
                    }
                }
            else:
                error = response_data.get('error', {})
                msg = f"[{error.get('code', '?')}] {error.get('message', 'Unknown error')}"
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Registration Failed',
                        'message': msg,
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error(f"WhatsApp registration failed: {str(e)}")
            raise

    def action_sync_templates(self):
        """Sync templates from Meta WhatsApp Business Account"""
        self.ensure_one()
        url = f"https://graph.facebook.com/{self.api_version}/{self.business_account_id}/message_templates"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                templates_data = response.json().get('data', [])
                for t_data in templates_data:
                    template = self.env['whatsapp.template'].search([
                        ('name', '=', t_data.get('name')),
                        ('account_id', '=', self.id)
                    ], limit=1)
                    
                    vals = {
                        'name': t_data.get('name'),
                        'template_id': t_data.get('id'),
                        'language': t_data.get('language'),
                        'category': t_data.get('category').lower(),
                        'status': t_data.get('status').lower(),
                        'account_id': self.id,
                    }
                    
                    # Extract body content
                    for component in t_data.get('components', []):
                        if component.get('type') == 'BODY':
                            vals['body'] = component.get('text')
                        elif component.get('type') == 'HEADER':
                            vals['header_type'] = component.get('format').lower()
                            if vals['header_type'] == 'text':
                                vals['header_text'] = component.get('text')
                        elif component.get('type') == 'FOOTER':
                            vals['footer'] = component.get('text')
                    
                    if template:
                        template.write(vals)
                    else:
                        self.env['whatsapp.template'].create(vals)
                
                self.last_sync_date = fields.Datetime.now()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Templates Synced',
                        'message': f'Successfully synced {len(templates_data)} templates from Meta.',
                        'type': 'success',
                    }
                }
            else:
                raise Exception(f"Meta API Error: {response.text}")
        except Exception as e:
            _logger.error(f"Template sync failed: {str(e)}")
            raise

    def send_message(self, to_number, message_type='text', **kwargs):
        """
        Send WhatsApp message via Cloud API with support for Interactive messages
        """
        self.ensure_one()
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to_number,
        }
        
        if message_type == 'text':
            payload['type'] = 'text'
            payload['text'] = {'body': kwargs.get('body', '')}
        elif message_type == 'template':
            payload['type'] = 'template'
            payload['template'] = kwargs.get('template', {})
        elif message_type == 'image':
            payload['type'] = 'image'
            payload['image'] = kwargs.get('image', {})
        elif message_type == 'interactive':
            payload['type'] = 'interactive'
            payload['interactive'] = kwargs.get('interactive', {})
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response_data = response.json()
            
            vals = {
                'account_id': self.id,
                'phone_number': to_number,
                'partner_id': kwargs.get('partner_id'),
                'message_type': message_type,
                'body': kwargs.get('body', ''),
                'direction': 'outbound',
                'raw_data': json.dumps(payload),
            }

            if response.status_code == 200:
                vals.update({
                    'status': 'sent',
                    'message_id': response_data.get('messages', [{}])[0].get('id'),
                    'sent_date': fields.Datetime.now(),
                })
            else:
                _logger.error(f"WhatsApp send failed: {response_data}")
                vals.update({
                    'status': 'failed',
                    'error_message': str(response_data.get('error', {}).get('message', 'Unknown error')),
                })
            
            return self.env['whatsapp.message'].create(vals)
                
        except Exception as e:
            _logger.error(f"WhatsApp message send error: {str(e)}")
            raise

    def action_send_interactive_buttons(self, to_number, body, buttons):
        """
        Helper to send interactive buttons
        :param buttons: List of dicts [{'id': 'id1', 'title': 'Button 1'}, ...]
        """
        interactive_payload = {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [{"type": "reply", "reply": b} for b in buttons]
            }
        }
        return self.send_message(to_number, message_type='interactive', interactive=interactive_payload, body=body)

    def action_send_list_menu(self, to_number, body, button_text, sections):
        """
        Helper to send list menu
        :param sections: List of sections for the list
        """
        interactive_payload = {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
        return self.send_message(to_number, message_type='interactive', interactive=interactive_payload, body=body)
