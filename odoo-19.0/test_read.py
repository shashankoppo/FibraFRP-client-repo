import sys
chat_id = 25
fields = [
    'display_name', 'phone_number', 'history_html', 'unread_count',
    'session_open', 'sla_status', 'sla_timer_minutes',
    'partner_id', 'whatsapp_profile_name', 'display_name_initial',
    'sale_order_count', 'invoice_count', 'lead_id'
]
kwargs = {'context': {'wa_history_limit': 100}}
# Equivalent to ORM call
res = env['whatsapp.chat'].browse([chat_id]).read(fields, **kwargs)
print(f"Read result: {res}")
print(f"history_html keys: {res[0].keys() if res else 'None'}")
