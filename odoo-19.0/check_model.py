import odoo
import sys

def check():
    config = odoo.tools.config
    config.parse_config(['-c', 'odoo.conf', '-d', 'elsx_dev'])
    registry = odoo.registry(config['db_name'])
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        model = env['ir.model'].search([('model', '=', 'res.partner.title')])
        print(f"Model ID: {model.id if model else 'None'}")
        if model:
            print(f"Model Name: {model.name}")

if __name__ == '__main__':
    check()
