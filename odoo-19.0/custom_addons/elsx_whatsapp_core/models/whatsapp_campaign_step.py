# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class WhatsAppCampaignStep(models.Model):
    _name = 'whatsapp.campaign.step'
    _description = 'WhatsApp Drip Campaign Step'
    _order = 'sequence'

    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign', required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Step Name', required=True)
    
    # Timing
    delay_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
    ], string='Delay Type', default='days')
    delay_unit = fields.Integer('Delay Unit', default=1)
    
    # Content
    template_id = fields.Many2one('whatsapp.template', string='Template')
    message_body = fields.Text('Message Body')
    
    # Conditions
    condition_type = fields.Selection([
        ('none', 'No Condition'),
        ('last_read', 'If Last Message Was Read'),
        ('last_not_read', 'If Last Message Was NOT Read'),
        ('last_delivered', 'If Last Message Was Delivered'),
        ('last_failed', 'If Last Message Failed'),
        ('replied', 'If Customer Replied'),
        ('not_replied', 'If Customer Did Not Reply'),
        ('clicked', 'If Customer Clicked Button/List'),
        ('no_reply', 'No Reply After Delay'),
    ], string='Condition', default='none')

    @api.constrains('delay_unit', 'template_id', 'message_body')
    def _check_step_configuration(self):
        for step in self:
            if step.delay_unit < 0:
                raise ValidationError("Drip step delay must be zero or greater.")
            if not step.template_id and not (step.message_body or '').strip():
                raise ValidationError(
                    f'Drip step "{step.name}" requires either a template or message body.'
                )
            if step.template_id:
                if step.template_id.status != 'approved':
                    raise ValidationError(f'Drip step "{step.name}" requires an approved template.')
                if (
                    step.campaign_id.account_id
                    and step.template_id.account_id
                    and step.template_id.account_id != step.campaign_id.account_id
                ):
                    raise ValidationError(f'Drip step "{step.name}" template must belong to the campaign account.')
                if step.template_id.header_type in ('image', 'video', 'document') and not (
                    step.template_id.header_media_url or step.template_id.header_media_file
                ):
                    raise ValidationError(
                        f'Drip step "{step.name}" template has a {step.template_id.header_type} header. '
                        "Set a default header media file or URL on the template before using it in a campaign."
                    )
