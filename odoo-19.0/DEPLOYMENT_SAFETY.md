# WhatsApp Hardening and Client-Safe Deployment

For the short operator instructions, use [DEPLOYMENT_QUICKSTART.md](DEPLOYMENT_QUICKSTART.md).

## Release Status

This revision is a release candidate, not a production certification. It changes access rules,
consent handling, delivery, and deployment orchestration. Complete the rollout gates below before
deploying a client. Syntax checks or a successful image build alone do not establish data safety.
See [validation results](WHATSAPP_HARDENING_VALIDATION.md) for completed checks and remaining work.

Production always targets the existing database configured on that VPS. No replacement production
database is created. A restore rehearsal uses a separate, isolated test environment, never a second
live client database on the production service.

## Commands

Run from `odoo-19.0` after the release gates and one-time configuration:

```bash
# Existing production client, configured on this VPS
git pull --ff-only origin main && docker compose run --rm --build deploy-prod

# Separate, brand-new Compose environment only
git pull --ff-only origin main && docker compose run --rm --build deploy-new
```

The Compose job uses the revision already pulled/checked out and includes its own deployment
toolchain. It reuses the existing guards; see the quickstart for local socket permissions and path
requirements. The older host wrappers remain supported and perform their own pull unless CI or
`NO_PULL=YES` is set. The worktree must be clean; commit reviewed source changes and keep
VPS secrets in ignored files or injected CI environment variables. Never commit credentials.

An ordinary `docker compose up -d --build` starts rebuilt services; it does **not** upgrade database
schemas. Use the production command for installed module upgrades, including barcode changes.
Do not use `docker compose down -v`, delete volumes, restore over the client DB, or uninstall/reinstall
WhatsApp to repair a registry error.

### Existing Client Configuration

Provide through existing VPS/CI secret configuration, with no interactive prompts:

- `ODOO_AUTO_UPDATE_DB_NAME`: exact existing client database name. Despite its legacy name, this no
  longer enables startup upgrades. `LIVE_DB_NAME` is a compatibility alias; values must agree if both exist.
- `BACKUP_PASSPHRASE`: strong, separately retained backup encryption secret.
- `POSTGRES_USER` and `POSTGRES_PASSWORD`: existing database credentials, unchanged.
- Leave `INSTALL_MODULES`, `EXTRA_INSTALL_MODULES`, and `ODOO_AUTO_INSTALL_MODULES` unset;
  keep `ODOO_AUTO_ALLOW_INSTALL=NO`. Production rejects installation requests.
- Preserve the original Compose project name, PostgreSQL volume and Odoo filestore volume.
- Install Git and modern Docker Engine/Compose with `run --build`, `--wait` / JSON config support.
  Only the optional host wrappers also need Bash, Python 3.10+ and OpenSSL installed on the VPS.
- The Apps guard `elsx_client_restrictions` must already be installed. Missing guards block
  production deployment; they are never automatically installed by an update.

Missing, conflicting, placeholder and nonexistent database names fail without creation. The runner
also refuses an unpinned shared Odoo service containing another initialized database. Such a server
needs a reviewed multi-database rollout or service isolation; do not delete its other databases.

For the previously reported Fibera VPS, the target is `FiberaFRP_DB`. Keep its existing VPS/CI
settings and credentials; add `ODOO_AUTO_UPDATE_DB_NAME=FiberaFRP_DB` and provide
`BACKUP_PASSPHRASE` through the existing secret configuration. Do not replace the entire `.env` file.
The previously listed `YOUR_CLIENT_DB_NAME` must not be used as the target. If it is initialized and
the Odoo service is unpinned, the shared-database guard will stop deployment until routing is reviewed.

### First Upgrade From a Source Bind Mount

Older deployments mounted the repository into the running application. Pulling then changes live
Python/JS before a maintenance upgrade. The runner detects this and refuses to pull while it is running.
For this one-time transition, schedule downtime, take an independent database-plus-filestore backup,
stop Odoo, review/stash only the known local lockfile change, and pull the reviewed release. Then use
`NO_PULL=YES bash deploy-prod.sh`. Never discard all local changes or overwrite VPS configuration.

### New Environment Configuration

Use a separate Compose project and fresh volumes. Configure `NEW_DB_NAME`, an explicit comma-separated
`NEW_INSTALL_MODULES` list including `elsx_client_restrictions`, and `NEW_DB_ADMIN_PASSWORD` in VPS/CI secrets. `COUNTRY` and `ADMIN_LOGIN` default
to `IN` and `admin`. This path refuses an existing target database or existing Odoo service; dependencies
may be intentionally installed only here. Configure `ODOO_AUTO_UPDATE_DB_NAME` to that same database
from the start; `NEW_INSTALL_MODULES` is ignored on later production updates. Legacy `INSTALL_MODULES`
is still accepted for new installs only, but must be removed before production updates.

Keep production target variables unset during a new installation, or set both aliases to exactly
`NEW_DB_NAME`; a different production target is refused before starting services. New names use only
letters, numbers and underscores. Set a strong `POSTGRES_PASSWORD` for a fresh server. The installer
checks that every explicitly requested module really is installed and waits for application health
before reporting success. On failed startup it stops Odoo and retains the new database for diagnosis.

