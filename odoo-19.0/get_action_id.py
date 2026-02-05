
import odoo
from odoo import api, Registry

def get_action_id():
    odoo.tools.config.parse_config(['-c', 'odoo.conf'])
    registry = Registry('elsx_dev')
    with registry.cursor() as cr:
        env = api.Environment(cr, 1, {})
        action = env.ref('base.open_module_tree')
        print(f"ACTION_ID:{action.id}")

if __name__ == "__main__":
    get_action_id()
