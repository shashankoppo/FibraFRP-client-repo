# -*- coding: utf-8 -*-
{
    'name': 'ELSX Website Snippet Library',
    'summary': 'Reusable business website snippets for Odoo Website editor',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': 'ELSX Global',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/snippets.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'elsx_website_snippets/static/src/css/snippets.css',
        ],
        'website.assets_wysiwyg': [
            'elsx_website_snippets/static/src/css/snippets.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
}

