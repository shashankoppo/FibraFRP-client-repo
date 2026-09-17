# -*- coding: utf-8 -*-
{
    "name": "ELSX Apps Access and Native Administration",
    "version": "2.10.0",
    "category": "Administration",
    "summary": "Password-protected Apps entry with native ERP administration",
    "description": """
ELSX Native Administration Cleanup
==================================

This technical compatibility addon removes retired ELSX access restrictions
and restores native Community Settings, Users, Companies, groups, access rights
and record rules. Apps entry and module changes require a separate session unlock.
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
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
