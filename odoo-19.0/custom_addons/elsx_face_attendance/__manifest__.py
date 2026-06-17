# -*- coding: utf-8 -*-
{
    'name': 'ELSx Face Attendance',
    'version': '19.0.1.5.1',
    'category': 'Human Resources/Attendances',
    'summary': 'Optional facial verification for Attendances with local Docker processing',
    'description': '''
ELSx Face Attendance
====================

Adds optional face verification on top of standard Attendances. The feature is
disabled by default, uses a local sidecar when enabled, and keeps normal
check-in/check-out behavior unchanged.
    ''',
    'author': 'ELSxGlobal',
    'website': 'https://elsxglobal.com',
    'license': 'LGPL-3',
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'views/face_attendance_templates.xml',
        'views/hr_attendance_views.xml',
        'views/hr_employee_views.xml',
        'views/face_attendance_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'elsx_face_attendance/static/src/css/face_attendance.css',
            'elsx_face_attendance/static/src/js/face_attendance_portal.js',
        ],
        'hr_attendance.assets_public_attendance': [
            'elsx_face_attendance/static/src/xml/face_attendance_kiosk.xml',
            'elsx_face_attendance/static/src/css/face_attendance.css',
            'elsx_face_attendance/static/src/js/face_attendance_portal.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
