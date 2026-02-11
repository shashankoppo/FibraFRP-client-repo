# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_menus(self, debug):
        """
        Override to hide Apps menu from all users.
        Only accessible via /action-39 secret URL.
        """
        menus = super(IrUiMenu, self).load_menus(debug)
        
        # Get the Apps menu ID
        try:
            apps_menu = self.env.ref('base.menu_apps', raise_if_not_found=False)
            management_menu = self.env.ref('base.menu_management', raise_if_not_found=False)
            
            if apps_menu and 'root' in menus:
                # Remove Apps menu from root
                if apps_menu.id in menus['root'].get('children', []):
                    menus['root']['children'].remove(apps_menu.id)
                
                # Remove from all_menu_ids
                if apps_menu.id in menus.get('all_menu_ids', []):
                    menus['all_menu_ids'].remove(apps_menu.id)
                
                # Remove the menu entry itself
                if str(apps_menu.id) in menus:
                    del menus[str(apps_menu.id)]
            
            if management_menu and 'root' in menus:
                # Remove Management menu from root
                if management_menu.id in menus['root'].get('children', []):
                    menus['root']['children'].remove(management_menu.id)
                
                # Remove from all_menu_ids
                if management_menu.id in menus.get('all_menu_ids', []):
                    menus['all_menu_ids'].remove(management_menu.id)
                
                # Remove the menu entry itself
                if str(management_menu.id) in menus:
                    del menus[str(management_menu.id)]
                    
            _logger.info('Apps menu hidden from menu tree')
            
        except Exception as e:
            _logger.warning('Failed to hide Apps menu: %s', e)
        
        return menus
