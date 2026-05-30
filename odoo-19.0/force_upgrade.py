import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

# File logger
log_file = open('/opt/odoo/upgrade_output.txt', 'w', encoding='utf-8')
def log(msg):
    print(msg)
    log_file.write(str(msg) + '\n')
    log_file.flush()

log("Starting database transaction...")
registry = Registry('qwerty')
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    module = env['ir.module.module'].search([('name', '=', 'elsx_whatsapp_marketing')])
    log(f"Module state before upgrade: {module.state}")
    try:
        module.button_immediate_upgrade()
        cr.commit()
        log("Upgrade committed successfully!")
    except Exception as e:
        log(f"Exception during upgrade: {e}")
        import traceback
        traceback.print_exc(file=log_file)

log_file.close()
