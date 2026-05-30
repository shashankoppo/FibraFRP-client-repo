import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api, SUPERUSER_ID

def test_postcommit():
    db_name = 'qwerty'
    odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', db_name])
    
    from odoo.modules.registry import Registry
    registry = Registry(db_name)
    with registry.cursor() as cr:
        print("Registering postcommit callback...")
        
        def my_callback():
            print("POSTCOMMIT CALLBACK EXECUTED!")
            
        cr.postcommit.add(my_callback)
        print("Calling cr.commit()...")
        cr.commit()
        print("After cr.commit().")

if __name__ == '__main__':
    test_postcommit()
