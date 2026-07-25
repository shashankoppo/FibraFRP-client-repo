{
    'name': 'ELSX AI Marketing Agent',
    'version': '1.0',
    'category': 'Marketing',
    'summary': 'Draft-only AI lead and content assistance',
    'description': 'Uses the shared ELSX AI service layer to draft CRM replies and marketing copy with user approval.',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['crm', 'mail', 'elsx_whatsapp_marketing'],
    'data': [
        'security/ir.model.access.csv',
        'views/marketing_ai_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': True,
}
