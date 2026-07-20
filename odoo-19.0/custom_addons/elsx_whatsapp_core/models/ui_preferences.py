# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    whatsapp_workspace_role = fields.Selection([
        ('automatic', 'Automatic from Access Rights'),
        ('agent', 'Agent'),
        ('marketer', 'Marketer'),
        ('manager', 'Manager'),
    ], string='WhatsApp Start Workspace', default='automatic', required=True)
    whatsapp_ui_version_override = fields.Selection([
        ('inherit', 'Use Database Default'),
        ('legacy', 'Legacy'),
        ('v2', 'V2'),
    ], string='WhatsApp Interface', default='inherit', required=True)

    def get_whatsapp_ui_version(self):
        self.ensure_one()
        if self.whatsapp_ui_version_override != 'inherit':
            return self.whatsapp_ui_version_override
        return self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.ui.version',
            default='legacy',
        )

    def get_whatsapp_workspace_role(self):
        self.ensure_one()
        if self.whatsapp_workspace_role != 'automatic':
            return self.whatsapp_workspace_role
        whatsapp_manager = False
        if self.env.ref(
            'elsx_whatsapp_marketing.group_whatsapp_manager',
            raise_if_not_found=False,
        ):
            whatsapp_manager = self.has_group(
                'elsx_whatsapp_marketing.group_whatsapp_manager'
            )
        if self.has_group('base.group_system') or whatsapp_manager:
            return 'manager'
        return 'agent'
