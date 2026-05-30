# -*- coding: utf-8 -*-
{
    'name': 'ELSX Tally Invoice Bridge',
    'summary': 'Export and push Odoo invoices to Tally XML gateway',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': 'ELSX Global',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/tally_sync_log_views.xml',
    ],
    'installable': True,
    'application': False,
}
