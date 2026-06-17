# ELSx SaaS Governance Notes

This module protects a deployed client database from accidental platform damage.
It does not change existing users, companies, records, access rights, WhatsApp
accounts, campaigns, invoices, Tally settings, or attendance records.

Protected modules cannot be uninstalled from the normal Apps UI unless a
technical recovery context is deliberately used by a developer:

- CRM
- Contacts
- Sales
- Accounting / Invoicing
- WhatsApp Marketing
- Attendance
- Attendance Tracking
- Tally integration
- Client Restrictions
- Face Attendance
- Base web/mail/system modules

Admins can open **Settings > Technical > Safe Module Change** to review a module
operation before deployment. The wizard checks whether a protected module or a
downstream dependency is involved and requires confirmation that an encrypted
backup exists.

The SaaS admin console lives in **ELSx SaaS Admin > Tenants** after
`elsx_saas` is installed. It is a registry and deployment-control surface, not a
one-click database mutation tool.

Use the SaaS admin console to manage:

- Tenant name, legal name, admin email, domain, and planned database name.
- Plan, max users, storage quota, and enabled modules.
- Production safety checklist: encrypted backup, database created, filestore
  present, modules upgraded, webhook checked.
- Tenant lifecycle: draft, provision requested, provisioning, active,
  suspended, archived.
- The generated deployment plan for the server operator.

The SaaS admin console deliberately does not:

- Create/drop PostgreSQL databases directly from the browser.
- Delete filestores.
- Copy live WhatsApp credentials between tenants.
- Install/uninstall protected modules without the controlled deployment path.
- Change existing FiberaFRP production records, users, messages, invoices, or
  CRM records.

Production updates should use:

```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE
bash deploy/safe_production_update.sh FiberaFRP_DB
```

The controlled script creates/verifies an encrypted backup, upgrades only the
requested modules, restarts Odoo/sidecar, and prints health checks. It never
runs `docker compose down -v` and never uninstalls modules.

To install an outside addon safely:

1. Copy the addon folder into `custom_addons`.
2. Confirm its manifest dependencies exist and it supports this Odoo 19 build.
3. Run the backup-protected update with explicit module names:

```bash
EXTRA_INSTALL_MODULES=my_new_module EXTRA_UPGRADE_MODULES=my_new_module bash deploy/safe_production_update.sh FiberaFRP_DB
```

The module guard does not block normal installs. It blocks protected uninstalls
and any install can still fail if the outside addon has incompatible Python,
missing dependencies, broken XML inheritance, unsupported assets, or a module
technical name that Odoo cannot find in the addon path.

For a real multi-tenant SaaS rollout, use one database per tenant or a clearly
designed tenant-isolation module after separate staging tests. Do not retrofit
tenant isolation directly into the live FiberaFRP production database.

Recommended SaaS model:

1. Keep `FiberaFRP_DB` as the live production tenant.
2. Create every new client as a separate database from `/web/database/manager`
   or by encrypted restore.
3. Register that client in **ELSx SaaS Admin > Tenants**.
4. Run the generated deployment plan after backup.
5. Configure WhatsApp/Tally credentials per tenant only when intentionally
   approved.
6. Keep face attendance disabled until each tenant has consent, enrollment, and
   staging tests.
