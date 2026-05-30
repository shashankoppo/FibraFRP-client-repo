# -*- coding: utf-8 -*-
{
    'name': "ELSX Bank Reconciliation AI Engine",
    'summary': """
        Python-based Heuristic & ML Reconcile engine.""",
    'description': """
        Provides advanced fuzzy matching and machine-learning assisted
        reconciliation automation.
    """,
    'author': "ELSX",
    'category': 'Accounting/Accounting',
    'version': '19.0.1.0',
    'depends': ['account', 'om_account_accountant'],
    'data': [
        'security/ir.model.access.csv',
        'views/reconciliation_widget.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_bank_ai/static/src/js/reconciliation_action.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
