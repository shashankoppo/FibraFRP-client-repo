# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError


WHATSAPP_SHELL_MODULE = 'elsx_whatsapp_marketing'
ACTIVE_MODULE_STATES = frozenset(('installed', 'to upgrade'))


class WhatsAppRuntimeGuard(models.AbstractModel):
    _name = 'whatsapp.runtime.guard'
    _description = 'WhatsApp Runtime Guard'

    @api.model
    def is_enabled(self):
        shell = self.env['ir.module.module']._get(WHATSAPP_SHELL_MODULE)
        shell_installed = bool(
            shell and shell.state in ACTIVE_MODULE_STATES
        )
        runtime_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.runtime.enabled',
            default='True',
        ) == 'True'
        return shell_installed and runtime_enabled

    @api.model
    def assert_enabled(self):
        if not self.is_enabled():
            raise UserError(_(
                'WhatsApp sending and automation are paused. An administrator must resume the runtime in Settings.'
            ))
        return True
