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
    chat = env['whatsapp.chat'].browse(15)
    print("CHAT:", chat.phone_number, "STATE:", chat.state)
    print("MESSAGES COUNT:", len(chat.message_ids))
    print("INBOUND COUNT:", len(chat.message_ids.filtered(lambda m: m.direction == 'inbound')))
    print("OUTBOUND COUNT:", len(chat.message_ids.filtered(lambda m: m.direction == 'outbound')))
    
    # Check history_html
    history = chat.history_html
    print("HISTORY LENGTH:", len(history or ''))
    
    # Check if 'inbound' is in history_html
    import re
    inbound_bubbles = re.findall(r'o_whatsapp_msg_inbound', history or '')
    print("INBOUND BUBBLES IN HTML:", len(inbound_bubbles))
    
    # Print some snippets
    if history:
        print("FIRST 500 CHARS OF HISTORY:")
        print(history[:500])
        print("LAST 500 CHARS OF HISTORY:")
        print(history[-500:])
