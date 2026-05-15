
import json
import logging
from odoo import api, SUPERUSER_ID

def run(env):
    templates = env['whatsapp.template'].search([])
    for t in templates:
        print(f"Name: {t.name}, Meta Name: {t.meta_template_name}, Lang: {t.language}, Code: {t.language_code}")
