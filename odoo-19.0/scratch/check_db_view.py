import xmlrpc.client

url = 'https://fibera.elsxglobal.com'
db = 'qwerty'
username = 'shashankumar1927@gmail.com'
password = '12345678Op'

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
view = models.execute_kw(db, uid, password, 'ir.ui.view', 'search_read', [[['name', '=', 'whatsapp.chat.form']]], {'fields': ['arch_db'], 'limit': 1})

if view:
    print("VIEW_FOUND: True")
    print("ARCH:", view[0]['arch_db'][:1000])
else:
    print("VIEW_FOUND: False")
