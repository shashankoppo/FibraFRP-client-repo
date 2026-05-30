import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

db_name = 'qwerty'
registry = Registry(db_name)
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    total = env['whatsapp.webhook.log'].sudo().search_count([])
    print(f"Total webhook logs: {total}")
    logs = env['whatsapp.webhook.log'].sudo().search([], order='id desc', limit=20)
    for log in logs:
        print(f"ID: {log.id} | Event: {log.event_type} | Status: {log.status} | Error: {log.error_detail or 'None'} | Created: {log.create_date}")
        if log.error_detail or log.status == 'error':
            print(f"  Raw payload: {log.raw_payload}")
