# ELSxGlobal SaaS Implementation Manual

## 1. Purpose

This manual explains how to use, test, deploy, and extend the ELSxGlobal SaaS implementation safely.
It is written for testers, technicians, deployment engineers, and administrators who must protect existing client databases, CRM, WhatsApp Marketing, invoices, attendance, Tally, website, and filestore data while moving the platform toward a real multi-tenant SaaS system.

The current production rule is simple:

- Client data stays inside PostgreSQL databases and filestore volumes.
- GitHub stores code, scripts, and documentation only.
- Backups must be encrypted before any production module upgrade.
- Updates should target the intended database unless a deliberate all-database upgrade is approved.
- WhatsApp Marketing and CRM integrations must remain working after every update.

## 2. Current SaaS Reality

The current SaaS module is a governance and management layer. It provides records, menus, APIs, views, and safety controls for tenant management, billing plans, usage tracking, module requests, support tickets, upgrade logs, and deployment planning.

It is not yet a fully automatic tenant provisioner that safely creates domains, clones template databases, configures reverse proxy routes, assigns SSL certificates, configures SMTP, and deploys isolated client instances end to end without technician review.

This distinction matters. Testers must not mark provisioning as complete unless the full provisioning flow is implemented and verified on a staging server.

## 3. High-Level Architecture

### 3.1 Runtime Stack

The Docker stack normally contains:

| Component | Purpose |
|---|---|
| Odoo application container | Runs the main business application and custom addons. |
| PostgreSQL container | Stores all databases, including production client databases. |
| WhatsApp sidecar | Optional realtime/socket support for WhatsApp UI/events. |
| Face sidecar | Optional face recognition service for face attendance. |
| Reverse proxy/tunnel | Public HTTPS routing for production domains and webhooks. |

### 3.2 Database Model

The intended SaaS model is:

| Database Type | Purpose |
|---|---|
| Master Admin DB | SaaS operator console, tenant registry, plans, usage, billing, support, provisioning records. |
| Client DB | Each customer tenant's operational data, users, CRM, invoices, WhatsApp, attendance, website, files. |
| Template DB | Clean base database used to create new tenants. It must not contain live tokens or customer data. |
| Backup DB or copy | Temporary restore/test copy for verification only. |

Existing production database example:

```text
FiberaFRP_DB
```

The production database name may differ on another server. Always confirm before running scripts.

## 4. Safety Rules For Production

Follow these rules every time:

1. Do not run `docker compose down -v`.
2. Do not delete Docker volumes.
3. Do not restore over a live database unless a rollback is explicitly approved.
4. Do not run all-database updates when only one client DB needs an update.
5. Do not store client backups, tokens, `.env`, database dumps, or filestore archives in GitHub.
6. Do not uninstall protected business modules from production.
7. Do not change WhatsApp webhook routing or Meta credentials during unrelated SaaS work.
8. Do not modify live templates, campaigns, invoices, flows, contacts, or records from scripts unless the script is specifically designed and approved for that migration.
9. Run tests on a copy database before production when a change touches models, views, module security, deployment scripts, or frontend assets.
10. Keep manual verification notes after every deployment.

## 5. Main Files And Scripts

### 5.1 SaaS Addon

```text
custom_addons/elsx_saas/
```

Important files:

| Path | Purpose |
|---|---|
| `__manifest__.py` | Module metadata and dependencies. |
| `models/saas_tenant.py` | Tenant records and lifecycle fields. |
| `models/saas_billing.py` | Billing plans, invoices, subscription style records. |
| `models/saas_usage_tracking.py` | Usage, quotas, resource tracking. |
| `models/saas_api_token.py` | API token support. |
| `models/saas_support_ticket.py` | Support ticket model. |
| `models/upgrade_log.py` | Upgrade and deployment logs. |
| `controllers/saas_api.py` | API endpoints for SaaS operations. |
| `views/saas_tenant_views.xml` | Tenant list, form, actions, menus. |
| `views/saas_advanced_views.xml` | Advanced SaaS views. |
| `views/saas_enterprise_views.xml` | Console-style management views. |
| `security/saas_security.xml` | Security groups and access control. |
| `security/ir.model.access.csv` | Model permissions. |
| `static/src/css/saas_admin.css` | SaaS console styling. |

