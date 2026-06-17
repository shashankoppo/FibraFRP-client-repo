{
    'name': 'ELSX ERP SaaS Master',
    'version': '19.0.2.0.0',
    'category': 'SaaS',
    'summary': 'Enterprise SaaS tenant registry, API management, billing, and admin governance',
    'description': '''
Enterprise SaaS tenant registry with complete lifecycle management.

Features:
- Safe SaaS tenant registry and admin governance
- API token management and audit logging
- Tenant health checks and usage analytics
- Support ticket system with SLA tracking
- Billing plans, invoicing, and subscription management
- Webhook events and integrations
- Production-safe deployment controls

This module does not create/drop databases directly from the UI. It records
tenant lifecycle, modules, and deployment plans so production database work
stays behind encrypted backup and controlled shell scripts.
    ''',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/saas_security.xml',
        'security/ir.model.access.csv',
        'views/saas_tenant_views.xml',
        'views/saas_advanced_views.xml',
        'views/saas_enterprise_views.xml',
        'data/sequences_and_plans.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_saas/static/src/css/saas_admin.css',
        ],
    },
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