Example non-secret settings for a **separate fresh VPS**, with administrator/database passwords
provided through that VPS's secret configuration:

```dotenv
NEW_DB_NAME=FiberaFRP_New
ODOO_AUTO_UPDATE_DB_NAME=FiberaFRP_New
NEW_INSTALL_MODULES=sale_management,stock,account,crm,elsx_whatsapp_marketing,elsx_client_restrictions
```

This is an example initial app selection, not a production upgrade list. After the reviewed revision
has been pushed and release gates have passed, run `bash deploy-new.sh` from `odoo-19.0`. For later
updates, use `bash deploy-prod.sh` with the same configured target and backup secret.
Do not invoke new installation again to update existing data.

## What Production Does

1. Locks deployment, validates configuration and volume identities, builds and tags a candidate image.
2. Checks installed addon availability/dependencies/states, access mapping, Meta secrets and free space.
3. Stops Odoo and its sending cron workers. Other database connections must be stopped by the operator.
4. Takes a custom PostgreSQL dump and matching configured filestore archive while writes are stopped.
5. Encrypts the bundle with OpenSSL AES-256-CBC/PBKDF2 and verifies decryption, archive readability,
   dump catalogue and SHA-256. Retains configuration, image IDs and deployment metadata. This is not
   a substitute for a successful restoration rehearsal. Keep an off-VPS copy and its checksum securely.
6. Installs a database trigger protecting the original installed module set, then upgrades those modules.
   Module discovery can create uninstalled catalogue rows; automatic installation, removal, renaming
   or deletion of installed modules is rejected inside the upgrade transaction.
7. Checks module equality, registry, settings/inbox views, selected business-record fingerprints,
   financial amount fields, consent history, pending WhatsApp records and existing attachment hashes.
8. Starts the verified candidate and checks container health before clearing maintenance.

Existing schema migrations may legitimately recompute values. The fingerprint check deliberately
blocks unexpected changes instead of deciding they are harmless. It covers the tables/columns listed
in `deploy/integrity.py`, not every business field in every third-party addon. The local rehearsal caught
the rebranding addon's built-in bot rename (`OdooBot` to `System Bot`); a comparable client difference
requires explicit review. Do not regenerate the baseline simply to make verification pass.

The runner leaves an existing legacy WhatsApp relay running. Meta retries failed callbacks while Odoo
is stopped. External writers, reverse-proxy maintenance pages and direct application access restrictions
remain infrastructure responsibilities. Do not prune images or backups during rollout.

## Failure and Recovery

Failures after maintenance leave Odoo stopped, with the existing DB/volumes intact. Guard/maintenance
tables block an ordinary restart of an unfinished upgrade. A failed upgrade may have partially committed
schema changes; restarting an old image is not a general rollback strategy.

Use the exact backup directory printed by deployment in `RECOVERY_DIR`:

```bash
# Read-only metadata inspection
python3 deploy/client_recover.py inspect

# Retry checks/start only when the upgrade already completed
python3 deploy/client_recover.py verify-and-start

# After reviewing and checking out a corrective revision
python3 deploy/client_recover.py resume-upgrade
```

Recovery verifies the encrypted backup checksum, configured DB, original container volume identities
and candidate image. It never drops, replaces or automatically restores a database. A corrective
upgrade retains the original integrity baseline. Keep the candidate/recovery `ODOO_IMAGE` tag in VPS/CI
configuration if explicitly pinning images for later ordinary restarts; do not rebuild an old checkout
over that tag. With `ODOO_IMAGE` unset, the runner promotes the default `odoo-custom:19.0` startup alias
only after successful health checks. Candidate/recovery tags are built separately and retained.

If restoration is required, keep production stopped. Decrypt the bundle in a private isolated directory
using the retained passphrase, restore `database.dump` and the **matching** `filestore.tar` to an isolated
environment using the retained image, and verify it first. Production restoration requires a separately
approved operator procedure and an agreed recovery point. No destructive one-line restore is provided.

## WhatsApp Behavior

- ERP Bus carries inbox notifications, not bulk sends. PostgreSQL-backed direct/campaign/retry queues
  call Meta. Bus capacity is not a messages-per-second guarantee.
- Verified inbound Meta timestamps establish the 24-hour service window; replay cannot extend it.
  Legacy inbound creation dates remain a fallback. Service replies do not silently grant marketing consent.
- Marketing templates, including manually selected ones, require applicable marketing consent.
  Account/category consent events supersede earlier events by event time; equal-time conflicts block.
  Explicit all-message withdrawal blocks service replies. A later explicit opt-in can supersede withdrawal.
- An import without consent preserves existing permissions and does not invent an opt-out event.
  Account-specific imports/forms do not change the global legacy partner opt-in flag.
- Sales, CRM, invoice and AI automatic-send settings are not enabled by this deployment. Intentionally
  enabled client settings are retained. Do not enable them on restored test copies.
- Verified webhooks are persisted before acknowledgment. Failed events retry with backoff and have
  manager replay controls. Duplicate IDs and status/reply/reaction lookups are account-scoped.
