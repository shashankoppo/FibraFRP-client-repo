{
    'name': 'ELSX HR Onboarding & Document Signing',
    'version': '1.0',
    'summary': 'Full Employee Onboarding Pipeline with eSignature',
    'description': """
        End-to-end Employee Onboarding system:
        - Onboarding plan with checklist tasks (IT setup, NDA, Training, etc.)
        - Automatic dispatch of signing requests via elsx_sign module
        - Employee portal view for task completion
        - HR dashboard for progress tracking
    """,
    'author': 'ELSX',
    'depends': ['hr', 'mail', 'elsx_sign'],
    'data': [
        'security/ir.model.access.csv',
        'views/onboarding_plan_views.xml',
        'views/onboarding_stage_views.xml',
        'views/hr_employee_views.xml',
        'data/onboarding_stages_data.xml',
    ],
    'installable': True,
    'application': True,
}
