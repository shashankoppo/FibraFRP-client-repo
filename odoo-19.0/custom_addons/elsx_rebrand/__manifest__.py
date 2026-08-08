{
    'name': 'ELSxGlobal Rebrand',
    'version': '1.2.6',
    'category': 'Tools',
    'summary': 'Remove visible platform branding from the UI',
    'description': 'Removes visible platform branding from backend, frontend, login, footer, title, browser, PWA, report, email template, and Apps metadata strings without touching business data.',
    'author': 'ELSxGlobal',
    'license': 'LGPL-3',
    'website': 'https://elsxglobal.com',
    'depends': ['web'],
    'data': [
        'data/rebrand_runtime.xml',
        'views/rebrand_assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_rebrand/static/src/css/website_editor_compat.css',
            'elsx_rebrand/static/src/xml/backend_branding.xml',
            'elsx_rebrand/static/src/js/backend_branding.js',
        ],
        'web.assets_frontend': [
            'elsx_rebrand/static/src/css/no_portal_branding.css',
        ],
        'point_of_sale._assets_pos': [
            'elsx_rebrand/static/src/xml/pos_branding.xml',
        ],
        'point_of_sale.customer_display_assets': [
            'elsx_rebrand/static/src/xml/pos_branding.xml',
        ],
        'html_builder.iframe_add_dialog': [
            'elsx_rebrand/static/src/css/website_editor_iframe_compat.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
}
