{
    'name': 'ELSX Advanced Views (Gantt & Map)',
    'version': '1.0',
    'summary': 'OWL Gantt and Map Renderers',
    'description': 'Injects native cohort, gantt, and map view architectural capabilities.',
    'author': 'ELSX',
    'depends': ['base', 'web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'elsx_gantt_cohort/static/src/js/gantt_view.js',
            # You will place standard Frappe Gantt css/js here before launch.
            # 'elsx_gantt_cohort/static/lib/frappe-gantt.min.js',
            # 'elsx_gantt_cohort/static/lib/frappe-gantt.css',
        ]
    },
    'installable': True,
}
