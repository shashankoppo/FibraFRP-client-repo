import xmlrpc.client

url = 'http://localhost:8069'
db = 'qwerty'
username = 'admin'
password = 'admin'

common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
uid = common.authenticate(db, username, password, {})

models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))

try:
    res = models.execute_kw(db, uid, password, 'whatsapp.chat', 'read',
                            [[25], ['history_html']],
                            {'context': {'wa_history_limit': 100}})
    print(f"Result type: {type(res)}")
    if res:
        html = res[0].get('history_html', '')
        print(f"HTML length: {len(html) if html else 0}")
        if html:
            print("First 100 chars:", html[:100])
    else:
        print("Empty list returned")
except Exception as e:
    print(f"RPC Error: {e}")
