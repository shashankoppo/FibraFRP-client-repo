# -*- coding: utf-8 -*-
{
    'name': 'ELSx Attendance Tunnel Tracking',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Improves attendance IP/location capture behind tunnels and proxies',
    'description': '''
ELSx Attendance Tunnel Tracking
===============================

This addon keeps standard Attendances behavior intact and only improves device
tracking metadata capture when Odoo is accessed through a tunnel or reverse
proxy. It also makes the existing attendance IP/location fields easier for HR
users to see in the attendance list.
    ''',
    'author': 'ELSxGlobal',
    'website': 'https://elsxglobal.com',
    'license': 'LGPL-3',
    'depends': ['hr_attendance'],
    'data': [
        'views/hr_attendance_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
}
