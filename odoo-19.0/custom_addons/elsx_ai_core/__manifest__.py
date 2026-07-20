# -*- coding: utf-8 -*-
{
    'name': 'ELSX AI Core',
    'summary': 'Persistent provider, prompt, job, log, and tool services for ELSX applications',
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': 'ELSX Global',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/elsx_ai_defaults.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
