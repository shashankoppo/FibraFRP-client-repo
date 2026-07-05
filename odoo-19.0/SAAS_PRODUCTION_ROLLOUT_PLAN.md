# ELSxGlobal SaaS Production Rollout Plan

This plan is intentionally production-safe. It moves the platform toward a real
multi-tenant SaaS engine while keeping existing client databases, WhatsApp
Marketing, CRM, invoices, Tally, attendance, and filestore data untouched unless
an administrator explicitly runs a reviewed backup-first deployment command.

## Current Safe Baseline

- One Docker-based application stack runs Odoo, PostgreSQL, WhatsApp sidecar, and optional face sidecar.
- Existing production database such as `FiberaFRP_DB` remains the source of client truth.
- `elsx_saas` currently acts as a governance console: tenant registry, module requests, billing records, health records, usage records, and deployment plans.
- Browser actions in the SaaS console do not create, drop, clone, or modify client databases.
- Existing WhatsApp Marketing works through isolated records inside the selected database and webhook routing that includes a database selector or primary webhook flag.

## Non-Negotiable Production Rules

- Never run `docker compose down -v`.
- Never delete Docker volumes during deployment.
- Never upgrade every database unless tenant-wide work is intentional.
- Always create an encrypted backup before module upgrade.
- Keep WhatsApp Marketing and its dependencies untouched unless fixing a confirmed WhatsApp bug.
- Keep live Meta tokens, customer data, invoices, chats, and filestore outside GitHub.

## Phase 1: Read-Only Readiness Audit

Use the audit script before rollout:

```bash
bash deploy/saas_readiness_audit.sh
```

It checks repository state, compose health, runtime limits, database inventory,
critical module states, SaaS registry presence, and WhatsApp webhook isolation
signals. It writes a text report under `reports/`.

For the active client only:

```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo && \
export BACKUP_PASSPHRASE && \
TARGET_DBS=FiberaFRP_DB CONFIRM_TARGET_DBS=YES \
bash deploy/safe_update_all_dbs.sh
```

## Phase 2: Master Admin Instance

Create a separate master database and domain for SaaS administration. The master database stores tenant registry, subscription plans, provisioning requests, module requests, telemetry snapshots, backup metadata, and billing state. It must not store tenant operational data such as contacts, invoices, chats, Meta tokens, or attendance records.

## Phase 3: Template Database

Create a base template database with only safe default configuration: CRM, Contacts, Sales/Invoicing as required, WhatsApp Marketing installed without live credentials, Face Attendance installed but disabled, ELSxGlobal branding/client restrictions, and SaaS-safe module protections.

The template database must not contain live client credentials, customer data, WhatsApp messages, invoices, or production filestore.

## Phase 4: Provisioning Engine

Provisioning should be script/API driven, not a direct destructive browser action. The flow should be:

1. SaaS admin approves tenant.
2. Encrypted backup exists for production systems.
3. PostgreSQL clones the template database.
4. Filestore template is copied.
5. Odoo XML-RPC configures admin user, company name, `web.base.url`, selected modules, quotas, and disabled-by-default WhatsApp/face credentials.
6. Tenant is marked active only after health checks pass.

## Phase 5: Domain Routing And Isolation

The objective requires strict domain-to-database isolation. Do not enable a hard `dbfilter` until routing is ready.

Required future artifacts:

- tenant domain map,
- reverse proxy map,
- generated `dbfilter` strategy,
- SSL certificate automation,
- tenant-specific `web.base.url`,
- webhook endpoint mapping.

Current config keeps DB manager flexible. SaaS production isolation should replace that with a controlled mapping after testing.

## Phase 6: WhatsApp Multi-Tenant Routing

Each tenant database must keep its own WhatsApp account records, Meta phone number ID, WABA ID, webhook verify token, app secret, templates, chats/messages, and API logs.

Webhook routing must resolve the tenant without leaking data between databases. For production SaaS this should be domain/path mapped at the reverse proxy and then explicitly opened in Odoo.

## Phase 7: Billing, Quotas, And Lifecycle

Billing should support weekly, monthly, yearly, 3-year, 5-year, and custom contracts.

Lifecycle actions must be soft-first: trial, active, grace, suspended, archived. Hard delete should require backup verification and explicit technical approval.

## Phase 8: Monitoring And Scale

Add central telemetry for database size, filestore size, active users, WhatsApp volume, invoice count, attendance usage, cron status, sidecar health, and slow/error logs. Use this to decide when to split tenants across remote servers or versions.

## RAM Planning

The Docker stack is heavier than a helper-script LXC because it includes PostgreSQL, Odoo, sidecars, logs, registry cache, and Docker overhead. On a 4 GB VM, high memory usage is expected. For production SaaS with WhatsApp and Website, 8 GB RAM is the practical minimum before adding more tenants.