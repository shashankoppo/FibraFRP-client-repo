# -*- coding: utf-8 -*-
{
    "name": "ELSX Native Administration Cleanup",
    "version": "2.7.0",
    "category": "Administration",
    "summary": "Removes legacy restrictions and restores native Odoo administration",
    "description": """
ELSX Native Administration Cleanup
==================================

This technical compatibility addon removes retired ELSX access restrictions
and restores native Odoo Community Settings, Users, Companies, Apps, groups,
access-rights, and record-rule administration.
    """,
    "author": "ELSX",
    "website": "https://elsxglobal.com",
    "license": "LGPL-3",
    "depends": ["base", "base_setup", "web"],
    "data": [
        "data/native_admin_cleanup.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
    "post_init_hook": "post_init_hook",
}
