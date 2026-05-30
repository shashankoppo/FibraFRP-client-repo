# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_menus(self, debug):
        """
        Compatibility hook from the old access-helper addon.

        The system no longer hides menus here. Standard Odoo access groups
        decide what each user can see.
        """
        return super(IrUiMenu, self).load_menus(debug)
