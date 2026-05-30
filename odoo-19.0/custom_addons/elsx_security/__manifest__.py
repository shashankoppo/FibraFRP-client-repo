{
    'name': 'ELSX ERP Security Core',
    'version': '1.0',
    'category': 'Security',
    'summary': 'Quantum-Scale Session Management & Threat Detection',
    'description': 'Provides high-frequency session auditing, IP-based access control, and autonomous threat detection.',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['base', 'web', 'elsx_blockchain_ledger'],
    'data': [
        'security/ir.model.access.csv',
        'views/security_config_views.xml',
    ],
    'installable': True,
    'application': True,
}
