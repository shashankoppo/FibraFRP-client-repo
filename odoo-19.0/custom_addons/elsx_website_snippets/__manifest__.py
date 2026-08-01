# -*- coding: utf-8 -*-
{
    'name': 'ELSX Website Snippet Library',
    'summary': 'Reusable business website snippets for Odoo Website editor',
    'version': '19.0.1.3.0',
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
        'website.website_builder_assets': [
            'elsx_website_snippets/static/src/builder/plugins/options/elsx_website_options.xml',
            'elsx_website_snippets/static/src/builder/plugins/options/elsx_website_options.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
}

