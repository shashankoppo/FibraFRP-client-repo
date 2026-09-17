# Permanent Deployment Commands

Release candidate: run the checks in [DEPLOYMENT_SAFETY.md](DEPLOYMENT_SAFETY.md)
on an isolated restored client copy before a production rollout. Local edits must first
be reviewed, committed and pushed; a VPS cannot pull unpublished work.

## Existing Client VPS

From the **existing** `odoo-19.0` directory, keep `.env`, DB credentials, Compose project
and volumes. Add the exact existing DB target and a strong backup encryption secret once:

```dotenv
ODOO_AUTO_UPDATE_DB_NAME=FiberaFRP_DB
BACKUP_PASSPHRASE=<your-private-backup-secret>
ODOO_AUTO_ALLOW_INSTALL=NO
```

Replace the secret placeholder with your own retained secret. On another client's VPS,
use that client's actual DB name. Never overwrite their existing `.env` with a template.
Leave legacy `INSTALL_MODULES`, `EXTRA_INSTALL_MODULES` and `ODOO_AUTO_INSTALL_MODULES` unset.
The Apps guard `elsx_client_restrictions` must already be installed; otherwise preflight
stops and requires a separately approved installation. It does not install it behind your back.

Every update:

```bash
git pull --ff-only origin main && docker compose run --rm --build deploy-prod
```

This pulls main with fast-forward only. The deployment job builds, stops Odoo for a matching DB/filestore
encrypted backup, upgrades **installed** modules, checks integrity and starts the app.
It never creates a replacement DB or automatically installs/uninstalls modules.
Allow maintenance downtime. Failure leaves the database/volumes in place and Odoo stopped
for explicit recovery. Never bypass a failed guard with a plain restart.

Old VPSs with a source bind mount or local `package-lock.json` changes need the one-time
transition described in the safety runbook **before pulling**. Do not discard local edits.

## Separate Fresh VPS, No Client DB

Clone the released repo, then enter `odoo-19.0`. Configure a private `.env` using
[deploy/new.env.example](deploy/new.env.example) as reference. Choose the new DB name,
initial app list, and distinct PostgreSQL, ERP administrator and backup secrets.
Keep `NEW_DB_NAME` and `ODOO_AUTO_UPDATE_DB_NAME` equal. Include `elsx_client_restrictions`
in `NEW_INSTALL_MODULES`. Protect `.env` with `chmod 600 .env` and retain backup secrets off-VPS.

First installation only:

```bash
git pull --ff-only origin main && docker compose run --rm --build deploy-new
```

It refuses an existing target DB or existing Odoo service. It installs only the explicitly
selected initial apps and their required dependencies. The new-only settings can remain;
they are ignored by production. Subsequent updates use:

```bash
git pull --ff-only origin main && docker compose run --rm --build deploy-prod
```

## Alpine and Ubuntu

Use the same two deployment commands on either host, from the physical `odoo-19.0`
directory in a normal VPS shell. The host needs Git and a working modern Docker Engine
and Compose with `run --build`, `--wait` and JSON configuration support. Python, Bash
and OpenSSL for deployment are supplied by the one-off runner image.

On an existing Docker host, install Git once as root if missing:

```bash
# Alpine
apk add --no-cache git

# Ubuntu
apt-get update
apt-get install -y git

# Check Docker Engine and Compose are already installed and running
docker info
docker compose version
```

For a fresh host without Docker, follow the distribution's installation guide first:
[Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) or
[Alpine Docker packages](https://pkgs.alpinelinux.org/packages?name=docker-cli-compose).
Do not replace a working client's Docker installation during an application update.

The one-off deployment container mounts the reviewed checkout at the same absolute path
and uses the **local Docker socket**, which gives it host-administrator-level control.
Use only a trusted checkout and trusted VPS operators. It exposes no ports and has no
container network connection. It validates the original Compose project name and host
bind paths before calling the existing guarded runner. It never mounts client data
volumes directly; the guarded runner retains the existing volume identity checks.

Run on the VPS itself, not against a remote Docker context or Windows Docker Desktop.
Keep custom Compose/env files inside the repository's mounted directory. Secret env files
must be named `.env`, `.env.*` or `*.env`; those patterns are excluded from Docker builds. Do not set
`PWD` to a made-up path; enter the physical directory with `cd -P` if using a symlink.
Do not pull or change the checkout while another deployment is running.

Explicitly targeting `deploy-prod` or `deploy-new` activates that one-off service without
needing a `--profile` argument. Neither is part of default startup. Even an accidental
`up --profile deployment` is rejected because deployment requires a one-off `run`.
See [Docker's profile behavior](https://docs.docker.com/compose/how-tos/profiles/).

The prior `bash deploy-prod.sh` / `bash deploy-new.sh` commands remain supported for
operators who prefer host scripts (Bash, Python 3.10+ and OpenSSL required there).
CI can omit `git pull` and run the Compose job directly against its checked-out revision;
the container does not pull again. Existing `.env` and supported VPS/CI settings are reused.

## Apps Lock

The requested Apps password is stored as a salted PBKDF2 hash, never plaintext. Apps
requires a separate unlock even for administrators; normal employees do not gain new
access by knowing it. The unlock lasts 15 minutes, is tied to that login session and
database, and is cleared by logout. Visiting `/elsx/apps/unlock` locks it immediately again.
Incorrect attempts are limited per user across browser sessions.

Settings and ordinary ERP operations keep their native permissions. Module-management
RPC mutations are guarded; the guard cannot uninstall itself through the application.
CLI maintenance uses the separate installed-only deployment guard. This is an application
workflow lock, not protection against someone controlling the host, database or custom code.
Use HTTPS. A per-client replacement hash can be injected with `ELSX_APPS_PASSWORD_HASH`;
the application exposes no password-disable switch. Do not use the Apps password for backups.

`git pull origin main && docker compose up -d --build` is **not** the update command:
ordinary Compose startup intentionally does not upgrade DB schemas. Never run
`docker compose down -v` on client environments.
