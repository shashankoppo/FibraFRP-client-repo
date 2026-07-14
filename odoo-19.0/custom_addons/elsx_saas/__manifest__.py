{
    'name': 'ELSX ERP SaaS Master (Deactivated)',
    'version': '19.0.3.2.0',
    'category': 'SaaS',
    'license': 'LGPL-3',
    'summary': 'Passive SaaS governance records with automation disabled by default',
    'description': '''
Passive SaaS governance layer.

Current production mode:
- SaaS automation is disabled by default (elsx_saas.enabled = 0)
- No tenant database is created, cloned, dropped, restored, or modified from the UI
- No app/module is installed from the SaaS UI while disabled
- SaaS billing crons are inactive while disabled
- SaaS menus and native app-store overrides are hidden by the deactivation cleanup
- Client databases, CRM, WhatsApp, invoices, attendance, Tally, website, and filestore data stay untouched

This addon remains installable only so existing deployments can receive the
safe deactivation metadata update. Re-enable only after a separate production
approval and staging verification.
    ''',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/saas_security.xml',
        'security/ir.model.access.csv',
        'views/saas_tenant_views.xml',
        'views/saas_dashboard_views.xml',
        'views/saas_advanced_views.xml',
        'views/saas_enterprise_views.xml',
        'views/saas_app_views.xml',
        'views/saas_user_views.xml',
        'views/saas_user_dashboard_views.xml',
        'views/saas_native_apps_override.xml',
        'data/sequences_and_plans.xml',
        'data/saas_cron.xml',
        'data/saas_deactivation.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_saas/static/src/css/saas_admin.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
