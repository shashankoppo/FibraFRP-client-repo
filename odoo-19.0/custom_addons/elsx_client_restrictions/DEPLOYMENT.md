# Deployment

Deploy this addon like any normal custom module. It does not delete records,
uninstall modules, drop databases, or touch the Odoo filestore.

Recommended checks after upgrade:

- Apps opens for system administrators through `/elsx-secret/apps/<token>`.
- Legacy `/action-39/<token>` bookmarks still work.
- Regular users see only menus allowed by their Odoo groups.
- Module list refresh does not trigger automatic upgrades.

To retrieve the Apps URL for a database, run a controlled admin query and keep
the token private:

```bash
docker compose exec -T db psql -U odoo -d YOUR_DB -Atc "SELECT '/elsx-secret/apps/' || value FROM ir_config_parameter WHERE key='elsx_client_restrictions.apps_secret_token';"
```