- Ambiguous dispatches are held for review, not blindly resent. Meta acceptance is distinct from delivery.
  The dispatch ledger survives a parent transaction rollback. An orphan ledger entry needs investigation;
  this is not an end-to-end exactly-once delivery guarantee.
- Default/per-account Meta API versions are preserved. Review official Meta compatibility and controlled
  template/media fixtures before intentionally changing them.

Managers can inspect webhook retries, dispatch-review records and queue diagnostics. Active campaigns
keep existing pause/resume/cancellation controls. Queue metrics are operational snapshots, not a full
worker-heartbeat or delivery-latency monitoring platform.

## Sidecar Retirement

The WhatsApp Node service is excluded from default startup. The `legacy-whatsapp` Compose profile exists
only for migration; the separate face-attendance service is unchanged. Do not restart/rebuild a currently
running legacy relay merely to test the profile: older in-memory events may be lost on restart.

For **each** VPS record: current image, realtime mode, public Meta callback, proxy upstream, database,
signing/relay-secret configuration, Redis/memory queue usage, pending/processing/dead counts and owner.
Keep this inventory outside the repository if it contains secrets.

1. Verify ERP Bus delivery between two authorized inbox sessions, including a user without account access.
   Configure the authenticated Odoo websocket route at the reverse proxy when using multiprocess Odoo.
2. Have the credential owner switch the Meta callback and proxy route to Odoo's signed webhook endpoint.
   Preserve the correct database selection. Verify challenge, inbound, reply and delivery status with test contacts.
3. Retain the old relay until the route is verified and all pending, processing and failed events are resolved.
   The migration relay exposes authenticated `/migration/status` and `/migration/replay-failed` endpoints;
   the latter requeues at most 100 failed events per request. It acknowledges new webhooks only after Odoo
   durably accepts them. It refuses Socket.IO connections and unauthenticated diagnostic calls.
4. Stop only the WhatsApp sidecar after the inventory records zero unresolved events and verified direct routing.
   Retain rollback configuration. Delete Node sources/references only after every inventoried VPS has migrated.

Deprecated Odoo settings remain for old database-view compatibility. The browser uses ERP Bus regardless
of the stored old socket-mode selection. Do not expose port 3000 publicly; the legacy profile binds loopback.

## Access, Forms and Privacy

The upgrade removes blanket internal-user WhatsApp access. It maps demonstrable team members and chat
assignees, scopes data by company/account and limits sensitive configuration/logs to managers. Accounts
without identifiable teams or with ambiguous company ownership block deployment. Multi-company account
mapping uses the system parameter `whatsapp.account.company_mapping` (JSON account ID to company ID).
Review agent membership before rollout; do not grant every internal user manager rights as a workaround.

Production HMAC cannot be disabled with the old skip flag. Forms use CSRF, atomic IP throttling, server-side
consent, upload count/size limits and content parsing for supported images/PDFs. Set
`ODOO_TRUSTED_PROXY_CIDRS` only to actual proxy peers and enforce request-size/time limits at that proxy.
Parsing and rejecting known active PDF features is not malware scanning; regulated uploads may need
quarantine/scanning outside this module. Keep public attachment access disabled.

New API logs redact sensitive content and secrets; existing evidence is not rewritten. AI payload redaction
is not anonymization. Keep AI and destructive retention off until the client's data-processing policy is
approved. A complete audit of every legacy RPC/AI operation remains a release gate.

## Required Rollout Gates

- Run module Python/XML checks, deployment unit/SQL guard tests and the complete Odoo test suite.
- Run the Docker build/new-install/prod/recovery workflow on Linux with production-equivalent mounts,
  proxy and secrets. The development machine's Docker engine was unavailable during this implementation.
- Restore a real client backup to an isolated environment with network egress denied except loopback,
  mail disabled and external automation blocked before first application startup.
- Exercise the old-to-new migrations there; compare installed modules, real Sales/Inventory/Accounting/CRM
  records and totals, consent history and attachment contents; rehearse restoration and recovery.
- Complete browser tests for inbox, media, templates, campaigns, bots, settings and analytics, including
  multi-company/agent/manager permissions and private Bus subscriptions. No browser session was available here.
- Exercise concurrent opt-out/pause during dispatch, webhook ordering/crashes, Redis drain/restart,
  ambiguous API outcomes, forged RPC relationships and concurrent form uploads. Do not treat focused unit
  tests as exhaustive concurrency or security proof.
- Benchmark production-representative campaigns against a mocked Meta endpoint with real worker/ledger
  behavior and inbox browsers. The included 100-recipient rollback-only fixture mocks the dispatch ledger
  and rate limiter; it detects regressions, not production capacity.
- Canary one VPS at the tested revision with controlled contacts, verify inbound/reply/status/queues,
  then expand. Do not declare all deployments migrated without inventory evidence.

References: [WhatsApp Business Messaging Policy](https://business.whatsapp.com/policy) and
[Odoo 19 deployment documentation](https://www.odoo.com/documentation/19.0/administration/on_premise/deploy.html).