### 5.2 Deployment Scripts

```text
deploy/
```

Important scripts:

| Script | Purpose |
|---|---|
| `safe_production_update.sh` | Safer single-database production module update. |
| `safe_update_all_dbs.sh` | Multi-database updater. Supports targeted DB mode with `TARGET_DBS`. |
| `saas_readiness_audit.sh` | Read-only audit for SaaS readiness and critical module state. |
| `export_live_encrypted_backup.sh` | Creates encrypted portable DB plus filestore backup. |
| `restore_live_encrypted_backup.sh` | Restores encrypted backup when explicitly confirmed. |
| `upgrade_module_all_dbs.sh` | Upgrades one module across databases. Use carefully. |
| `diagnose_live_whatsapp.sh` | WhatsApp production diagnostic helper. |
| `configure_live_db.sh` | Live DB configuration and repair helper. |
| `verify_ubuntu_docker.sh` | Ubuntu Docker environment check. |
| `safe_update_windows.ps1` | Windows helper script. |

## 6. Accessing The SaaS Admin Console

### 6.1 Menu Path

After the SaaS module is installed and upgraded:

```text
ELSx SaaS Control
```

Depending on user access and menu configuration, it may appear in the app switcher or main menu.

### 6.2 Required User Access

Only trusted platform administrators should access SaaS management.

Recommended groups:

| User Type | Access |
|---|---|
| Normal client user | No SaaS admin access. |
| Client admin | No master SaaS admin access unless explicitly required. |
| Support technician | Read or limited operational access. |
| SaaS admin | Tenant, billing, support, and health management. |
| System owner | Full technical access. |

### 6.3 If The Menu Is Missing

1. Confirm the module is installed:

```bash
docker exec -it odoo_app python3 /opt/odoo/odoo-bin shell -c /etc/odoo/odoo.conf -d FiberaFRP_DB
```

Then inspect module state from UI or database.

2. Confirm the user has the SaaS security group.
3. Clear browser cache or open in private/incognito mode.
4. Restart only Odoo if assets are stale:

```bash
docker restart odoo_app
```

5. Check logs:

```bash
docker logs --tail 250 odoo_app
```


## 6.4 SaaS Command Center

After the latest SaaS upgrade, the first screen for SaaS administrators should be:

```text
ELSx SaaS Control > Command Center
```

Use this page as the operator dashboard. It is intentionally read-mostly and does not create, clone, delete, or modify tenant databases.

### 6.4.1 Command Center Areas

| Area | What It Shows | What To Do |
|---|---|---|
| Tenant Operations | Total, active, warning, and suspended tenants. | Open warning tenants first and review health notes. |
| Billing Cycle | MRR, ARR, open invoices, and overdue invoices. | Open billing cycles and follow up on overdue accounts. |
| Apps / Modules | Pending module requests and high-risk requests. | Review dependency/staging/backup checks before approval. |
| Support | Open tickets and breached tickets. | Prioritize breached tickets and production blockers. |
| CIA Triad | Confidentiality, integrity, and availability health. | Treat warning or danger status as a release blocker. |
| Operator Guidance | Next safe action for the platform operator. | Follow guidance before touching production. |

### 6.4.2 Command Center Safety

The dashboard reads from SaaS governance tables only. It does not touch client CRM records, WhatsApp messages, invoices, attendance entries, templates, campaigns, flows, filestore, Meta credentials, Tally settings, or production tenant databases.

If the dashboard is empty, create or sync SaaS governance records first. Do not assume an empty dashboard means the production system has no clients.

