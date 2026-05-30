from odoo import fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ELSXMarketingAI(models.Model):
    _name = 'elsx.marketing.ai'
    _description = 'ELSX Draft Marketing AI'

    name = fields.Char('Campaign Name', required=True)
    target_audience = fields.Char('Target Audience')
    generated_content = fields.Text('AI Draft Content')
    ai_job_id = fields.Many2one('elsx.ai.job', string='AI Job', readonly=True)
    platform = fields.Selection([
        ('email', 'Email'),
        ('linkedin', 'LinkedIn'),
        ('twitter', 'Twitter'),
        ('instagram', 'Instagram'),
    ], string='Platform', default='email')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generating', 'Generating'),
        ('approved', 'Approved'),
        ('posted', 'Posted'),
    ], default='draft')

    def action_generate_content(self):
        """Generate an auditable draft through the shared AI layer."""
        self.ensure_one()
        provider_model = self.env['elsx.ai.provider']
        if not provider_model._ai_enabled():
            raise UserError(_('Enable AI in Settings and test an AI provider before generating marketing drafts.'))

        self.state = 'generating'
        job = self.env['elsx.ai.job'].create_job(
            'whatsapp_campaign_default',
            'Marketing draft for %s' % self.display_name,
            origin=self,
            input_text='\n'.join([
                'Campaign: %s' % (self.name or ''),
                'Platform: %s' % (self.platform or ''),
                'Audience: %s' % (self.target_audience or ''),
                'Draft only. Do not post or send automatically.',
            ]),
        )
        job.action_run()
        self.write({
            'generated_content': job.response_text or job.response_json or '',
            'ai_job_id': job.id,
            'state': 'draft',
        })
        _logger.info("ELSX AI drafted content for %s via job %s", self.name, job.id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Marketing Draft Job'),
            'res_model': 'elsx.ai.job',
            'res_id': job.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_post_content(self):
        """Keep AI marketing draft-only until a real approved publishing flow exists."""
        raise UserError(_('Automatic posting is disabled. Review the AI draft and publish through the approved marketing channel manually.'))
