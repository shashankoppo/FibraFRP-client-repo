# -*- coding: utf-8 -*-
{
    'name': 'ELSx Public Router',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Server-wide public redirects for multi-database kiosk links',
    'description': '''
Small server-wide router for public links that need to select a database before
reaching normal Odoo controllers, such as attendance kiosk URLs.
    ''',
    'author': 'ELSxGlobal',
    'website': 'https://elsxglobal.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
