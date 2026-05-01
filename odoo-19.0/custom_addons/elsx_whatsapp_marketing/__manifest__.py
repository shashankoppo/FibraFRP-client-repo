{
    'name': 'ELSX WhatsApp Marketing & Automation',
    'version': '19.0.1.0.6',
    'category': 'Marketing/WhatsApp',
    'summary': 'Next-Gen WhatsApp Business API & AI-Powered Marketing Automation',
    'description': '''
        ELSX WhatsApp Evolution
        =======================
        
        The planet's most advanced WhatsApp Business integration for Odoo.
        
        **Elite Features:**
        *   **Meta Cloud API Sync**: Real-time synchronization with Meta Business Suite.
        *   **AI Smart Reply**: GPT-4o powered autonomous customer engagement.
        *   **Deep CRM Sync**: Automatic lead nurturing via WhatsApp.
        *   **Blockchain Logging**: Every message verified on the ELSX Immutable Ledger.
        *   **Dynamic Templates**: Interactive buttons, lists, and catalog support.
        *   **ROI Dashboard**: Real-time conversion tracking and analytics.
    ''',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': [
        'base',
        'web',
        'crm',
        'sale',
        'mail',
        'contacts',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/whatsapp_security.xml',
        'data/whatsapp_templates.xml',
        'views/whatsapp_message_views.xml',
        'views/whatsapp_template_views.xml',
        'wizard/send_whatsapp_wizard_views.xml',
        'views/whatsapp_chat_views.xml',
        'views/whatsapp_campaign_views.xml',
        'views/whatsapp_contact_views.xml',
        'views/whatsapp_account_views.xml',
        'views/whatsapp_menu.xml',
        'data/whatsapp_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elsx_whatsapp_marketing/static/src/css/whatsapp.css',
            'elsx_whatsapp_marketing/static/src/js/whatsapp_widget.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
