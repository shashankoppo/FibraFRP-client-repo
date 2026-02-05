# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class SecretAccessController(http.Controller):
    """
    Controller to handle secret URL access to Apps module
    Only /action-39 should provide access to the Apps menu
    """

    @http.route('/action-39', type='http', auth='user', website=False)
    def secret_apps_access(self, **kwargs):
        """
        Secret endpoint to access Apps module
        """
        _logger.info('Secret access to Apps module via /action-39 by user: %s', request.env.user.login)
        
        # Find the Apps action ID dynamically
        try:
            action = request.env.ref('base.open_module_tree')
            return request.redirect('/web#action=%s' % action.id)
        except Exception:
            # Fallback to 39 if ref fails
            return request.redirect('/web#action=39')
