# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class WhatsAppUninstallReadinessWizard(models.TransientModel):
    _name = 'whatsapp.uninstall.readiness.wizard'
    _description = 'WhatsApp Uninstall Readiness'

    backup_reference = fields.Char(
        required=True,
        help='Exact encrypted backup reference registered by the controlled production update.',
    )
    backup_confirmed = fields.Boolean(
        string='I verified the encrypted backup and restore instructions',
    )
    expected_confirmation = fields.Char(
        readonly=True,
        default=lambda self: self.env[
            'elsx.whatsapp.uninstall.readiness'
        ].expected_confirmation(),
    )
    typed_confirmation = fields.Char()
    readiness_id = fields.Many2one(
        'elsx.whatsapp.uninstall.readiness',
        readonly=True,
    )
    state = fields.Selection(related='readiness_id.state', readonly=True)
    blocker_count = fields.Integer(related='readiness_id.blocker_count', readonly=True)
    report_text = fields.Text(related='readiness_id.report_text', readonly=True)
    authorization_token = fields.Char(readonly=True)
    authorization_expires_at = fields.Datetime(
        related='readiness_id.authorization_expires_at',
        readonly=True,
    )

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Uninstall Readiness'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_run_checks(self):
        self.ensure_one()
        readiness = self.env['elsx.whatsapp.uninstall.readiness'].create_readiness(
            self.backup_reference,
            self.backup_confirmed,
            self.typed_confirmation or '',
        )
        self.write({
            'readiness_id': readiness.id,
            'authorization_token': False,
        })
        return self._reopen()

    def action_authorize(self):
        self.ensure_one()
        if not self.readiness_id:
            raise UserError(_('Run the readiness checks first.'))
        token = self.readiness_id.issue_authorization()
        self.authorization_token = token
        return self._reopen()

    def action_open_uninstall_confirmation(self):
        self.ensure_one()
        if not self.authorization_token:
            raise UserError(_('Create a valid 15-minute authorization first.'))
        self.env[
            'elsx.whatsapp.uninstall.readiness'
        ].validate_authorization_token(self.authorization_token)
        module = self.env['ir.module.module'].sudo().search([
            ('name', '=', 'elsx_whatsapp_marketing'),
            ('state', 'in', ('installed', 'to upgrade')),
        ], limit=1)
        if not module:
            raise UserError(_('The WhatsApp application shell is not installed.'))
        action = module.with_context(
            elsx_whatsapp_uninstall_token=self.authorization_token,
        ).button_uninstall_wizard()
        action['context'] = {
            **(action.get('context') or {}),
            'default_module_ids': module.ids,
            'elsx_whatsapp_uninstall_token': self.authorization_token,
        }
        return action
