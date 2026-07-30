{
    'name': 'ELSxGlobal Rebrand',
    'version': '1.2.1',
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
    'installable': True,
    'application': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
}
