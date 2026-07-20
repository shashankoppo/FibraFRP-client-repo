# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


STEPS = ['audience', 'content', 'personalization', 'schedule', 'review']


class WhatsAppCampaignWizard(models.TransientModel):
    _name = 'whatsapp.campaign.wizard'
    _description = 'Guided WhatsApp Campaign'

    step = fields.Selection([
        ('audience', '1. Audience'),
        ('content', '2. Content'),
        ('personalization', '3. Personalization'),
        ('schedule', '4. Schedule'),
        ('review', '5. Review'),
    ], default='audience', required=True, readonly=True)
    campaign_id = fields.Many2one('whatsapp.campaign', readonly=True)
    name = fields.Char(required=True)
    account_id = fields.Many2one('whatsapp.account', required=True)
    campaign_type = fields.Selection([
        ('broadcast', 'Broadcast'),
        ('drip', 'Drip Campaign'),
    ], default='broadcast', required=True)
    target_type = fields.Selection([
        ('all', 'All Contacts'),
        ('segment', 'Segment'),
        ('manual', 'Selected Contacts'),
        ('crm_stage', 'CRM Stage'),
        ('tags', 'Contact Tags'),
        ('csv', 'CSV Upload'),
    ], default='manual', required=True)
    segment_id = fields.Many2one('whatsapp.contact.segment')
    domain_filter = fields.Char()
    crm_stage_id = fields.Many2one('crm.stage')
    tag_ids = fields.Many2many('res.partner.category')
    partner_ids = fields.Many2many('res.partner')
    csv_file = fields.Binary()
    csv_filename = fields.Char()
    template_id = fields.Many2one(
        'whatsapp.template',
        domain=[('status', '=', 'approved')],
    )
    message_body = fields.Text()
    preview_partner_id = fields.Many2one('res.partner')
    preview_payload_json = fields.Text(
        compute='_compute_preview_payload_json',
        readonly=True,
    )
    schedule_type = fields.Selection([
        ('immediate', 'Send Immediately'),
        ('scheduled', 'Schedule'),
    ], default='immediate', required=True)
    schedule_date = fields.Datetime()
    review_text = fields.Text(readonly=True)
    review_json = fields.Text(readonly=True)
    blocker_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    eligible_count = fields.Integer(readonly=True)
    can_launch = fields.Boolean(readonly=True)

    @api.depends(
        'template_id',
        'template_id.preview_payload_json',
        'message_body',
        'preview_partner_id',
    )
    def _compute_preview_payload_json(self):
        for wizard in self:
            if wizard.template_id:
                payload = wizard.template_id.get_preview_payload(
                    partner_id=wizard.preview_partner_id.id,
                )
            else:
                body = wizard.message_body or ''
                if wizard.preview_partner_id:
                    body = body.replace(
                        '{{name}}',
                        wizard.preview_partner_id.name or '',
                    )
                    body = body.replace(
                        '{{company}}',
                        wizard.preview_partner_id.company_name or '',
                    )
                payload = {
                    'version': 1,
                    'header': {'type': 'none', 'text': '', 'media_url': False},
                    'body': body,
                    'footer': '',
                    'buttons': [],
                    'carousel': [],
                    'variables': [],
                    'warnings': [],
                }
            wizard.preview_payload_json = json.dumps(payload, sort_keys=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if self.env.context.get('active_model') == 'whatsapp.campaign' and active_id:
            campaign = self.env['whatsapp.campaign'].browse(active_id).exists()
            if campaign:
                values.update({
                    'campaign_id': campaign.id,
                    'name': campaign.name,
                    'account_id': campaign.account_id.id,
                    'campaign_type': campaign.campaign_type,
                    'target_type': campaign.target_type,
                    'segment_id': campaign.segment_id.id,
                    'domain_filter': campaign.domain_filter,
                    'crm_stage_id': campaign.crm_stage_id.id,
                    'tag_ids': [(6, 0, campaign.tag_ids.ids)],
                    'partner_ids': [(6, 0, campaign.partner_ids.ids)],
                    'csv_file': campaign.csv_file,
                    'csv_filename': campaign.csv_filename,
                    'template_id': campaign.template_id.id,
                    'message_body': campaign.message_body,
                    'preview_partner_id': campaign.preview_partner_id.id,
                    'schedule_type': campaign.schedule_type,
                    'schedule_date': campaign.schedule_date,
                })
        return values

    def _campaign_values(self):
        self.ensure_one()
        return {
            'name': self.name,
            'account_id': self.account_id.id,
            'campaign_type': self.campaign_type,
            'target_type': self.target_type,
            'segment_id': self.segment_id.id,
            'domain_filter': self.domain_filter,
            'crm_stage_id': self.crm_stage_id.id,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
            'partner_ids': [(6, 0, self.partner_ids.ids)],
            'csv_file': self.csv_file,
            'csv_filename': self.csv_filename,
            'template_id': self.template_id.id,
            'message_body': self.message_body,
            'preview_partner_id': self.preview_partner_id.id,
            'schedule_type': self.schedule_type,
            'schedule_date': self.schedule_date,
        }

    def _sync_campaign(self):
        self.ensure_one()
        values = self._campaign_values()
        if self.campaign_id:
            if self.campaign_id.state != 'draft':
                raise UserError(_('Only draft campaigns can be changed by the guided workflow.'))
            self.campaign_id.write(values)
        else:
            self.campaign_id = self.env['whatsapp.campaign'].create(values)
        return self.campaign_id

    def _validate_step(self):
        self.ensure_one()
        if self.step == 'audience':
            if self.target_type == 'manual' and not self.partner_ids:
                raise ValidationError(_('Select at least one contact.'))
            if self.target_type == 'segment' and not (
                self.segment_id or (self.domain_filter or '').strip()
            ):
                raise ValidationError(_('Select a segment or enter a valid domain.'))
            if self.target_type == 'tags' and not self.tag_ids:
                raise ValidationError(_('Select at least one contact tag.'))
            if self.target_type == 'csv' and not self.csv_file:
                raise ValidationError(_('Upload an audience CSV.'))
        elif self.step == 'content':
            if not self.template_id and not (self.message_body or '').strip():
                raise ValidationError(_('Select an approved template or enter message content.'))
        elif self.step == 'schedule':
            if self.schedule_type == 'scheduled' and not self.schedule_date:
                raise ValidationError(_('Select a scheduled date and time.'))

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Guided WhatsApp Campaign'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_next(self):
        self.ensure_one()
        self._validate_step()
        self._sync_campaign()
        index = STEPS.index(self.step)
        self.step = STEPS[min(index + 1, len(STEPS) - 1)]
        if self.step == 'review':
            self._refresh_review()
        return self._reopen()

    def action_previous(self):
        self.ensure_one()
        index = STEPS.index(self.step)
        self.step = STEPS[max(index - 1, 0)]
        return self._reopen()

    def _refresh_review(self):
        self.ensure_one()
        campaign = self._sync_campaign()
        review = campaign.get_launch_review()
        counts = review['counts']
        lines = [
            _('Source recipients: %s') % counts['source'],
            _('Eligible after deduplication: %s') % counts['eligible'],
            _('Opt-in exclusions: %s') % counts['opt_in_excluded'],
            _('Consent exclusions: %s') % counts['consent_excluded'],
            _('Invalid numbers: %s') % counts['invalid_numbers'],
        ]
        lines.extend(
            '[WARNING] %s' % item['message']
            for item in review['warnings']
        )
        lines.extend(
            '[BLOCKED] %s' % item['message']
            for item in review['blockers']
        )
        self.write({
            'review_json': json.dumps(review, sort_keys=True),
            'review_text': '\n'.join(lines),
            'blocker_count': len(review['blockers']),
            'warning_count': len(review['warnings']),
            'eligible_count': counts['eligible'],
            'can_launch': review['can_launch'],
        })
        return review

    def action_refresh_review(self):
        self.ensure_one()
        self._refresh_review()
        return self._reopen()

    def action_test_send(self):
        self.ensure_one()
        if not self.template_id:
            raise UserError(_('Select an approved template before opening Test Send.'))
        partner = self.preview_partner_id or self.partner_ids[:1]
        action = self.env.ref(
            'elsx_whatsapp_marketing.action_send_whatsapp_wizard'
        ).read()[0]
        action['context'] = {
            'default_account_id': self.account_id.id,
            'default_template_id': self.template_id.id,
            'default_partner_ids': [(6, 0, partner.ids)],
        }
        return action

    def action_launch(self):
        self.ensure_one()
        review = self._refresh_review()
        if not review['can_launch']:
            raise UserError(_(
                'Campaign launch is blocked. Resolve every blocking review item first.'
            ))
        return self.campaign_id.action_send_campaign()
