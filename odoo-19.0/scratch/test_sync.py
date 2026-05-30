import sys
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config

def test_sync():
    # In docker, the config file is at /etc/odoo/odoo.conf
    config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', 'qwerty'])
    registry = Registry('qwerty')

    
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        
        # Helper to search
        def find_partner(name):
            return env['res.partner'].search([('name', '=', name)], limit=1)
            
        def find_whatsapp_contact(name):
            return env['whatsapp.contact'].search([('name', '=', name)], limit=1)
            
        # Clean up any existing test records
        test_partners = env['res.partner'].search([('name', 'like', 'TEST_SYNC_')])
        if test_partners:
            test_partners.unlink()
        test_contacts = env['whatsapp.contact'].search([('name', 'like', 'TEST_SYNC_')])
        if test_contacts:
            test_contacts.unlink()
            
        print("res.partner fields:", [f for f in env['res.partner']._fields if 'phone' in f or 'mobile' in f or 'whatsapp' in f])
        print("--- TEST 1: Creating res.partner with phone/mobile ---")
        partner = env['res.partner'].create({
            'name': 'TEST_SYNC_PARTNER_1',
            'phone': '+91 98765 43210',
            'whatsapp_opt_in': True,
        })
        print(f"Created Partner ID: {partner.id}, name: {partner.name}, phone: {partner.phone}, whatsapp_opt_in: {partner.whatsapp_opt_in}")
        
        # Verify contact was created
        contact = env['whatsapp.contact'].search([('partner_id', '=', partner.id)], limit=1)
        if not contact:
            # Maybe searched by phone
            normalized = ''.join(c for c in partner.phone if c.isdigit())
            contact = env['whatsapp.contact'].search([('phone_number', '=', normalized)], limit=1)
        
        if contact:
            print(f"SUCCESS: WhatsApp Contact created automatically! ID: {contact.id}, name: {contact.name}, phone: {contact.phone_number}, opt_in: {contact.opt_in}")
        else:
            print("FAILURE: No WhatsApp Contact created automatically for partner.")
            
        print("\n--- TEST 2: Bidirectional Sync - Partner Opt-out ---")
        partner.write({'whatsapp_opt_in': False})
        env.cr.commit()  # Flush/commit to trigger any side effects
        
        # Reload contact
        if contact:
            contact.invalidate_recordset()
            print(f"Partner opt_in set to False. Contact opt_in is now: {contact.opt_in}")
            if contact.opt_in is False:
                print("SUCCESS: Partner opt-out synced to WhatsApp contact.")
            else:
                print("FAILURE: Partner opt-out NOT synced to WhatsApp contact.")
        
        print("\n--- TEST 3: Bidirectional Sync - Contact Opt-in ---")
        if contact:
            contact.write({'opt_in': True})
            env.cr.commit()
            partner.invalidate_recordset()
            print(f"Contact opt_in set to True. Partner whatsapp_opt_in is now: {partner.whatsapp_opt_in}")
            if partner.whatsapp_opt_in is True:
                print("SUCCESS: Contact opt-in synced to Partner.")
            else:
                print("FAILURE: Contact opt-in NOT synced to Partner.")

        print("\n--- TEST 4: Update Partner name & phone ---")
        partner.write({
            'name': 'TEST_SYNC_PARTNER_1_UPDATED',
            'phone': '+919999988888'
        })
        env.cr.commit()
        if contact:
            contact.invalidate_recordset()
            print(f"Partner name updated to: {partner.name}, phone: {partner.phone}")
            print(f"Contact name is now: {contact.name}, phone is now: {contact.phone_number}")
            if contact.name == 'TEST_SYNC_PARTNER_1_UPDATED' and '9999988888' in contact.phone_number:
                print("SUCCESS: Partner name and phone updates synced to contact.")
            else:
                print("FAILURE: Partner name/phone updates did not sync to contact.")

        print("\n--- TEST 5: Create WhatsApp contact first, should link partner ---")
        partner_link = env['res.partner'].create({
            'name': 'TEST_SYNC_PARTNER_2',
            'phone': '+917777777777',
        })
        
        # Create whatsapp contact with same phone
        new_contact = env['whatsapp.contact'].create({
            'name': 'TEST_SYNC_CONTACT_2',
            'phone_number': '917777777777',
            'opt_in': True,
        })
        print(f"Created Contact: ID: {new_contact.id}, name: {new_contact.name}, phone: {new_contact.phone_number}")
        print(f"Linked Partner ID: {new_contact.partner_id.id if new_contact.partner_id else 'None'} (Expected Partner ID: {partner_link.id})")
        if new_contact.partner_id == partner_link:
            print("SUCCESS: Auto-linked existing partner by phone number.")
        else:
            print("FAILURE: Did not auto-link existing partner by phone.")

        # Clean up
        partner.unlink()
        partner_link.unlink()
        if contact:
            contact.unlink()
        new_contact.unlink()
        print("Cleaned up test records successfully.")

if __name__ == '__main__':
    test_sync()
