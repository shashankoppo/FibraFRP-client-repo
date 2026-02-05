import odoo
from odoo import api

odoo.tools.config.parse_config(['-c', 'odoo.conf'])

db_name = 'elsx_dev'
with odoo.api.Environment.manage():
    reg = odoo.registry(db_name)
    with reg.cursor() as cr:
        env = api.Environment(cr, odoo.SUPERUSER_ID, {})
        group = env.ref('elsx_client_restrictions.group_system_admin_only', raise_if_not_found=False)
        admin = env.ref('base.user_admin', raise_if_not_found=False)
        if group and admin:
            if admin not in group.user_ids:
                group.user_ids = [(4, admin.id)]
                print(f"Added admin user to {group.name}")
            else:
                print("Admin user already in group")
        else:
            print("Group or Admin user not found")
        cr.commit()
