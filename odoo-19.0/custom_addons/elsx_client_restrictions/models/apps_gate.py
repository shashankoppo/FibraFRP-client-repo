from odoo import api, models, _
from odoo.exceptions import AccessError
from odoo.http import request

from ..apps_gate import require_unlocked


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _elsx_require_apps_unlocked(self):
        require_unlocked()

    @api.model
    def get_views(self, views, options=None):
        require_unlocked()
        return super().get_views(views, options=options)

    @api.model
    def web_search_read(self, *args, **kwargs):
        require_unlocked()
        return super().web_search_read(*args, **kwargs)

    def web_read(self, specification):
        require_unlocked()
        return super().web_read(specification)

    @api.model_create_multi
    def create(self, vals_list):
        require_unlocked()
        return super().create(vals_list)

    def write(self, vals):
        require_unlocked()
        if request and vals.get("state") in ("uninstalled", "to remove") and any(
                module.name == "elsx_client_restrictions" for module in self):
            raise AccessError(_("The Apps access guard cannot be removed through the application."))
        return super().write(vals)

    def unlink(self):
        require_unlocked()
        if request and any(module.name == "elsx_client_restrictions" for module in self):
            raise AccessError(_("The Apps access guard cannot be removed through the application."))
        return super().unlink()

    def button_immediate_install(self):
        require_unlocked()
        return super().button_immediate_install()

    def button_immediate_upgrade(self):
        require_unlocked()
        return super().button_immediate_upgrade()

    def button_immediate_uninstall(self):
        require_unlocked()
        return super().button_immediate_uninstall()

    @api.model
    def update_list(self):
        require_unlocked()
        return super().update_list()