### 6.4.3 Who Should See It

Only users in the SaaS administrator group should see the command center. Normal client users should not see SaaS tenant management, billing governance, module requests, or infrastructure health.

## 7. Local Docker Desktop Testing

Use Docker Desktop testing before touching production.

### 7.1 Start The Stack

From repo root:

```bash
cd ~/Desktop/FiberaFRP/FibraFRP-client-repo/odoo-19.0
```

Then:

```bash
docker compose up -d --build
```

### 7.2 Confirm Containers

```bash
docker compose ps
```

Expected:

| Container | Expected State |
|---|---|
| `odoo_app` | Up / healthy |
| `odoo-190-db-1` | Up / healthy |
| `whatsapp_sidecar` | Up if configured; otherwise investigate if WhatsApp realtime is required |

### 7.3 Open Local System

```text
http://localhost:8069
```

If no database is selected, use:

```text
http://localhost:8069/web/database/selector
```

or include DB in URL for public routes when needed:

```text
http://localhost:8069/odoo?db=FiberaFRP_DB
```

### 7.4 Upgrade SaaS Module On Local Test DB

Use a test/copy database first:

```bash
docker exec odoo_app python3 /opt/odoo/odoo-bin -c /etc/odoo/odoo.conf -d FiberaFRP_DB -u elsx_saas --stop-after-init
```

Restart:

```bash
docker restart odoo_app
```

### 7.5 Read Logs

```bash
docker logs --tail 250 odoo_app
```

Search for:

```text
Traceback
RPC_ERROR
ParseError
OwlError
ERROR
CRITICAL
```

## 8. Read-Only SaaS Readiness Audit

Use this before deployment or before enabling SaaS features.

```bash
bash deploy/saas_readiness_audit.sh
```

The script is read-only. It checks:

- Git state.
- Docker Compose validity.
- Running containers.
- Runtime limits.
- DB list.
- Critical module states in each DB.
- WhatsApp account table presence.
- WhatsApp account count.
- Primary webhook flags.
- SaaS tenant and billing records.
- Missing implementation warnings.

Reports are written under:

```text
reports/
```

Reports must not be committed to GitHub.

## 9. Production Update Flow

### 9.1 Recommended Active Client Only Command

Use this when only the live client DB should be updated:

```bash
cd ~/Desktop/FiberaFRP/FibraFRP-client-repo/odoo-19.0 && \
git pull origin main && \
chmod +x entrypoint.sh deploy/*.sh && \
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo && \
export BACKUP_PASSPHRASE && \
TARGET_DBS=FiberaFRP_DB CONFIRM_TARGET_DBS=YES \
bash deploy/safe_update_all_dbs.sh && \
docker compose ps && \
docker logs --tail 250 odoo_app
```

Change `FiberaFRP_DB` only if the live database name is different.

### 9.2 Why Not Always Use All-DB Update

All-DB update can be slow because it backs up and upgrades every application database.
It can consume high RAM and CPU on a 4 GB VM.
Use all-DB update only when intentionally upgrading every tenant.

### 9.3 All-DB Update Command

Use only after approval:

```bash
cd ~/Desktop/FiberaFRP/FibraFRP-client-repo/odoo-19.0 && \
git pull origin main && \
chmod +x entrypoint.sh deploy/*.sh && \
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo && \
export BACKUP_PASSPHRASE && \
CONFIRM_ALL_DBS=YES bash deploy/safe_update_all_dbs.sh && \
docker compose ps && \
docker logs --tail 250 odoo_app
```

## 10. Encrypted Backup Flow

### 10.1 Create Backup

```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo && \
export BACKUP_PASSPHRASE && \
bash deploy/export_live_encrypted_backup.sh FiberaFRP_DB
```

Backup output goes to:

```text
secure_backups/
```

Do not push this folder to GitHub.

### 10.2 Restore Backup

Restore only when explicitly approved:

