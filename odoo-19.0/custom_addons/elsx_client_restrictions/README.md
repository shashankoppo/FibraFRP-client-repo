# ELSX System Access Helpers

This addon keeps production Apps/module access controlled while preserving a
known URL path for trusted administrators.

Current behavior:

- The raw Apps menu is hidden from normal navigation.
- System administrators can open Apps through `/elsx-secret/apps/<token>`.
- Legacy bookmarks using `/action-39/<token>` continue to redirect to Apps.
- The secret token is stored in `elsx_client_restrictions.apps_secret_token` and
  is created automatically on install/upgrade if missing.
- Module installs/upgrades stay under Odoo permissions and the backup-first
  deployment scripts; this addon does not auto-upgrade modules during app-list
  refresh.

Use Odoo Settings and user groups for normal access control. Share the Apps URL
only with trusted system administrators.