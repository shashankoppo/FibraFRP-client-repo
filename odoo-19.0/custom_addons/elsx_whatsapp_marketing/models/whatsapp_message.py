# -*- coding: utf-8 -*-
from odoo import models, fields, api
import requests
import json
import logging

_logger = logging.getLogger(__name__)


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

    # Interactive Data
    button_text = fields.Char('Button Text', help='Text of the button clicked')
    button_payload = fields.Char('Button Payload', help='Developer payload of the button')
    list_item_id = fields.Char('List Item ID', help='ID of the list item selected')
    list_item_title = fields.Char('List Item Title')

    # Conversation Grouping
    chat_id = fields.Char('Chat ID', compute='_compute_chat_id', store=True)
    chat_id_ref = fields.Many2one('whatsapp.chat', string='Conversation', ondelete='cascade')
    raw_data = fields.Text('Raw Meta Data', help='Complete JSON payload from Meta')

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

    @api.depends('phone_number', 'account_id')
    def _compute_chat_id(self):
        for record in self:
            if record.phone_number and record.account_id:
                record.chat_id = f"{record.account_id.id}_{record.phone_number}"
            else:
                record.chat_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('chat_id_ref'):
                account_id = vals.get('account_id')
                phone = vals.get('phone_number')
                if account_id and phone:
                    chat = self.env['whatsapp.chat'].sudo().search([
                        ('account_id', '=', account_id),
                        ('phone_number', '=', phone)
                    ], limit=1)
                    if not chat:
                        chat = self.env['whatsapp.chat'].sudo().create({
                            'account_id': account_id,
                            'phone_number': phone,
                            'partner_id': vals.get('partner_id'),
                        })
                    vals['chat_id_ref'] = chat.id
        return super().create(vals_list)

    @staticmethod
    def _normalize_phone(phone):
        """Ensure phone number has country code (strip spaces, +, dashes).
        If the number is 10 digits and starts with a digit 6-9, prepend India code 91."""
        if not phone:
            return phone
        # Strip whitespace, +, -, spaces
        clean = phone.strip().replace('+', '').replace('-', '').replace(' ', '')
        # If 10 digits and starts with 6-9, assume Indian number
        if len(clean) == 10 and clean[0] in '6789':
            clean = '91' + clean
        return clean

    def action_send(self):
        """Send the message via WhatsApp Cloud API directly, updating this record's status."""
        for record in self:
            if record.status != 'draft':
                continue

            account = record.account_id
            phone = self._normalize_phone(record.phone_number)

            # Update phone number if normalization changed it
            if phone != record.phone_number:
                record.phone_number = phone

            url = f"https://graph.facebook.com/{account.api_version}/{account.phone_number_id}/messages"
            headers = {
                'Authorization': f'Bearer {account.access_token}',
                'Content-Type': 'application/json',
            }
            payload = {
                'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': phone,
            }

            if record.message_type == 'text':
                payload['type'] = 'text'
                payload['text'] = {'body': record.body or ' '}  # Meta requires non-empty body
            elif record.message_type == 'template':
                payload['type'] = 'template'
                try:
                    payload['template'] = json.loads(record.raw_data or '{}')
                except Exception:
                    payload['template'] = {}
            elif record.message_type == 'interactive':
                payload['type'] = 'interactive'
                try:
                    payload['interactive'] = json.loads(record.raw_data or '{}')
                except Exception:
                    payload['interactive'] = {}

            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                response_data = response.json()

                if response.status_code == 200:
                    wamid = response_data.get('messages', [{}])[0].get('id', '')
                    record.write({
                        'status': 'sent',
                        'sent_date': fields.Datetime.now(),
                        'message_id': wamid,
                        'raw_data': json.dumps(payload),
                        'error_message': False,
                    })
                    _logger.info(f"WhatsApp message sent to {phone}, wamid={wamid}")
                else:
                    error = response_data.get('error', {})
                    error_msg = f"[{error.get('code', '?')}] {error.get('message', str(response_data))}"
                    record.write({
                        'status': 'failed',
                        'error_message': error_msg,
                    })
                    _logger.error(f"WhatsApp send failed for {phone}: {error_msg}")

            except Exception as e:
                record.write({
                    'status': 'failed',
                    'error_message': str(e),
                })
                _logger.error(f"WhatsApp send exception for {phone}: {str(e)}")

    def action_retry(self):
        """Retry sending failed message"""
        self.write({'status': 'draft', 'error_message': False})
        return self.action_send()
