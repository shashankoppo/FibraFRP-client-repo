# ELSX System Access Helpers

This addon preserves a known Apps URL path for trusted administrators while
leaving normal Odoo Settings, Apps, and group permissions in charge.

Current behavior:

- Settings and Apps remain available to system administrators.
- System administrators can also open Apps through `/elsx-secret/apps/<token>`.
- Legacy bookmarks using `/action-39/<token>` continue to redirect to Apps.
- The secret token is stored in `elsx_client_restrictions.apps_secret_token` and
  is created automatically on install/upgrade if missing.
- Older production metadata that hid Apps or broke Settings is repaired
  idempotently at menu load time; this touches only Odoo technical metadata.
- `elsx_saas` is no longer protected by this helper, so it can be removed by a
  backup-first uninstall script when explicitly requested.
- Module installs/upgrades stay under Odoo permissions and the backup-first
  deployment scripts; this addon does not auto-upgrade modules during app-list
  refresh or container startup.

Use Odoo Settings and user groups for normal access control. Share the Apps URL
only with trusted system administrators.
