# Hardening Validation Record

## Docker Commands: 2026-09-13

Added opt-in one-off Compose services `deploy-prod` and `deploy-new` which invoke the
same guarded deployment implementation. The public commands now use Git plus
`docker compose run --rm --build deploy-prod` (or `deploy-new`); host wrappers remain available.
The runner ships Bash/Python/OpenSSL, preserves the original Compose project identity and
verifies identical host/container checkout paths before accessing deployment functions.
It requires the local VPS Docker socket and a trusted checkout/operator, never a remote context.

Deployment test discovery: **33 passed**, including four isolated PostgreSQL tests. Eight new tests cover project/path/config identity,
new-vs-production service selection, one-off-only execution and local socket requirements.
Default Compose still resolves to only `db` and `odoo`; deployment-profile configuration also
validates. Python compilation, 43 XML parses and whitespace checks pass. The legacy relay
security test passed. The complete Apps/WhatsApp suite was rerun: **96 Odoo tests passed with
zero failures/errors** on the isolated test database.

The local Linux Docker engine remains unavailable. The new runner image and complete Compose
new/production/recovery workflows require Linux validation before client deployment. The prior
production-readiness gates still apply. No client data was accessed, modified or deployed from
this machine.

## Simple Commands and Apps Lock: 2026-09-10

- Permanent commands remain `bash deploy-prod.sh` and `bash deploy-new.sh` on Alpine/Ubuntu.
  Added separate private-config examples and a short quickstart; removed conflicting normal-update
  commands from the README. `NEW_INSTALL_MODULES` applies only to explicit fresh installation and
  may remain configured during production updates. Production still rejects legacy install flags.
- Apps guard uses a salted PBKDF2-SHA512 hash, 15-minute per-login/DB unlocks, CSRF-protected forms
  and atomic per-user attempt throttling. Administrator/sudo/context bypass and application removal
  of the guard are blocked. Native Settings views remain accessible. Host/DB/custom-code owners
  remain outside this application workflow boundary.
- **96 Odoo tests passed, zero failures/errors**: 13 Apps/native-administration tests plus all
  83 WhatsApp tests. Real local HTTP tests covered wrong password, unlock/relock, direct locked RPC,
  cross-session throttling, ordinary-user denial, CSRF, Settings and WhatsApp public forms.
  The initial run caught a password-page formatting error and one invalid test field; both were
  corrected before the passing combined run. Log: local `.apps-whatsapp-tests.log`.
- **25 deployment tests passed**, including four isolated PostgreSQL tests. Added coverage for
  mandatory guard availability, explicit new-install app selection, retained new-only settings,
  conflicting lists, non-default new database credentials and host-compatible backup hashing.
- Python compilation, 43 XML parses, default Compose validation, three changed Bash scripts'
  syntax and `git diff --check` passed. Host backup hashing no longer requires Python 3.11;
  Ubuntu's Python 3.10 is sufficient for the host orchestration (Odoo Python stays in its image).
- No client database/server was accessed. The disposable PostgreSQL test cluster is stopped after
  checks. Existing unrelated changes remain untouched; nothing was committed or pushed.

The Docker Linux engine and in-app browser were unavailable. Full Linux image-build/new-install/
backup/recovery runs, a restored real-client rehearsal and browser UI checks are still required.
These passing tests do not certify every third-party migration or production deployment.

## Deployment Recheck: 2026-09-10

Re-read both deployment paths and added conflict checks for new/production targets, early new-name
validation, explicit installed-module verification after new installation, and a health-gated startup
that stops on failure. All **19 deployment tests** passed, including four tests using the isolated
PostgreSQL cluster; the cluster was stopped immediately afterward. Python compilation, default
Compose validation and five Bash syntax checks passed. The WhatsApp module's 83-test result below
is from the prior run, not a new run on this date; module code was unchanged in this recheck.

Docker's Linux engine is still unavailable, so complete container deployment/recovery and restored
client rehearsals remain outstanding. No production operation was performed. Command examples in
the runbook apply only after the reviewed revision is released and client rollout gates pass.

## Original Validation

Date: 2026-09-09. Status: release candidate; production approval pending.

No production/client database was accessed or modified. Tests used a new local PostgreSQL cluster
on loopback port 16439, database `wa_hardening_test`, with synthetic records. That test cluster is
stopped. No deployment, commit or push was performed. Unrelated barcode/rebranding working-tree
changes were preserved.

## Passed Checks

- Odoo integration suite: **83 tests, zero failures/errors**, including five public-form HTTP tests.
  Loaded the module, registry, views and test assets with Python 3.12 and local PostgreSQL 14.
- Deployment tests: **13 passed**, including three real SQL trigger/fingerprint tests; the ten
  configuration/privacy tests were rerun after the final deployment bookkeeping changes.
- Legacy Node relay: authenticated diagnostics, invalid/missing HMAC rejection, exact signed payload
  relay, failure acknowledgment and Socket.IO rejection passed against a local mock Odoo endpoint.
  An intermittent Windows child-start timeout was observed; the harness now allows bounded 30-second
  startup and captures process errors. Final run passed in about 5.4 seconds.
- Python compile checks; all **42 module XML files** parsed; modified JavaScript syntax checks passed.
- Five deployment shell scripts passed `bash -n`; default and legacy-profile Compose configurations
  validated. Default Compose services are `db` and `odoo`.
- `git diff --check` passed. Existing unrelated changes were not reverted or staged.

## Guarded Upgrade Rehearsal

The installed-only guarded upgrade ran over all **66 installed modules** in the synthetic database.
No new modules were installed and none were uninstalled. Verification intentionally refused release
when the rebranding addon changed the built-in bot's name from `OdooBot` to `System Bot`.

Only that synthetic fixture's original name was restored; the original integrity baseline was not
replaced. Registry/view, module-set, business fingerprint and attachment verification then passed,
and the explicit release phase completed. This demonstrates the stop/review behavior, not a clean
first-pass upgrade of a real client. The later Docker image/recovery orchestration changes have not
been executed end to end because Docker Desktop's engine could not start.

## Synthetic Campaign

The final 100-recipient campaign fixture completed in **1.719 seconds** with unique recipients and
accepted statuses. It also checked that pause preserved pending records and resume continued delivery.
The fixture mocks Meta with 2 ms delay, the rate limiter and durable ledger, and uses rollback-only
synthetic data. Its observed 58.17 accepts/second is **not production sending capacity**. The empty
inbox query rounded to 0.00 ms; browser inbox responsiveness was not measured.

## Still Required

- Linux Docker new-install, production backup/encryption/restore and corrective recovery rehearsal.
- Restored real-client old-to-new migration with outbound networking/mail/automation blocked, financial
  and inventory integrity checks, permission mapping and attachment restoration.
- Browser workflow/access tests; full legacy RPC/AI audit and remaining cross-account security review.
- Multi-worker concurrency/crash/restart tests, real-ledger load tests and Redis migration-drain tests.
- Per-VPS callback/proxy/queue inventory, verified sidecar retirement and controlled-contact canary.

The implementation is not a claim that every legacy WhatsApp workflow is proven correct. Deployment
commands, prerequisites and explicit recovery procedures are in [DEPLOYMENT_SAFETY.md](DEPLOYMENT_SAFETY.md).
