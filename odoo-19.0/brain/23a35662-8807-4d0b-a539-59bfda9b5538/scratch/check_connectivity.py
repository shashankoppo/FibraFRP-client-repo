
from odoo import api, SUPERUSER_ID

def run(env):
    logs = env['whatsapp.webhook.log'].search([], limit=10)
    print(f"Total Logs: {env['whatsapp.webhook.log'].search_count([])}")
    for log in logs:
        print(f"Log ID: {log.id}, Event: {log.event_type}, Status: {log.status}, Error: {log.error_detail or ''}")
    
    messages = env['whatsapp.message'].search([('message_type', '=', 'template')], limit=5)
    print(f"\nRecent Template Messages:")
    for msg in messages:
        print(f"ID: {msg.id}, Body: {msg.body}, Status: {msg.status}")
