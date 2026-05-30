import sys
import json
sys.path.insert(0, '/opt/odoo')
import odoo
from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import config
config.parse_config(['-c', '/etc/odoo/odoo.conf'])

registry = Registry('qwerty')
with registry.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    
    # Find all whatsapp message records where message_type is template
    messages = env['whatsapp.message'].search([('message_type', '=', 'template')])
    print(f"Found {len(messages)} template messages.")
    
    updated_count = 0
    for msg in messages:
        template_name = msg.template_name
        body = msg.body
        
        # Try to parse from raw_data if template_name is not set
        if not template_name and msg.raw_data:
            try:
                data = json.loads(msg.raw_data)
                template_name = data.get('template', {}).get('name')
            except Exception as e:
                print(f"Error parsing raw_data for msg {msg.id}: {e}")
                
        if template_name:
            # Let's find the template
            template = env['whatsapp.template'].sudo().search([('name', '=', template_name)], limit=1)
            if template:
                vals = {}
                if not msg.template_name:
                    vals['template_name'] = template_name
                if not msg.template_id:
                    vals['template_id'] = template.id
                if not body or body == 'Media: template' or body == 'Template Sent':
                    vals['body'] = template.body
                
                if vals:
                    msg.write(vals)
                    updated_count += 1
                    print(f"Updated msg {msg.id}: {vals}")
            else:
                print(f"Template '{template_name}' not found in database for msg {msg.id}")
                
    cr.commit()
    print(f"Successfully updated {updated_count} messages.")
