{
    'name': 'ELSxGlobal Rebrand',
    'version': '1.1.1',
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
    'installable': True,
    'application': False,
    'auto_install': True,
}
