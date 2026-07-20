# -*- coding: utf-8 -*-
from odoo import api, fields, models


class WhatsAppPlaceholder(models.Model):
    _name = 'whatsapp.placeholder'
    _description = 'WhatsApp Placeholder Registry'
    _order = 'sequence, context_type, placeholder'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    placeholder = fields.Char(required=True, help="Token used in messages, for example {{name}}.")
    context_type = fields.Selection([
        ('all', 'All'),
        ('contact', 'Contact'),
        ('chat', 'Team Inbox / Chat'),
        ('campaign', 'Campaign'),
        ('flow', 'Bot Flow'),
        ('crm', 'CRM'),
        ('invoice', 'Invoice'),
        ('ai', 'AI Prompt'),
    ], default='all', required=True)
    sample_value = fields.Char()
    description = fields.Text()

    _placeholder_unique = models.Constraint(
        'unique(placeholder, context_type)',
        'Placeholder must be unique per context.',
    )

    @api.model
    def get_placeholder_values(self, context_type='all', partner=False, chat=False, record=False, extra=None):
        """Return runtime values for known placeholders.

        The values are intentionally conservative and safe for previews. Flow
        variables and AI prompt values can pass an explicit `extra` dict.
        """
        values = {}
        extra = extra or {}
        partner = partner or getattr(chat, 'partner_id', False)
        if partner:
            values.update({
                '{{name}}': partner.name or '',
                '{{partner_name}}': partner.name or '',
                '{{customer_name}}': partner.name or '',
                '{{company}}': getattr(partner, 'company_name', False) or getattr(partner, 'commercial_company_name', False) or '',
                '{{company_name}}': getattr(partner, 'company_name', False) or getattr(partner, 'commercial_company_name', False) or '',
                '{{phone}}': getattr(partner, 'mobile', False) or getattr(partner, 'phone', False) or '',
                '{{phone_number}}': getattr(partner, 'mobile', False) or getattr(partner, 'phone', False) or '',
                '{{mobile}}': getattr(partner, 'mobile', False) or '',
                '{{email}}': getattr(partner, 'email', False) or '',
            })
        if chat:
            values.update({
                '{{last_message}}': getattr(chat, 'last_message_body', False) or '',
                '{{last_reply}}': getattr(chat, 'last_message_body', False) or '',
                '{{chat_status}}': getattr(chat, 'state', False) or '',
                '{{assigned_agent}}': chat.assigned_user_id.name if getattr(chat, 'assigned_user_id', False) else '',
            })
        if record:
            values.update({
                '{{record_name}}': getattr(record, 'display_name', False) or getattr(record, 'name', False) or '',
                '{{document_number}}': getattr(record, 'name', False) or '',
                '{{amount_total}}': getattr(record, 'amount_total', False) or '',
                '{{invoice_total}}': getattr(record, 'amount_total', False) or '',
                '{{invoice_due_date}}': getattr(record, 'invoice_date_due', False) or '',
                '{{opportunity_name}}': getattr(record, 'name', False) if getattr(record, '_name', '') == 'crm.lead' else '',
            })
        values.update(extra)

        domain = [('active', '=', True), ('context_type', 'in', ['all', context_type or 'all'])]
        for placeholder in self.search(domain):
            values.setdefault(placeholder.placeholder, placeholder.sample_value or '')
        return values

    @api.model
    def render_text(self, text, context_type='all', partner=False, chat=False, record=False, extra=None):
        rendered = text or ''
        for token, value in self.get_placeholder_values(
            context_type=context_type,
            partner=partner,
            chat=chat,
            record=record,
            extra=extra,
        ).items():
            rendered = rendered.replace(token, str(value or ''))
        return rendered
