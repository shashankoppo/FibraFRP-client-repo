# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    @api.model
    def button_immediate_install(self):
        """
        Override to auto-install dependencies
        """
        for module in self:
            if module.state != 'installed':
                # Recursive install is handled by Odoo naturally, 
                # but we ensure they are marked for installation.
                # Here we just log and call super.
                _logger.info('Installing module %s', module.name)
        
        return super(IrModuleModule, self).button_immediate_install()

    @api.model
    def update_list(self):
        """
        Override to auto-upgrade modules if needed
        """
        res = super(IrModuleModule, self).update_list()
        
        # Auto-upgrade modules that are in 'to upgrade' state
        to_upgrade = self.search([('state', '=', 'to upgrade')])
        if to_upgrade:
            _logger.info('Auto-upgrading modules: %s', to_upgrade.mapped('name'))
            to_upgrade.button_immediate_upgrade()
            
        return res
