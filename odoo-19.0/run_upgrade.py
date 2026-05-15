import odoo
from odoo import api, SUPERUSER_ID

def upgrade_module():
    db_name = 'elsx_dev'
    odoo.tools.config.parse_config(['-c', 'odoo.local.conf', '-d', db_name])
    
    from odoo.orm.registry import Registry
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        module = env['ir.module.module'].search([('name', '=', 'elsx_whatsapp_marketing')])
        if module:
            print(f"Upgrading module {module.name}...")
            module.button_immediate_upgrade()
            cr.commit()
            print("Upgrade complete.")
        else:
            print("Module not found.")

if __name__ == '__main__':
    upgrade_module()
