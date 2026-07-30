{
    'name': 'ELSxGlobal Rebrand',
    'version': '1.2.4',
    'category': 'Tools',
    'summary': 'Replace visible platform UI branding with ELSxGlobal',
    'description': 'Rebrands visible backend, frontend, login, footer, title, browser, PWA, report, and Apps metadata strings to ELSxGlobal without touching business data.',
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
        ],
        'web.assets_frontend_minimal': [
            ('after', 'website/static/src/js/content/redirect.js', 'elsx_rebrand/static/src/js/website_editor_entry.js'),
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
