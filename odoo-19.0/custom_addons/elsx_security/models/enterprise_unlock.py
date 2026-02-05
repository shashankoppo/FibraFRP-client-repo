from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)

class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def button_immediate_install(self):
        # Ensure all ELSX modules are allowed to be installed
        return super(IrModuleModule, self).button_immediate_install()

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Simulated Enterprise Contract
    elsx_enterprise_active = fields.Boolean('ELSX Enterprise Active', default=True)

class PublisherWarrantyContract(models.AbstractModel):
    _inherit = 'publisher_warranty.contract'

    def update_notification(self, cron_mode=False):
        # Suppress Odoo Enterprise notification checks
        _logger.info("ELSX: Suppressing Odoo Enterprise contract checks.")
        return True
