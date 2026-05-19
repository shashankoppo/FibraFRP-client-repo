# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import json

_logger = logging.getLogger(__name__)


class WhatsAppBotRule(models.Model):
    _name = 'whatsapp.bot.rule'
    _description = 'WhatsApp Bot Keyword Rule'
    _order = 'sequence, id'

    name = fields.Char('Rule Name', required=True)
    account_id = fields.Many2one('whatsapp.account', string='Account')
    sequence = fields.Integer('Priority', default=10)
    active = fields.Boolean('Active', default=True)

    # Trigger
    trigger_type = fields.Selection([
        ('keyword', 'Keyword Match'),
        ('first_message', 'First Message Ever'),
        ('no_reply_24h', 'No Reply in 24 Hours'),
        ('any', 'Any Incoming Message'),
    ], string='Trigger', default='keyword', required=True)

    keywords = fields.Char('Keywords', help='Comma-separated keywords that trigger this rule (e.g. hello, hi, start)')

    # Action
    action_type = fields.Selection([
        ('text', 'Send Text Message'),
        ('template', 'Send Template'),
        ('transfer', 'Transfer to Agent'),
        ('assign_label', 'Assign Label'),
    ], string='Action', default='text', required=True)

    reply_text = fields.Text('Reply Text')
    template_id = fields.Many2one('whatsapp.template', string='Template')
    assign_user_id = fields.Many2one('res.users', string='Assign to Agent')
    tag_id = fields.Many2one('res.partner.category', string='Label to Assign')

    def check_and_fire(self, env, account, phone_number, body, partner_id=None, chat_id=None):
        """Check if this rule matches and fire the action. Returns True if matched."""
        self.ensure_one()
        matched = False

        if self.trigger_type == 'keyword':
            keywords = [k.strip().lower() for k in (self.keywords or '').split(',') if k.strip()]
            matched = any(kw in (body or '').lower() for kw in keywords)
        elif self.trigger_type == 'first_message':
            count = env['whatsapp.message'].sudo().search_count([
                ('account_id', '=', account.id),
                ('phone_number', '=', phone_number),
                ('direction', '=', 'inbound'),
            ])
            matched = count <= 1
        elif self.trigger_type == 'no_reply_24h':
            _logger.info("Bot rule '%s' no_reply_24h trigger has no runtime scheduler yet.", self.name)
            matched = False
        elif self.trigger_type == 'any':
            matched = True

        if not matched:
            return False

        # Fire the action
        try:
            if self.action_type == 'text' and self.reply_text:
                msg = env['whatsapp.message'].sudo().create({
                    'account_id': account.id,
                    'phone_number': phone_number,
                    'partner_id': partner_id,
                    'message_type': 'text',
                    'body': self.reply_text,
                    'direction': 'outbound',
                    'chat_id_ref': chat_id,
                    'is_automated': True,
                })
                msg.action_send()

            elif self.action_type == 'template' and self.template_id:
                partner = env['res.partner'].sudo().browse(partner_id) if partner_id else False
                template_payload = self.template_id._prepare_send_payload(partner=partner)
                msg = env['whatsapp.message'].sudo().create({
                    'account_id': account.id,
                    'phone_number': phone_number,
                    'partner_id': partner_id,
                    'message_type': 'template',
                    'body': self.template_id.body,
                    'template_id': self.template_id.id,
                    'template_name': self.template_id._get_send_template_name(),
                    'template_language': self.template_id._get_send_language_code(),
                    'raw_data': json.dumps(template_payload),
                    'direction': 'outbound',
                    'chat_id_ref': chat_id,
                    'is_automated': True,
                })
                msg.action_send()

            elif self.action_type == 'transfer' and self.assign_user_id and chat_id:
                env['whatsapp.chat'].sudo().browse(chat_id).write({
                    'assigned_user_id': self.assign_user_id.id,
                    'state': 'open',
                })

            elif self.action_type == 'assign_label' and self.tag_id and chat_id:
                env['whatsapp.chat'].sudo().browse(chat_id).write({
                    'tag_ids': [(4, self.tag_id.id)],
                })

        except Exception as e:
            _logger.error(f"Bot Rule '{self.name}' action failed: {e}")

        return True
