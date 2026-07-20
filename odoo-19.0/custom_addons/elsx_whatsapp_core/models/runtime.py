# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError


class WhatsAppRuntimeGuard(models.AbstractModel):
    _name = 'whatsapp.runtime.guard'
    _description = 'WhatsApp Runtime Guard'

    @api.model
    def is_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.runtime.enabled',
            default='True',
        ) == 'True'

    @api.model
    def assert_enabled(self):
        if not self.is_enabled():
            raise UserError(_(
                'WhatsApp sending and automation are paused. An administrator must resume the runtime in Settings.'
            ))
        return True
