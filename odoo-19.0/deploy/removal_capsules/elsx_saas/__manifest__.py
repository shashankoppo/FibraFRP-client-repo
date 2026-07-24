{
    'name': 'Retired ELSX SaaS Removal Capsule',
    'version': '19.0.3.2.0',
    'category': 'Hidden',
    'license': 'LGPL-3',
    'summary': 'Migration-only model registry used for safe uninstallation',
    'description': '''
Migration-only model registry. This directory is outside the active addon path
and is loaded solely by the backup-gated removal helper while uninstalling the
retired module from an existing database. It contains no data files, views,
menus, security rules, controllers, assets, or runtime activation path.
    ''',
    'author': 'ELSX',
    'website': 'https://elsxglobal.com',
    'depends': ['base', 'web', 'mail'],
    'data': [],
    'assets': {},
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
