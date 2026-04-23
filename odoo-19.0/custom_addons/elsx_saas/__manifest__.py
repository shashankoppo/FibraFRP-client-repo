{
    'name': 'ELSX ERP SaaS Master',
    'version': '1.0',
    'category': 'SaaS',
    'summary': 'Multi-Tenant Database Provisioning & Management',
    'description': 'Master dashboard to spin up, monitor, and manage autonomous ELSX ERP instances.',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/saas_tenant_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': True,
}