```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo && \
export BACKUP_PASSPHRASE && \
CONFIRM_RESTORE=YES bash deploy/restore_live_encrypted_backup.sh /path/to/backup.enc FiberaFRP_DB
```

### 10.3 Restore Config Too

Only if you intentionally want to restore `.env` and config files:

```bash
RESTORE_CONFIG=YES CONFIRM_RESTORE=YES bash deploy/restore_live_encrypted_backup.sh /path/to/backup.enc FiberaFRP_DB
```

## 11. Tenant Lifecycle Guide

### 11.1 New Tenant Request

1. Create a SaaS tenant record.
2. Fill company name, contact, email, domain, plan, trial dates, and required modules.
3. Set the status to draft or trial.
4. Do not activate until provisioning checks pass.

### 11.2 Tenant Review

Check:

- Owner details.
- Billing plan.
- Contract terms.
- Domain/subdomain.
- Required modules.
- Data residency/backup policy.
- WhatsApp requirement.
- Tally requirement.
- Website requirement.
- Attendance requirement.
- Face attendance requirement.

### 11.3 Tenant Activation

Current safe activation is manual or technician-assisted.

A complete activation should eventually perform:

1. Clone template DB.
2. Copy template filestore.
3. Set `web.base.url`.
4. Create tenant admin.
5. Install allowed modules.
6. Apply plan limits.
7. Configure SMTP.
8. Configure domain/proxy/SSL.
9. Confirm login.
10. Mark tenant active only after tests pass.

### 11.4 Tenant Suspension

Suspension must be soft-first.

Allowed safe behavior:

- Mark tenant suspended.
- Disable login or restrict access if implemented.
- Keep database and filestore intact.
- Keep backups available.
- Never delete tenant DB during suspension.

### 11.5 Tenant Archive

Archiving should keep data restorable.

Recommended behavior:

- Mark tenant archived.
- Stop billing or mark contract ended.
- Export encrypted backup.
- Disable public routes if implemented.
- Keep database untouched unless technical deletion is separately approved.

## 12. Billing And Plans

### 12.1 Required Billing Cycles

The SaaS system should support:

- Weekly.
- Monthly.
- Yearly.
- 3-year.
- 5-year.
- Custom contract.

### 12.2 Plan Fields To Verify

For each billing plan, check:

- Plan name.
- Price.
- Billing cycle.
- User limit.
- Storage limit.
- WhatsApp message quota.
- Website quota.
- Email/SMS quota if applicable.
- Backup retention.
- Allowed modules.
- Trial length.
- Support level.

### 12.3 Missing Billing Implementation

Still required for full SaaS:

- Payment gateway integration with Stripe or PayPal.
- Invoice generation per billing cycle.
- Payment failure handling.
- Grace period automation.
- Subscription renewal automation.
- Usage-based overage calculation.
- Tenant lock/suspension automation.
- Billing email notifications.


### 12.4 Billing Cycle Operating Workflow

Use this workflow for every tenant billing period:

1. Open **ELSx SaaS Control > Command Center**.
2. Review **MRR**, **ARR**, **Open Invoices**, and **Overdue Invoices**.
3. Open **Billing Cycles**.
4. Filter by payment status: draft, sent, partial, overdue, paid, or cancelled.
5. Confirm tenant, plan, cycle date, due date, amount, and currency.
6. For overdue cycles, create a support or accounts follow-up note.
7. Do not suspend a tenant automatically unless the suspension policy and grace period are configured and approved.
8. After payment confirmation, mark the cycle paid or reconcile through the configured accounting workflow.
9. Reopen the Command Center and confirm the overdue count changed.

### 12.5 Billing Safety Rules

- Billing records are governance records; accounting invoices remain in the accounting module.
- Do not delete billing plans once used by a tenant. Archive or stop using the plan instead.
- Do not hard-delete billing add-ons or plan limits in production.
- Do not run billing automation on live tenants until tested on a copy database.
- Keep gateway secrets outside GitHub and outside screenshots.

