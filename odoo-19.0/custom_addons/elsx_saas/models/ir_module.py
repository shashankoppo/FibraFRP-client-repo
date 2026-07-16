# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError

from ..utils import is_saas_system_enabled


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def action_request_saas_module(self):
        """Disabled SaaS app request entry point."""
        if not is_saas_system_enabled(self.env):
            raise UserError(_(
                'The SaaS system is deactivated. App requests and module installs are disabled to protect production client data.'
            ))

        self.ensure_one()
        tenant_user = self.env['elsx.saas.tenant'].search([
            ('user_id', '=', self.env.user.id),
        ], limit=1)

        if not tenant_user:
            raise UserError(_('You are not linked to any active SaaS Tenant.'))

        return {
            'name': _('Request Module'),
            'type': 'ir.actions.act_window',
            'res_model': 'elsx.saas.module.request',
            'view_mode': 'form',
            'context': {
                'default_tenant_id': tenant_user.id,
                'default_name': self.shortdesc or self.name,
                'default_module_name': self.name,
            },
        }

    @api.model
    def _elsx_saas_deactivate_runtime(self):
        """Make the SaaS layer passive without touching operational client data."""
        self.env['ir.config_parameter'].sudo().set_param('elsx_saas.enabled', '0')

        def ref(xmlid):
            return self.env.ref(xmlid, raise_if_not_found=False)

        base_user = ref('base.group_user')
        base_system = ref('base.group_system')
        base_apps_menu = ref('base.menu_management')
        saas_groups = [
            ref('elsx_saas.group_elsx_saas_app_user'),
            ref('elsx_saas.group_elsx_saas_user'),
            ref('elsx_saas.group_elsx_saas_admin'),
        ]
        for group in [group for group in saas_groups if group]:
            if base_user:
                base_user.write({'implied_ids': [(3, group.id)]})
            if base_system:
                base_system.write({'implied_ids': [(3, group.id)]})
            if base_apps_menu:
                base_apps_menu.write({'group_ids': [(3, group.id)]})

        root_menu = ref('elsx_saas.menu_elsx_saas_root')
        if root_menu:
            menus = self.env['ir.ui.menu'].with_context(active_test=False).search([('id', 'child_of', root_menu.id)])
            menus.write({'active': False})

        for xmlid in (
            'elsx_saas.view_module_kanban_saas_override',
            'elsx_saas.view_module_form_saas_override',
        ):
            view = ref(xmlid)
            if view:
                view.write({'active': False})

        for xmlid in (
            'elsx_saas.cron_detect_overdue_billing',
            'elsx_saas.cron_auto_generate_invoices',
        ):
            cron = ref(xmlid)
            if cron:
                cron.write({'active': False})

        return True
