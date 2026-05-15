import odoo
from odoo import api, SUPERUSER_ID

def check_chat():
    db_name = 'qwerty'
    odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', db_name])
    
    from odoo.orm.registry import Registry
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        chat = env['whatsapp.chat'].search([('display_name', 'ilike', 'Public user')], limit=1)
        if chat:
            print(f"Chat ID: {chat.id}")
            print(f"History HTML: {chat.history_html}")
        else:
            print("Chat not found.")

if __name__ == '__main__':
    check_chat()
