# -*- coding: utf-8 -*-
{
    'name': 'ELSX System Access Helpers',
    'version': '2.4.1',
    'category': 'Administration',
    'summary': 'Admin Apps access helper with controlled shortcut',
    'description': '''
        ELSX System Access Helpers
        ==========================

        Compatibility shell for databases where the older access-helper
        technical module was already installed.

        Current behavior:
        - Settings remains available to system administrators
        - Apps requires the configured password before module access
        - Secret Apps URL remains available as an admin-only shortcut
        - No broad ir.module.module read interception
        - elsx_saas is no longer protected from safe uninstall
        - No automatic module upgrade side effects
        - Standard Odoo group permissions remain in charge
    ''',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'license': 'LGPL-3',
    'depends': ['base', 'base_setup', 'web'],
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
