# -*- coding: utf-8 -*-
import xmlrpc.client

def populate_showcase_data(url, db, username, password):
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    print(f"Authenticated as {username} (UID: {uid})")

    # 1. Create a WhatsApp Account if none exists
    account_id = models.execute_kw(db, uid, password, 'whatsapp.account', 'search', [[('name', '=', 'DoubleTick Demo Account')]])
    if not account_id:
        account_id = [models.execute_kw(db, uid, password, 'whatsapp.account', 'create', [{
            'name': 'DoubleTick Demo Account',
            'phone_number': '+1234567890',
            'phone_number_id': '12345',
            'business_account_id': '67890',
            'access_token': 'demo_token',
            'status': 'connected',
            'ai_enabled': True,
            'ai_context': 'We sell premium industrial equipment. Help customers with orders and delivery tracking.',
        }])]
    
    # 2. Create some Contacts
    contacts_data = [
        {'name': 'John Doe', 'mobile': '+1999888777'},
        {'name': 'Jane Smith', 'mobile': '+1555444333'},
    ]
    for contact in contacts_data:
        exists = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('mobile', '=', contact['mobile'])]])
        if not exists:
            models.execute_kw(db, uid, password, 'res.partner', 'create', [contact])

    # 3. Create a Team Inbox Chat
    partner_id = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('name', '=', 'John Doe')]], {'limit': 1})
    chat_id = models.execute_kw(db, uid, password, 'whatsapp.chat', 'create', [{
        'account_id': account_id[0],
        'partner_id': partner_id[0],
        'phone_number': '+1999888777',
    }])

    # 4. Create dummy messages for the chat
    messages = [
        {'body': 'Hi, I would like to inquire about my order.', 'direction': 'inbound', 'chat_id_ref': chat_id},
        {'body': 'Hello John! I can help with that. What is your Order ID?', 'direction': 'outbound', 'chat_id_ref': chat_id},
        {'body': 'It is SO123.', 'direction': 'inbound', 'chat_id_ref': chat_id},
        {'body': 'Checking now... One moment.', 'direction': 'outbound', 'chat_id_ref': chat_id},
    ]
    for msg in messages:
        msg.update({'account_id': account_id[0], 'phone_number': '+1999888777', 'status': 'read'})
        models.execute_kw(db, uid, password, 'whatsapp.message', 'create', [msg])

    print("Showcase data populated successfully!")

if __name__ == "__main__":
    # Update these with actual credentials if different
    URL = 'http://localhost:8069'
    DB = 'odoo' # Adjust if needed
    USER = 'admin'
    PASS = 'admin'
    
    try:
        populate_showcase_data(URL, DB, USER, PASS)
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure Odoo is running at http://localhost:8069")
