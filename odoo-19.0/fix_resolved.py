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
    chats = env['whatsapp.chat'].search([('state', '=', 'resolved'), ('is_archived', '=', True)])
    print(f"Found {len(chats)} archived resolved chats. Unarchiving them...")
    chats.write({'is_archived': False})
    cr.commit()
    print("Done!")
