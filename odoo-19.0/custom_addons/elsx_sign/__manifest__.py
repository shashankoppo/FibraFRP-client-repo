{
    'name': 'ELSX eSignature (HR Ecosystem)',
    'version': '1.0',
    'summary': 'Digital Signing & Approvals',
    'description': """
        Allows HR and users to send documents (PDFs) for digital e-signatures
        with legally binding hash logs and public facing Canvas links.
    """,
    'author': 'ELSX',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_templates.xml',
        'views/sign_request_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            # Open source signature pad for public portal
            'elsx_sign/static/src/js/signature_pad.js',
        ]
    },
    'installable': True,
}
