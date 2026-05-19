import sys
chat_id = 25
chat = env['whatsapp.chat'].browse(chat_id)
print(f"Chat: {chat.display_name}")
print(f"Message Count: {len(chat.message_ids)}")
html = chat.history_html
print(f"HTML Length: {len(html) if html else 'None'}")
