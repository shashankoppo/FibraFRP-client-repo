# -*- coding: utf-8 -*-
{
    "name": "ELSX Apps Password Gate",
    "version": "2.6.0",
    "category": "Administration",
    "summary": "Password protection for the native Odoo Apps screen",
    "description": """
ELSX Apps Password Gate
=======================

This compatibility addon has one access-control responsibility: system
administrators must enter the configured Apps password before opening Odoo's
native Apps screen. Settings, Users, Companies, module dependencies, and all
other Odoo access rules remain under standard Odoo Community behavior.
    """,
    "author": "ELSX",
    "website": "https://elsxglobal.com",
    "license": "LGPL-3",
    "depends": ["base", "base_setup", "web"],
    "data": [
        "data/apps_access.xml",
        "views/menu_restrictions.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
    "post_init_hook": "post_init_hook",
}