## 13. Module Governance

### 13.1 Protected Modules

These modules should be protected from accidental uninstall in production:

- Base/web/security modules.
- Contacts.
- CRM.
- Sales.
- Accounting/Invoicing.
- WhatsApp Marketing.
- WhatsApp dependencies.
- Attendance.
- Attendance Tracking.
- Tally integration.
- Client Restrictions.
- SaaS.
- Face Attendance if deployed.

### 13.2 Safe Module Change Flow

1. User requests module install, upgrade, or uninstall.
2. System checks protected module rules.
3. Technician confirms dependencies.
4. Backup is created.
5. Change is tested on staging/copy DB.
6. Production update runs only after approval.
7. Logs are checked.
8. User-facing menus are verified.

### 13.3 Third-Party Module Install Checklist

Before installing any third-party module:

- Confirm it supports this Odoo version/build.
- Confirm it does not override core views dangerously.
- Confirm manifest dependencies exist.
- Confirm license/compliance is acceptable.
- Confirm Python package dependencies are included in Docker image if needed.
- Test install on a copy DB.
- Open Settings, Apps, CRM, WhatsApp, Invoicing, Attendance after install.
- Check logs for view parse errors and missing fields.


### 13.4 Apps And Module Governance In SaaS

The Apps module should not be treated as a free-for-all in production. SaaS administrators should use the safe module-change process instead of allowing casual install/uninstall from the Apps screen.

Recommended flow:

1. Open **Safe Module Change** or the SaaS module request list.
2. Create a module request with module name, business reason, tenant/database, requester, and risk level.
3. Check whether the module is protected, critical, third-party, or dependency-heavy.
4. Confirm an encrypted backup exists.
5. Test install or upgrade on a copy database.
6. Verify Settings, CRM, WhatsApp Marketing, Invoicing, Attendance, Website, and Tally after the test.
7. Approve production only after the copy database passes.
8. Use the safe deployment script to update the target DB.
9. Record the result in the module request or upgrade log.

### 13.5 Critical Module Protection

Critical modules should stay installed and operational because removing them can break client workflows or data links.

| Module Area | Why It Is Protected |
|---|---|
| CRM / Contacts | WhatsApp chats, leads, quotes, and customers depend on partner/lead links. |
| Invoicing / Accounting | Existing invoices, payments, reports, and WhatsApp invoice actions depend on it. |
| WhatsApp Marketing | Webhooks, templates, campaigns, chats, flows, and CRM handoff depend on it. |
| Attendance / Face Attendance | Employee attendance and audit workflows depend on it. |
| Tally Integration | Invoice/export workflows depend on configured gateway/export logic. |
| SaaS / Client Restrictions | Production governance, menu control, and module safety depend on it. |

Normal UI should archive, deactivate, or request review instead of hard-deleting protected configuration.

## 14. WhatsApp And CRM Protection

### 14.1 What Must Stay Intact

- WhatsApp account records.
- Phone Number ID.
- WABA ID.
- Access token.
- Webhook verify token.
- App secret.
- Templates.
- Campaigns.
- Flows.
- Message history.
- Contacts/partners.
- CRM leads/opportunities.
- Invoice links.
- Campaign reply rules.

### 14.2 Before Any SaaS Update

Check:

1. Team Inbox opens.
2. Active account is connected/verified.
3. Recent inbound messages exist.
4. Templates screen opens.
5. Campaigns screen opens.
6. CRM lead links open.
7. Invoice links open.
8. No webhook tracebacks in logs.

### 14.3 After Any SaaS Update

Test:

1. Receive one inbound WhatsApp message.
2. Open Team Inbox.
3. Open the related contact.
4. Open or create a lead.
5. Open templates.
6. Preview a template.
7. Open campaigns.
8. Confirm no RPC/Owl errors.

## 15. Domain, Proxy, And Database Isolation

### 15.1 Current Status

