{
    'name': 'ELSX Blockchain Audit Ledger',
    'version': '1.0',
    'category': 'Security',
    'summary': 'Immutable blockchain-style audit logs for critical transactions.',
    'description': 'Provides a tamper-proof ledger for sales, invoices, and payments using cryptographic hashing.',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['base', 'account', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/blockchain_ledger_views.xml',
    ],
    'installable': True,
    'application': True,
}
