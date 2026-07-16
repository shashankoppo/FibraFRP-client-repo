# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _on_webclient_bootstrap(self):
        result = super()._on_webclient_bootstrap()
        self.env['ir.ui.menu'].sudo()._elsx_repair_startup_metadata()
        return result