# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ElsxModuleSafetyWizard(models.TransientModel):
    _name = 'elsx.module.safety.wizard'
    _description = 'ELSx Safe Module Change'

    operation = fields.Selection([
        ('install', 'Install'),
        ('upgrade', 'Upgrade'),
        ('uninstall', 'Uninstall'),
    ], default='upgrade', required=True)
    module_ids = fields.Many2many('ir.module.module', string='Modules')
    backup_confirmed = fields.Boolean(string='Encrypted backup has been created and verified')
    impact_summary = fields.Text(compute='_compute_impact_summary')

    @api.depends('module_ids', 'operation')
    def _compute_impact_summary(self):
        protected_names = self.env['ir.module.module']._elsx_protected_module_names()
        for wizard in self:
            modules = wizard.module_ids
            downstream = self.env['ir.module.module']
            if wizard.operation == 'uninstall' and modules:
                downstream = modules.downstream_dependencies()
            protected = (modules | downstream).filtered(lambda module: module.name in protected_names)
            lines = [
                _('Operation: %s') % dict(self._fields['operation'].selection).get(wizard.operation, wizard.operation),
                _('Selected modules: %s') % (', '.join(modules.mapped('name')) or _('None')),
            ]
            if downstream:
                lines.append(_('Downstream modules that may also be affected: %s') % ', '.join(sorted(downstream.mapped('name'))))
            if protected:
                lines.append(_('Protected modules involved: %s') % ', '.join(sorted(protected.mapped('name'))))
            else:
                lines.append(_('No protected module impact detected.'))
            lines.append(_('Use deploy/safe_production_update.sh for production upgrades. Never use docker compose down -v.'))
            wizard.impact_summary = '\n'.join(lines)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'ir.module.module' and self.env.context.get('active_ids'):
            vals['module_ids'] = [(6, 0, self.env.context['active_ids'])]
        return vals

    def action_confirm_plan(self):
        self.ensure_one()
        if not self.backup_confirmed:
            raise UserError(_('Confirm a verified encrypted backup before changing production modules.'))
        if self.operation == 'uninstall':
            protected = self.module_ids._elsx_protected_uninstall_candidates()
            if protected:
                raise UserError(_(
                    'This uninstall would affect protected modules: %s'
                ) % ', '.join(sorted(protected.mapped('name'))))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Safe Module Change'),
                'message': _('Preflight completed. Use the controlled deployment script for production changes.'),
                'type': 'success',
            },
        }
