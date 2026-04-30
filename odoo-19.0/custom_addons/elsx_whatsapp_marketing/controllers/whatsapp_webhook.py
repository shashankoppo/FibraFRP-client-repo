# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class WhatsAppWebhook(http.Controller):

    @http.route('/whatsapp/webhook/<int:account_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def whatsapp_webhook_verify(self, account_id, **kwargs):
        """Webhook verification for WhatsApp Cloud API"""
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        
        account = request.env['whatsapp.account'].sudo().browse(account_id)
        
        if mode == 'subscribe' and token == account.webhook_verify_token:
            _logger.info(f'WhatsApp webhook verified for account {account_id}')
            return challenge
        else:
            _logger.warning(f'WhatsApp webhook verification failed for account {account_id}')
            return 'Verification failed', 403

    @http.route('/whatsapp/webhook/<int:account_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def whatsapp_webhook_receive(self, account_id, **kwargs):
        """Receive incoming WhatsApp messages (HTTP to handle raw Meta JSON)"""
        try:
            raw_data = request.httprequest.data.decode('utf-8')
            data = json.loads(raw_data)
            _logger.info(f'WhatsApp webhook received: {data}')
            
            account = request.env['whatsapp.account'].sudo().browse(account_id)
            if not account:
                return 'Account not found', 404
            
            # Process webhook data
            if 'entry' in data:
                for entry in data['entry']:
                    for change in entry.get('changes', []):
                        value = change.get('value', {})
                        
                        # Process incoming messages
                        if 'messages' in value:
                            for message in value['messages']:
                                self._process_incoming_message(account, message, value, raw_data)
                        
                        # Process message status updates
                        if 'statuses' in value:
                            for status in value['statuses']:
                                self._process_status_update(account, status)
            
            return 'OK', 200
            
        except Exception as e:
            _logger.error(f'WhatsApp webhook error: {str(e)}')
            return 'Internal Error', 500
    
    def _process_incoming_message(self, account, message_data, value, raw_json):
        """Process incoming WhatsApp message including interactive types"""
        phone_number = message_data.get('from')
        message_id = message_data.get('id')
        message_type = message_data.get('type')
        
        vals = {
            'account_id': account.id,
            'phone_number': phone_number,
            'message_id': message_id,
            'message_type': message_type,
            'direction': 'inbound',
            'status': 'delivered',
            'raw_data': raw_json,
        }

        # Get message content based on type
        if message_type == 'text':
            vals['body'] = message_data.get('text', {}).get('body', '')
        elif message_type == 'image':
            vals['caption'] = message_data.get('image', {}).get('caption', '')
            # Future: Handle media download
        elif message_type == 'button':
            vals['body'] = message_data.get('button', {}).get('text', '')
            vals['button_text'] = vals['body']
            vals['button_payload'] = message_data.get('button', {}).get('payload', '')
        elif message_type == 'interactive':
            interactive = message_data.get('interactive', {})
            if interactive.get('type') == 'button_reply':
                reply = interactive.get('button_reply', {})
                vals['body'] = reply.get('title', '')
                vals['button_text'] = vals['body']
                vals['button_payload'] = reply.get('id', '')
            elif interactive.get('type') == 'list_reply':
                reply = interactive.get('list_reply', {})
                vals['body'] = reply.get('title', '')
                vals['list_item_id'] = reply.get('id', '')
                vals['list_item_title'] = reply.get('title', '')
        
        # Find partner
        partner = request.env['res.partner'].sudo().search([
            '|', ('mobile', '=', phone_number), ('phone', '=', phone_number)
        ], limit=1)
        if partner:
            vals['partner_id'] = partner.id
        
        # Create message record
        request.env['whatsapp.message'].sudo().create(vals)
        
        # Automation & AI
        if account.auto_reply_enabled and account.auto_reply_message:
            account.send_message(to_number=phone_number, message_type='text', body=account.auto_reply_message)
        elif account.ai_enabled:
            reply_text = self._get_ai_response(account, vals.get('body', ''), phone_number)
            if reply_text:
                account.send_message(to_number=phone_number, message_type='text', body=reply_text)

    def _get_ai_response(self, account, user_message, phone_number):
        """Simulate AI response generation"""
        msg = user_message.lower()
        if any(word in msg for word in ['invoice', 'bill', 'pay']):
            return "I've found your latest invoice. Would you like me to send a payment link? 💳"
        elif any(word in msg for word in ['track', 'where', 'delivery']):
            return "I can check your delivery status. Please provide your Order ID. 🚚"
        return f"Thank you for reaching out! We've received your message: '{user_message}'."
    
    def _process_status_update(self, account, status_data):
        """Process message status update"""
        message_id = status_data.get('id')
        status = status_data.get('status')
        
        message = request.env['whatsapp.message'].sudo().search([
            ('message_id', '=', message_id),
            ('account_id', '=', account.id)
        ], limit=1)
        
        if message:
            vals = {'status': status}
            if status == 'delivered':
                vals['delivered_date'] = fields.Datetime.now()
            elif status == 'read':
                vals['read_date'] = fields.Datetime.now()
            message.write(vals)
