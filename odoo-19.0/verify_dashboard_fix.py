import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

log_file = open('/opt/odoo/verify_output.txt', 'w', encoding='utf-8')
def log(msg):
    log_file.write(str(msg) + '\n')
    log_file.flush()

registry = Registry('qwerty')
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})

    log("=" * 70)
    log("DASHBOARD FIX VERIFICATION REPORT")
    log("=" * 70)

    # 1. Check ir.actions.client record
    log("\n--- 1. ir.actions.client record ---")
    client_data = env['ir.model.data'].search([
        ('module', '=', 'elsx_whatsapp_marketing'),
        ('name', '=', 'action_whatsapp_dashboard_client'),
    ])
    if client_data:
        client_action = env['ir.actions.client'].browse(client_data.res_id)
        log(f"  FOUND: id={client_action.id}, name='{client_action.name}', tag='{client_action.tag}'")
    else:
        log("  NOT FOUND! The client action was not loaded.")

    # 2. Check ir.actions.server record (legacy)
    log("\n--- 2. ir.actions.server record (legacy) ---")
    server_data = env['ir.model.data'].search([
        ('module', '=', 'elsx_whatsapp_marketing'),
        ('name', '=', 'action_whatsapp_dashboard_server'),
    ])
    if server_data:
        server_action = env['ir.actions.server'].browse(server_data.res_id)
        log(f"  FOUND: id={server_action.id}, name='{server_action.name}'")
    else:
        log("  NOT FOUND!")

    # 3. Check the Dashboard menu item
    log("\n--- 3. Dashboard menu item ---")
    menu_data = env['ir.model.data'].search([
        ('module', '=', 'elsx_whatsapp_marketing'),
        ('name', 'like', 'menu_whatsapp_analytics'),
    ])
    for md in menu_data:
        menu = env['ir.ui.menu'].browse(md.res_id)
        action_ref = menu.action
        log(f"  Menu: '{menu.name}' (xmlid: {md.name})")
        if action_ref:
            log(f"    Action type: {action_ref._name}")
            log(f"    Action id: {action_ref.id}")
            log(f"    Action name: {action_ref.name}")
            if hasattr(action_ref, 'tag'):
                log(f"    Action tag: {action_ref.tag}")
        else:
            log("    Action: NONE (menu has no action!)")

    # 4. Check the whatsapp_marketing_dashboard JS tag registration
    log("\n--- 4. All ir.actions.client with tag 'whatsapp_marketing_dashboard' ---")
    actions = env['ir.actions.client'].search([('tag', '=', 'whatsapp_marketing_dashboard')])
    for a in actions:
        log(f"  id={a.id}, name='{a.name}', tag='{a.tag}'")
    if not actions:
        log("  NONE FOUND!")

    # 5. Module state
    log("\n--- 5. Module state ---")
    module = env['ir.module.module'].search([('name', '=', 'elsx_whatsapp_marketing')])
    log(f"  Module state: {module.state}")

    log("\n" + "=" * 70)
    log("VERIFICATION COMPLETE")
    log("=" * 70)

log_file.close()
