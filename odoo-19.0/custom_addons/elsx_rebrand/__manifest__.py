{
    'name': 'ELSxGlobal Rebrand',
    'version': '1.1.0',
    'category': 'Tools',
    'summary': 'Replace visible Odoo UI branding with ELSxGlobal',
    'description': 'Rebrands visible backend, frontend, login, footer, title, and browser UI strings to ELSxGlobal without touching business data.',
    'author': 'ELSxGlobal',
    'license': 'LGPL-3',
    'website': 'https://elsxglobal.com',
    'depends': ['web'],
    'data': [
        'views/rebrand_assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_rebrand/static/src/css/elsx_style.css',
            'elsx_rebrand/static/src/js/elsx_unlocker.js',
        ],
        'web.assets_frontend': [
            'elsx_rebrand/static/src/css/elsx_style.css',
            'elsx_rebrand/static/src/js/elsx_unlocker.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
}
