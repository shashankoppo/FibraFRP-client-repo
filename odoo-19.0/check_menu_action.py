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
    # search ir_act_client
    print("CLIENT ACTIONS:")
    actions = env['ir.actions.client'].search([('tag', 'like', 'dashboard')])
    for act in actions:
        print(f"ID: {act.id}, Name: {act.name}, Tag: {act.tag}")
        
    print("\nXML DATA ENTRIES containing dashboard:")
    data = env['ir.model.data'].search([('name', 'like', 'dashboard'), ('module', '=', 'elsx_whatsapp_marketing')])
    for d in data:
        print(f"Module: {d.module}, Name: {d.name}, Model: {d.model}, ResID: {d.res_id}")
