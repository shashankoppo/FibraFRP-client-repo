from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    elsx_ai_score = fields.Float('AI Lead Score', help='AI calculated lead probability (0-100)', default=0.0)
    elsx_sentiment = fields.Selection([
        ('positive', 'Positive'),
        ('neutral', 'Neutral'),
        ('negative', 'Negative')
    ], string='AI Sentiment Analysis', readonly=True)
    elsx_ai_next_step = fields.Text('AI Suggested Next Step', readonly=True)

    def action_generate_ai_reply(self):
        """Create an auditable AI draft job for the lead."""
        self.ensure_one()
        if 'elsx.ai.job' in self.env.registry.models:
            job = self.env['elsx.ai.job'].create_job(
                'crm_reply',
                'CRM reply draft for %s' % self.display_name,
                origin=self,
                input_text='\n'.join([
                    'Lead: %s' % (self.name or ''),
                    'Customer: %s' % (self.partner_id.display_name or self.contact_name or ''),
                    'Email: %s' % (self.email_from or ''),
                    'Description: %s' % (self.description or ''),
                ]),
            )
            job.action_run()
            if job.response_text:
                self.write({'elsx_ai_next_step': job.response_text})
            return {
                'type': 'ir.actions.act_window',
                'name': 'AI CRM Draft Job',
                'res_model': 'elsx.ai.job',
                'res_id': job.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'AI Not Installed',
                'message': 'Install the ELSX AI service layer before generating CRM AI drafts.',
                'type': 'warning',
            }
        }
