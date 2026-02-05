# -*- coding: utf-8 -*-
{
    'name': 'ELSX Client Restrictions',
    'version': '2.0.0',
    'category': 'Hidden',
    'summary': 'Secret URL Access Control & Auto-Dependency Management',
    'description': '''
        Advanced Access Control System
        ===============================
        
        This module implements a sophisticated access control system:
        
        **Secret URL Access:**
        - Removes ALL standard access to Apps menu (including admin)
        - Only /action-39 URL provides access to Apps module
        - Client-side and server-side validation
        
        **Module Management:**
        - No restrictions on installed modules
        - Auto-fetch module updates
        - Auto-upgrade dependencies
        - Auto-install missing dependencies
        
        **Security:**
        - Menu-based restrictions
        - URL-based access control
        - Session-based validation
        
        Access Apps via: http://your-domain/action-39
    ''',
    'author': 'ELSX Evolution Engine',
    'website': 'https://elsx-erp.com',
    'depends': ['base', 'web'],
    'data': [
        'security/security_groups.xml',
        'views/menu_restrictions.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
    'license': 'LGPL-3',
}
