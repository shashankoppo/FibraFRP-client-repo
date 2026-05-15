from odoo import api, SUPERUSER_ID
import odoo

def check_fields():
    registry = odoo.modules.registry.Registry('qwerty')
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        fields = env['crm.lead']._fields.keys()
        print("CRM_LEAD_FIELDS: " + ",".join(fields))

if __name__ == "__main__":
    check_fields()
