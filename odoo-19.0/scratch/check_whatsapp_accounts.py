import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

db_name = 'qwerty'
registry = Registry(db_name)
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    accounts = env['whatsapp.account'].sudo().search([])
    print(f"Total WhatsApp accounts: {len(accounts)}")
    for acc in accounts:
        print(f"ID: {acc.id}")
        print(f"Name: {acc.name}")
        print(f"Active: {acc.active}")
        print(f"Status: {acc.status}")
        print(f"Phone Number ID: {acc.phone_number_id}")
        print(f"Business Account ID: {acc.business_account_id}")
        print(f"Skip Webhook HMAC: {acc.skip_webhook_hmac}")
        print(f"App Secret (first 4 chars): {acc.app_secret[:4] if acc.app_secret else 'None'}")
        print(f"Webhook URL (from settings/calculated): {acc.webhook_url if hasattr(acc, 'webhook_url') else 'N/A'}")
        print("-" * 40)
