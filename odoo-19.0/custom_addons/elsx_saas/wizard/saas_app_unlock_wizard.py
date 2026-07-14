# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..utils import verify_saas_app_unlock_password


class ELSXSaasAppUnlockWizard(models.TransientModel):
    _name = 'elsx.saas.app.unlock.wizard'
    _description = 'SaaS App Unlock Password'

    module_id = fields.Many2one('ir.module.module', string='App Module', readonly=True)
    module_request_id = fields.Many2one('elsx.saas.module.request', string='Tenant Module Request', readonly=True)
    password = fields.Char('Password', required=True)
    target_database = fields.Char(compute='_compute_target_info')
    module_name = fields.Char(compute='_compute_target_info')

    @api.depends('module_id', 'module_request_id')
    def _compute_target_info(self):
        for wizard in self:
            if wizard.module_request_id:
                wizard.module_name = wizard.module_request_id.module_name or wizard.module_request_id.name
                wizard.target_database = wizard.module_request_id.tenant_id.db_name
            elif wizard.module_id:
                wizard.module_name = wizard.module_id.shortdesc or wizard.module_id.name
                wizard.target_database = wizard.env.cr.dbname
            else:
                wizard.module_name = False
                wizard.target_database = False

    def action_confirm_unlock(self):
        self.ensure_one()
        if not verify_saas_app_unlock_password(self.env, self.password):
            raise UserError(_('Incorrect SaaS app unlock password.'))

        if self.module_request_id:
            return self.module_request_id.sudo()._install_on_tenant()

        if self.module_id:
            return self.module_id.sudo()._saas_install_or_upgrade()

        raise UserError(_('No app module was selected for unlock.'))
