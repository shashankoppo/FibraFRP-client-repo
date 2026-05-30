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

    # Check inbound messages
    inbound = env['whatsapp.message'].search([('direction', '=', 'inbound')], limit=10, order='id desc')
    print(f"\n=== INBOUND MESSAGES (total count: {env['whatsapp.message'].search_count([('direction','=','inbound')])}) ===")
    for m in inbound:
        print(f"  ID={m.id} | body={repr(m.body[:60] if m.body else 'EMPTY')} | type={m.message_type} | chat={m.chat_id_ref.id if m.chat_id_ref else 'NONE'} | date={m.create_date}")

    # Check template messages
    templates_sent = env['whatsapp.message'].search([('message_type', '=', 'template')], limit=10, order='id desc')
    print(f"\n=== TEMPLATE MESSAGES (total: {env['whatsapp.message'].search_count([('message_type','=','template')])}) ===")
    for m in templates_sent:
        print(f"  ID={m.id} | body={repr(m.body[:80] if m.body else 'EMPTY')} | template_name={m.template_name} | template_id={m.template_id.id if m.template_id else 'NONE'}")

    # Check whatsapp.template records
    templates = env['whatsapp.template'].search([], limit=10)
    print(f"\n=== WHATSAPP TEMPLATES (total: {env['whatsapp.template'].search_count([])}) ===")
    for t in templates:
        print(f"  ID={t.id} | name={t.name} | body={repr(t.body[:60] if t.body else 'EMPTY')} | status={t.status}")

    # Check history_html for chat 15
    chats = env['whatsapp.chat'].search([], limit=5, order='id desc')
    print(f"\n=== RECENT CHATS ===")
    for c in chats:
        print(f"  ID={c.id} | phone={c.phone_number} | state={c.state} | msg_count={len(c.message_ids)} | last_body={repr(c.last_message_body[:60] if c.last_message_body else 'EMPTY')}")
        msg_sample = c.message_ids.sorted('create_date', reverse=True)[:3]
        for m in msg_sample:
            print(f"    -> msg ID={m.id} dir={m.direction} type={m.message_type} body={repr(m.body[:50] if m.body else 'EMPTY')}")
