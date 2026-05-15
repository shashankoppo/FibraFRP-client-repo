import sys
sys.path.append('/opt/odoo')
import odoo
from odoo import api, SUPERUSER_ID

def check_db():
    db_name = 'qwerty'
    odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', db_name])
    from odoo.orm.registry import Registry
    registry = Registry(db_name)
    with registry.cursor() as cr:
        # Check which table has a foreign key to a non-existent column
        # We look for ANY constraint that references res_partner_category_id
        cr.execute("""
            SELECT tc.table_name, kcu.column_name, ccu.table_name as ref_table, ccu.column_name as ref_col
            FROM information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND (ccu.column_name = 'res_partner_category_id' OR kcu.column_name = 'res_partner_category_id');
        """)
        print(f"Results: {cr.fetchall()}")

if __name__ == '__main__':
    check_db()
