{
    'name': 'ELSX ERP Rebrand',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Total rebranding of Odoo to ELSX ERP',
    'description': 'Removes Odoo branding, replaces logos, and updates UI to ELSX Luxury Cyberpunk style.',
    'author': 'Antigravity (ELSX Evolution Engine)',
    'website': 'https://elsx-erp.com',
    'depends': ['web'],
    'data': [
        'views/rebrand_assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_rebrand/static/src/css/elsx_style.css',
            # 'elsx_rebrand/static/src/js/elsx_unlocker.js',
            # 'elsx_rebrand/static/src/js/elsx_assistant.js',
            # 'elsx_rebrand/static/src/xml/elsx_assistant_templates.xml',
        ],
        'web.assets_frontend': [
            'elsx_rebrand/static/src/css/elsx_style.css',
        ],
    },
    'qweb': [
        # 'static/src/xml/*.xml',
    ],
    'installable': True,
    'application': True,
}
