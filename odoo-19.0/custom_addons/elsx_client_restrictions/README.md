# ELSX Apps Password Gate

This addon keeps Odoo Community administration native except for one control:
system administrators must enter the configured password before opening Apps.

- Settings, Users, Companies, groups, and menus use standard Odoo behavior.
- Odoo's normal dependency rules control module install and uninstall impact.
- CLI upgrades remain available without an HTTP password session.
- A successful Apps unlock lasts 30 minutes; entering Apps again starts a fresh challenge.

The password is stored only as a SHA-256 hash in
`elsx_client_restrictions.apps_password_hash`.
