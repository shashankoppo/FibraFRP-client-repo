{
    'name': 'ELSX Approvals (HR Ecosystem)',
    'version': '1.0',
    'summary': 'Multi-Level HR Approvals Engine',
    'description': """
        Supports custom multi-level approval workflows for:
        - Leave Requests
        - Expense Reports
        - Purchase Orders
        - Custom internal approvals
        Each approval type supports sequential or parallel routing.
    """,
    'author': 'ELSX',
    'depends': ['hr', 'mail', 'hr_holidays', 'hr_expense'],
    'data': [
        'security/ir.model.access.csv',
        'data/approval_type_data.xml',
        'views/approval_request_views.xml',
        'views/approval_type_views.xml',
    ],
    'installable': True,
    'application': True,
}
