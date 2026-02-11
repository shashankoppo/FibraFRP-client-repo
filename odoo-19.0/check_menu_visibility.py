
import odoo
from odoo import api, SUPERUSER_ID

registry = odoo.registry('elsx_dev')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get a regular user (not admin) to test
    user = env['res.users'].search([('login', '=', 'admin')], limit=1) # Or create a test user
    
    # Test for admin first as that's usually the superuser
    menu_model = env['ir.ui.menu'].with_user(user)
    
    menus = menu_model.load_menus(debug=False)
    
    apps_menu = env.ref('base.menu_apps', raise_if_not_found=False)
    
    if apps_menu:
        apps_menu_id = apps_menu.id
        
        is_visible = False
        if str(apps_menu_id) in menus:
            is_visible = True
        
        # Check root children
        if 'root' in menus and apps_menu_id in menus['root'].get('children', []):
             is_visible = True

        if is_visible:
            print(f"FAIL: Apps menu ({apps_menu_id}) is still visible!")
        else:
            print(f"SUCCESS: Apps menu ({apps_menu_id}) is hidden.")
    else:
        print("Note: Apps menu reference not found.")
