import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo.service import db as db_service
print("List of databases:", db_service.list_dbs())