Current deployment allows flexible database manager usage. This is useful during development and recovery but is not the final SaaS isolation model.

### 15.2 Required SaaS Isolation

For production SaaS, each tenant should resolve by domain or subdomain:

```text
tenant-a.example.com -> tenant_a_db
tenant-b.example.com -> tenant_b_db
```

### 15.3 Missing Implementation

Still required:

- Domain registry model.
- Generated reverse proxy map.
- SSL automation.
- Per-tenant `web.base.url` automation.
- Strict dbfilter/domain mapping.
- Webhook tenant resolver.
- Safe domain validation.
- Customer custom domain setup wizard.

## 16. Template Database Guide

### 16.1 Template DB Must Include

- Base configuration.
- Branding.
- Contacts.
- CRM if part of all plans.
- Invoicing if part of all plans.
- Website if part of all plans.
- WhatsApp Marketing installed but not configured with live credentials.
- Tally installed but not configured with live credentials.
- Attendance installed if needed.
- Face Attendance disabled by default.
- Safe default admin user reset during provisioning.

### 16.2 Template DB Must Not Include

- Live customer records.
- Live invoices.
- Live WhatsApp chats/messages.
- Meta access tokens.
- App secrets.
- Tally production gateway credentials.
- Employee biometric data.
- Production filestore.

## 17. Tester Manual

### 17.1 General Login Test

1. Open system URL.
2. Select correct DB if prompted.
3. Log in as administrator or test user.
4. Confirm app menu opens.
5. Confirm Settings opens for admin.
6. Confirm no blank white screen.
7. Check browser console if UI fails.

### 17.2 SaaS Console Test

1. Open ELSx SaaS Control.
2. Open Tenants.
3. Create a test tenant record only if using a staging DB.
4. Open billing plans.
5. Open usage records.
6. Open support tickets.
7. Open upgrade logs.
8. Confirm buttons do not perform destructive database operations without confirmation.

### 17.3 WhatsApp Regression Test

1. Open WhatsApp Marketing.
2. Open Team Inbox.
3. Select existing chat.
4. Send safe internal test message if allowed.
5. Receive inbound test message.
6. Open template list.
7. Preview template.
8. Open campaigns.
9. Do not send live campaign unless approved.
10. Check logs.

### 17.4 CRM Regression Test

1. Open CRM.
2. Open leads/opportunities.
3. Open a WhatsApp-created lead.
4. Confirm partner link opens.
5. Confirm activity/chatter loads.
6. Confirm no access errors.

### 17.5 Invoicing Regression Test

1. Open Invoicing.
2. Open customer invoices.
3. Open one existing invoice.
4. Confirm PDF/report action works if configured.
5. Confirm WhatsApp invoice action still appears if module provides it.
6. Do not post or send test invoices in live production unless approved.

### 17.6 Attendance Regression Test

1. Open Attendances.
2. Open attendance list.
3. Open grouped/list views.
4. Confirm no timezone error.
5. Test normal attendance check-in/out only with a test employee.
6. If face attendance is installed, confirm it is disabled unless explicitly enabled.

### 17.7 Website Regression Test

1. Open Website.
2. Open homepage.
3. Open editor.
4. Make no live change unless approved.
5. Confirm AI Website Builder drafts do not publish automatically.

## 18. Technician Deployment Checklist

Before deployment:

- Confirm branch and commit.
- Confirm target DB.
- Confirm free disk space.
- Confirm Docker containers are healthy.
- Confirm backup passphrase is available.
- Confirm no uncommitted production changes unless reviewed.
- Confirm client active hours and maintenance window.
- Confirm rollback file path.

During deployment:

- Pull code.
- Run targeted backup/update.
- Restart Odoo only if needed.
- Watch logs.
- Keep browser smoke test ready.

After deployment:

- Login.
- Open Settings.
- Open SaaS console.
- Open WhatsApp Inbox.
- Receive inbound WhatsApp test.
- Open CRM.
- Open invoices.
- Open attendance.
- Open website.
- Save deployment notes.


