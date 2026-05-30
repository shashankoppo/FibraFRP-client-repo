import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api, SUPERUSER_ID
import logging

def test_download():
    db_name = 'qwerty'
    odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', db_name])
    
    # Configure logging to console
    logging.basicConfig(level=logging.INFO)
    
    from odoo.modules.registry import Registry
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        msg = env['whatsapp.message'].browse(1130)
        print(f"Message 1130 details:")
        print(f"  media_url: {msg.media_url}")
        print(f"  account: {msg.account_id.name} (id={msg.account_id.id})")
        print(f"  access_token: {'***' if msg.account_id.access_token else 'None'}")
        print(f"  phone_number_id: {msg.account_id.phone_number_id}")
        print(f"  api_version: {msg.account_id.api_version}")
        
        print("\nAttempting download_media_from_meta()...")
        res = msg.download_media_from_meta()
        print(f"Result: {res}")
        print(f"has_media: {bool(msg.media_file)} (len: {len(msg.media_file) if msg.media_file else 0})")
        cr.commit()

if __name__ == '__main__':
    test_download()
