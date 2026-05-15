{
    'name': 'ELSX AI Marketing Agent',
    'version': '1.0',
    'category': 'Marketing',
    'summary': 'Autonomous AI-driven Lead Gen & Content Generation',
    'description': 'Leverages LLMs to generate email campaigns, social posts, and analyze CRM sentiment.',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['crm', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/marketing_ai_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
