from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

def clear_assets():
    registry = Registry('qwerty')
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        # Clear all web assets to force rebuild
        attachments = env['ir.attachment'].search([('url', 'like', '/web/assets/%')])
        count = len(attachments)
        attachments.unlink()
        print(f"Cleared {count} asset bundles. Cache busted.")

if __name__ == '__main__':
    clear_assets()
