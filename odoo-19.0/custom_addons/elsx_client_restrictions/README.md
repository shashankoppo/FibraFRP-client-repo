# ELSX System Access Helpers

This addon is kept as a compatibility shell for databases where the existing
`elsx_client_restrictions` technical module was already installed.

Current behavior:

- Standard Odoo access groups control menus and actions.
- The addon leaves the Apps menu to standard Odoo group behavior.
- The addon does not auto-upgrade modules during app-list refresh.
- `/action-39` remains only as a legacy bookmark shortcut to the normal Apps action.

Use Odoo Settings and user groups for access control.
