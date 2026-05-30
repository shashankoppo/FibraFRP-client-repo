# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def button_immediate_install(self):
        """
        Compatibility hook only. Odoo handles dependency installation.
        """
        return super(IrModuleModule, self).button_immediate_install()

    def update_list(self):
        """
        Compatibility hook only. Never auto-upgrade modules from this addon.
        """
        return super(IrModuleModule, self).update_list()