## 18.1 CIA Triad Checklist For SaaS Operators

Use this checklist before approving production changes.

### Confidentiality

1. Confirm normal client users cannot open SaaS tenant management.
2. Confirm Meta tokens, Tally credentials, database backups, and `.env` files are not in GitHub.
3. Confirm each tenant database has its own operational records and credentials.
4. Confirm backup files are encrypted before transfer.
5. Confirm screenshots shared outside the team do not show secrets, tokens, customer phones, or invoices.

### Integrity

1. Confirm Git diff contains only expected files.
2. Confirm no script deletes or overwrites tenant databases automatically.
3. Confirm protected modules cannot be casually uninstalled.
4. Confirm module upgrades happen through backup-first scripts.
5. Confirm CRM, WhatsApp, invoices, and attendance still open after update.

### Availability

1. Confirm `odoo_app` and PostgreSQL containers are healthy.
2. Confirm WhatsApp sidecar is healthy if realtime socket features are required.
3. Confirm `/web/health` returns healthy status.
4. Confirm there is enough disk space for backup and filestore.
5. Confirm RAM pressure is acceptable before running all-database backup or build.
6. Confirm rollback backup exists before production update.

If any CIA item fails, stop and fix that item before continuing.

## 19. Missing Ecosystem And Implementation Gaps

This section is important. These items are not complete until implemented and tested.

### 19.1 Master Admin Separation

Missing or incomplete:

- Dedicated master admin DB setup guide.
- Tenant registry hosted only in master DB.
- Prevention of client admins accessing SaaS master console.
- Central operator dashboard across all tenant DBs.

### 19.2 Tenant Provisioning Engine

Missing or incomplete:

- One-click safe tenant provisioning.
- Template DB clone automation.
- Filestore clone automation.
- Per-tenant admin creation.
- Per-tenant domain setup.
- Per-tenant SSL setup.
- Per-tenant SMTP setup.
- Health-check based activation.
- Provisioning rollback.

### 19.3 Tenant Database Isolation

Missing or incomplete:

- Strict dbfilter strategy.
- Domain to DB mapping.
- Reverse proxy map generator.
- Multi-server tenant routing.
- Tenant lockout after suspension.

### 19.4 WhatsApp Multi-Tenant SaaS Routing

Missing or incomplete:

- Central webhook tenant resolver.
- Per-tenant webhook URL generator.
- Per-tenant Meta app/account mapping.
- Conflict prevention for duplicate phone number IDs across DBs.
- Cross-DB webhook health dashboard.
- Tenant-safe incoming message isolation tests.

### 19.5 Billing Automation

Missing or incomplete:

- Stripe integration.
- PayPal integration.
- Automatic invoice creation.
- Payment status webhook.
- Grace period logic.
- Auto-suspend after overdue period.
- Renewal reminders.
- Plan upgrade/downgrade workflow.

### 19.6 Usage Metering And Quotas

Missing or incomplete:

- Active user counting.
- Database size tracking.
- Filestore size tracking.
- WhatsApp message volume tracking.
- Campaign send quota.
- Website page quota.
- API usage quota.
- Warning thresholds.
- Hard enforcement rules.

### 19.7 Backup Portal

Missing or incomplete:

- Tenant-visible backup list.
- Admin restore request flow.
- Backup retention policy UI.
- Restore to staging/copy DB.
- Backup integrity verification.

### 19.8 Remote Server And Version Management

Missing or incomplete:

- Remote server registry.
- Tenant placement rules.
- Version/channel management.
- Staging branch deployment.
- Canary tenant deployment.
- Blue/green upgrade flow.

### 19.9 SaaS Admin UX

Missing or incomplete:

- WhatsApp health cards.
- Server resource cards.
- Action confirmation wizards.
- Better empty states.
- Audit trail timeline.
- Role-specific navigation.

