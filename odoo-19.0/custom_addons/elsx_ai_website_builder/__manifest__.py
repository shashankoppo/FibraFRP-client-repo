# -*- coding: utf-8 -*-
{
    'name': 'ELSx AI Studio',
    'version': '19.0.1.5.0',
    'category': 'Website/Website',
    'summary': 'Draft-first AI website page and section builder using configured ELSx AI providers',
    'description': '''
ELSx AI Studio
==============

Adds a production-safe AI studio inside the core Website workflow and a wider
ELSx CE AI Command Center. It reuses the existing ELSx AI provider records,
including NVIDIA NIM, and creates Odoo snippet-friendly unpublished page
copies that Website Managers can edit with the standard Website editor before
publishing. Includes page blueprints, quality checks, section plans, studio
presets, and draft-first AI workspaces for website, CRM, WhatsApp, campaign,
SEO, UX, and module planning.
    ''',
    'author': 'ELSxGlobal',
    'website': 'https://elsxglobal.com',
    'license': 'LGPL-3',
    'depends': ['website', 'elsx_whatsapp_marketing'],
    'data': [
        'security/ai_website_builder_security.xml',
        'security/ir.model.access.csv',
        'data/ai_website_builder_prompts.xml',
        'views/ai_website_builder_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_ai_website_builder/static/src/css/ai_website_builder.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
