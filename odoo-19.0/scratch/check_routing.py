import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

# Let's inspect routing
from odoo.http import routing_map

print("Routing map rules count:", len(routing_map._rules) if routing_map else "None")
for rule in routing_map._rules:
    if 'whatsapp' in rule.rule:
        print(f"Rule: {rule.rule} | Endpoint: {rule.endpoint} | Methods: {rule.methods}")
