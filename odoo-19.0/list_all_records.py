import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

registry = Registry('qwerty')
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    data = env['ir.model.data'].search([('name', 'like', 'whatsapp_dashboard'), ('module', '=', 'elsx_whatsapp_marketing')])
    print(f"Total dashboard XML records: {len(data)}")
    for d in data:
        print(f"Model: {d.model:<30} Name: {d.name:<50} ResID: {d.res_id}")
