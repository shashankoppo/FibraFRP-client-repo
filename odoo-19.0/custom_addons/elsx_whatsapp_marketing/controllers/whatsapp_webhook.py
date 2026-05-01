# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request, Response
import json
import logging

_logger = logging.getLogger(__name__)

FALLBACK_VERIFY_TOKEN = 'elsx_verify_2024'


class WhatsAppWebhook(http.Controller):

    @http.route('/whatsapp/webhook/<int:account_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def whatsapp_webhook_verify(self, account_id, **kwargs):
        """Webhook verification for WhatsApp Cloud API"""
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        _logger.info(f'Webhook verify attempt: mode={mode}, token={token}, account={account_id}')

        account = request.env['whatsapp.account'].sudo().browse(account_id)

        # Accept the hardcoded fallback OR the token set on the account
        account_token = (account and account.webhook_verify_token) or ''
        valid_tokens = [t for t in [account_token, FALLBACK_VERIFY_TOKEN] if t]

        if mode == 'subscribe' and token in valid_tokens:
            _logger.info(f'WhatsApp webhook verified for account {account_id}')
            # Auto-save the token if not set
            if account and not account.webhook_verify_token:
                account.sudo().write({'webhook_verify_token': token})
            return Response(challenge, status=200)
        else:
            _logger.warning(f'Webhook verification FAILED. Got: {token}, Expected one of: {valid_tokens}')
            return Response('Verification failed', status=403)

    @http.route('/whatsapp/webhook/<int:account_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def whatsapp_webhook_receive(self, account_id, **kwargs):
        """Receive incoming WhatsApp messages"""
        try:
            raw_data = request.httprequest.data.decode('utf-8')
            data = json.loads(raw_data)
            _logger.info(f'WhatsApp webhook received for account {account_id}')

            account = request.env['whatsapp.account'].sudo().browse(account_id)
            if not account.exists():
                _logger.error(f'Account {account_id} not found')
                return Response('Account not found', status=404)

            if 'entry' in data:
                for entry in data['entry']:
                    for change in entry.get('changes', []):
                        value = change.get('value', {})

                        # Incoming messages
                        if 'messages' in value:
                            for message in value['messages']:
                                self._process_incoming_message(account, message, value, raw_data)

                        # Status updates (sent/delivered/read)
                        if 'statuses' in value:
                            for status in value['statuses']:
                                self._process_status_update(account, status)

            return Response('OK', status=200)

        except Exception as e:
            _logger.error(f'WhatsApp webhook error: {str(e)}', exc_info=True)
            return Response('Internal Error', status=500)

    def _process_incoming_message(self, account, message_data, value, raw_json):
        """Process and store an incoming WhatsApp message"""
        phone_number = message_data.get('from', '')
        message_id = message_data.get('id', '')
        message_type = message_data.get('type', 'text')

        # Prevent duplicate messages
        existing = request.env['whatsapp.message'].sudo().search([
            ('message_id', '=', message_id)
        ], limit=1)
        if existing:
            _logger.info(f'Duplicate message {message_id}, skipping')
            return

        body = ''
        vals = {
            'account_id': account.id,
            'phone_number': phone_number,
            'message_id': message_id,
            'message_type': message_type,
            'direction': 'inbound',
            'status': 'delivered',
            'raw_data': raw_json,
        }

        if message_type == 'text':
            body = message_data.get('text', {}).get('body', '')
            vals['body'] = body
        elif message_type == 'image':
            body = message_data.get('image', {}).get('caption', '[Image]')
            vals['body'] = body
            vals['caption'] = body
        elif message_type == 'video':
            body = '[Video]'
            vals['body'] = body
        elif message_type == 'audio':
            body = '[Audio]'
            vals['body'] = body
        elif message_type == 'document':
            body = message_data.get('document', {}).get('filename', '[Document]')
            vals['body'] = body
        elif message_type == 'button':
            body = message_data.get('button', {}).get('text', '')
            vals['body'] = body
            vals['button_text'] = body
            vals['button_payload'] = message_data.get('button', {}).get('payload', '')
        elif message_type == 'interactive':
            interactive = message_data.get('interactive', {})
            if interactive.get('type') == 'button_reply':
                reply = interactive.get('button_reply', {})
                body = reply.get('title', '')
                vals['body'] = body
                vals['button_text'] = body
                vals['button_payload'] = reply.get('id', '')
            elif interactive.get('type') == 'list_reply':
                reply = interactive.get('list_reply', {})
                body = reply.get('title', '')
                vals['body'] = body
                vals['list_item_id'] = reply.get('id', '')
                vals['list_item_title'] = body
        else:
            vals['body'] = f'[{message_type}]'

        # Link to existing contact
        partner = request.env['res.partner'].sudo().search([
            '|', ('mobile', '=', phone_number), ('phone', '=', phone_number)
        ], limit=1)
        if partner:
            vals['partner_id'] = partner.id

        request.env['whatsapp.message'].sudo().create(vals)
        _logger.info(f'Saved inbound message from {phone_number}: {body[:50]}')

        # Auto-reply logic
        if account.auto_reply_enabled and account.auto_reply_message:
            account.send_message(to_number=phone_number, message_type='text', body=account.auto_reply_message)

    def _process_status_update(self, account, status_data):
        """Update message delivery status from Meta webhook"""
        message_id = status_data.get('id')
        new_status = status_data.get('status')

        if not message_id or not new_status:
            return

        message = request.env['whatsapp.message'].sudo().search([
            ('message_id', '=', message_id),
        ], limit=1)

        if message:
            update_vals = {'status': new_status}
            if new_status == 'delivered':
                update_vals['delivered_date'] = fields.Datetime.now()
            elif new_status == 'read':
                update_vals['read_date'] = fields.Datetime.now()
            message.sudo().write(update_vals)
            _logger.info(f'Message {message_id} status updated to {new_status}')
