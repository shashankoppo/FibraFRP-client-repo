# -*- coding: utf-8 -*-
{
    'name': 'ELSX System Access Helpers',
    'version': '2.2.3',
    'category': 'Administration',
    'summary': 'Hidden Apps menu with controlled admin shortcut',
    'description': '''
        ELSX System Access Helpers
        ==========================

        This addon is intentionally kept as a compatibility shell for databases
        where an older access-helper technical module was already installed.

        Current behavior:
        - Apps menu hidden from normal navigation by customer request
        - Apps action available only from an admin token URL shortcut
        - No automatic module upgrade side effects
        - Standard Odoo group permissions remain in charge
    ''',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/apps_access.xml',
        'views/branding_templates.xml',
        'views/menu_restrictions.xml',
        'views/module_safety_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_client_restrictions/static/src/js/elsx_branding.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
}