Recently added:

- Command Center dashboard for SaaS administrators.
- Tenant, billing, support, module request, and CIA triad summary cards.
- Read-mostly action buttons that open related SaaS governance records without touching tenant databases.

### 19.10 Security And Compliance

Missing or incomplete:

- Full tenant audit log.
- Admin action approval policy.
- Secrets rotation workflow.
- Data export request workflow.
- Data deletion workflow with legal approval.
- Biometric data consent workflow for face attendance.
- API token scope restrictions.

## 20. Troubleshooting

### 20.1 Settings Page Is Blank

Check:

```bash
docker logs --tail 250 odoo_app
```

Look for:

```text
ParseError
View error
Field does not exist
RPC_ERROR
OwlError
```

Likely causes:

- Broken settings view inheritance.
- Missing model field after module code update without DB upgrade.
- Bad XML in custom module.
- Asset cache mismatch.
- User missing required group.

Fix path:

1. Upgrade the affected module on a test DB.
2. If fixed, upgrade target production DB with backup-first script.
3. Restart Odoo.
4. Clear browser cache.

### 20.2 App Module Is Visible

Possible causes:

- User has system/admin access.
- Menu restrictions module not upgraded.
- Developer mode or direct URL access.
- SaaS policy intentionally allows app management for system owner.

Check:

- `elsx_client_restrictions` installed/upgraded.
- User groups.
- Menu restrictions XML.
- Safe Module Change menu.

### 20.3 WhatsApp Sidecar Restarting

Check:

```bash
docker logs --tail 250 whatsapp_sidecar
```

Common causes:

- Missing sidecar environment variable.
- Node dependency issue.
- Odoo URL unreachable from sidecar.
- Port conflict.
- Socket configuration mismatch.

If realtime sidecar is optional, Team Inbox may still work through normal Odoo requests. Confirm before restarting production.

### 20.4 Deployment Taking Too Long

Common causes:

- All DB backup instead of target DB backup.
- Large filestore.
- First-time Docker build.
- Low RAM.
- Multiple sidecars.
- PostgreSQL dump compression.

Use target DB mode:

```bash
TARGET_DBS=FiberaFRP_DB CONFIRM_TARGET_DBS=YES bash deploy/safe_update_all_dbs.sh
```

### 20.5 External Modules Not Installing

Check:

- Manifest syntax.
- Missing dependencies.
- Python package dependency not in Docker image.
- XML view references to missing fields/templates.
- Module conflicts with custom branding/client restrictions.
- Access CSV model IDs.

Install first on a copy DB.

## 21. Production Sign-Off Checklist

Do not sign off until all required items pass.

| Area | Pass Criteria |
|---|---|
| Login | Admin and normal user login works. |
| Settings | Settings opens, no blank screen. |
| SaaS | SaaS console opens for authorized admin only. |
| WhatsApp | Team Inbox opens and inbound test message arrives. |
| CRM | Leads open and WhatsApp-created leads are intact. |
| Invoices | Invoicing opens and existing invoices are present. |
| Campaigns | Campaign screens open without RPC errors. |
| Templates | Template preview opens without crashing. |
| Attendance | Attendance views open without timezone/RPC errors. |
| Website | Website opens and editor opens. |
| Logs | No new Traceback/RPC/Owl/View errors. |
| Backup | Encrypted backup exists and path is recorded. |
| Rollback | Restore command is known and tested on non-production if possible. |

## 22. Technician Notes Template

Use this after every deployment:

```text
Date/time:
Server:
Branch/commit:
Target DB:
Backup file:
Modules upgraded:
Commands run:
Smoke tests passed:
Issues found:
Rollback needed: yes/no
Technician:
```

## 23. Final Operating Principle

The SaaS system must become powerful without becoming dangerous.

Every new feature should follow this rule:

```text
Draft first, backup first, test first, activate manually, then automate only after proven safe.
```
