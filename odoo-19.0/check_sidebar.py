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
    data = env['whatsapp.chat'].get_sidebar_chats()
    print(f"Total chats in sidebar: {len(data)}")
    for c in data:
        chat_rec = env['whatsapp.chat'].browse(c.get('id'))
        assigned_to = chat_rec.assigned_user_id.name if chat_rec.assigned_user_id else 'Unassigned'
        print(f"ID: {chat_rec.id}, Name: {chat_rec.display_name}, Assigned: {assigned_to}")
