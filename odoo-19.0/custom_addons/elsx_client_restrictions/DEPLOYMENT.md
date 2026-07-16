# Deployment

Deploy this addon like any normal custom module. It does not delete records,
uninstall modules, drop databases, or touch the Odoo filestore.

Safe with normal production restart:

```bash
docker compose up -d --build
```

The restart loads the updated Python code immediately. A small idempotent repair
runs when Odoo loads menus and only restores technical metadata for core admin
menus and known stale Settings views. It does not touch contacts, invoices,
WhatsApp data, attendance, CRM, Tally, websites, databases, Docker volumes, or
filestore attachments.

Recommended checks after deployment:

- Settings opens for system administrators.
- Apps opens for system administrators from the menu and through `/elsx-secret/apps/<token>`.
- Legacy `/action-39/<token>` bookmarks still work.
- Regular users see only menus allowed by their Odoo groups.
- Module list refresh does not trigger automatic upgrades.

To retrieve the Apps URL for a database, run a controlled admin query and keep
the token private:

```bash
docker compose exec -T db psql -U odoo -d YOUR_DB -Atc "SELECT '/elsx-secret/apps/' || value FROM ir_config_parameter WHERE key='elsx_client_restrictions.apps_secret_token';"
```
