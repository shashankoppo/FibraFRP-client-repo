import odoo
from odoo import api, registry

# Load odoo config from odoo.conf
odoo.tools.config.parse_config(['-c', 'odoo.conf'])

db_name = 'elsx_dev'
reg = registry(db_name)
with reg.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    menu = env.ref('base.menu_management', raise_if_not_found=False)
    if menu:
        action = menu.action
        print(f"APPS_MENU_ID={menu.id}")
        if action:
            print(f"APPS_ACTION_ID={action.id}")
    else:
        print("Apps menu not found")

    settings_menu = env.ref('base.menu_administration', raise_if_not_found=False)
    if settings_menu:
        print(f"SETTINGS_MENU_ID={settings_menu.id}")
