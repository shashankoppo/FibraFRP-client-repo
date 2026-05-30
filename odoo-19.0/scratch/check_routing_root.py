import sys
import threading
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

db_name = 'qwerty'
threading.current_thread().dbname = db_name
registry = Registry(db_name)
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    routing_map = env['ir.http'].routing_map()
    print("Routing map rules count:", len(routing_map._rules) if routing_map else "None")
    count = 0
    for r in routing_map._rules:
        if 'whatsapp' in r.rule:
            print(f"  Rule: {r.rule} | Endpoint: {r.endpoint} | Methods: {r.methods}")
            count += 1
    print(f"Total rules matching whatsapp: {count}")
