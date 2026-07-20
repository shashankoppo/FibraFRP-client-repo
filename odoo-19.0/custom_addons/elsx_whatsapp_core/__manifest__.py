# -*- coding: utf-8 -*-
{
    'name': 'ELSX WhatsApp Core',
    'summary': 'Persistent WhatsApp records and runtime services independent of the removable UI shell',
    'version': '19.0.1.0.5',
    'category': 'Hidden',
    'author': 'ELSX Global',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'crm',
        'contacts',
        'mail',
        'sale',
        'account',
        'base_setup',
        'elsx_ai_core',
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
