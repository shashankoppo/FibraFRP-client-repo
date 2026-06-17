# Ubuntu 24.04 Docker Deployment Guide

This guide deploys the FiberaFRP Odoo 19 stack on Ubuntu 24.04 using Docker
Compose. It supports two modes:

- Exact clone: restore the current production database and filestore.
- Fresh database: create a new database and configure accounts manually.

## 1. Server Requirements

- Ubuntu 24.04 LTS.
- Docker Engine and Docker Compose plugin.
- Internet access during first build.
- Public HTTPS URL for production WhatsApp webhooks.
- Enough disk space for PostgreSQL, filestore, logs, and backups.

Check the host:

```bash
docker --version
docker compose version
```

## 2. Get the Code

```bash
git clone https://github.com/shashankoppo/FibraFRP-client-repo.git
cd FibraFRP-client-repo/odoo-19.0
```

Optional environment file:

```bash
cp deploy/ubuntu24.env.example .env
nano .env
```

The defaults still work without `.env`, but production should set strong
database and sidecar secrets.

## 3. Build and Start

Validate Compose first:

```bash
docker compose config
```

Build and start:

```bash
docker compose up -d --build
```

Watch startup:

```bash
docker compose ps
docker logs -f odoo_app
docker logs -f whatsapp_sidecar
```

Open:

```text
http://SERVER_IP:8069
http://SERVER_IP:8069/web/database/manager
```

## 4. Exact Clone Restore

Use this when the Ubuntu deployment must behave exactly like the current
working machine.

### Preferred: Encrypted Portable Backup

Use this path for live production data. It moves the database, filestore,
WhatsApp records, invoices, and included local config through one encrypted file
without committing private data to GitHub.

On the current/live server:

```bash
cd ~/Desktop/FiberaFRP/FibraFRP-client-repo/odoo-19.0
git pull origin main
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE
bash deploy/export_live_encrypted_backup.sh FiberaFRP_DB
```

Copy the generated `.enc` file from `secure_backups/` through private storage
only. Do not commit it to GitHub.

On the target Ubuntu Docker host:

```bash
cd ~/Desktop/FiberaFRP/FibraFRP-client-repo/odoo-19.0
git pull origin main
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE
CONFIRM_RESTORE=YES bash deploy/restore_live_encrypted_backup.sh /path/to/backup.enc FiberaFRP_DB
```

By default, restore does not overwrite local `.env` or `odoo.docker.conf`.
Restore those config files only when deliberately cloning the source server
configuration:

```bash
RESTORE_CONFIG=YES CONFIRM_RESTORE=YES bash deploy/restore_live_encrypted_backup.sh /path/to/backup.enc FiberaFRP_DB
```

After restore, run the live database helper so webhook ownership and module
state are refreshed:

```bash
bash deploy/configure_live_db.sh FiberaFRP_DB 1 elsx_verify_2024
```

### Advanced Manual Restore

Required files:

- PostgreSQL dump, for example `FiberaFRP_DB.pg_dump`.
- Filestore archive, for example `FiberaFRP_DB_filestore.tar.gz`.

Stop Odoo while restoring:

```bash
docker compose stop odoo sidecar
```

Restore database:

```bash
docker compose exec -T db dropdb -U odoo --if-exists FiberaFRP_DB
docker compose exec -T db createdb -U odoo FiberaFRP_DB
docker compose exec -T db pg_restore -U odoo -d FiberaFRP_DB --clean --if-exists < /path/to/FiberaFRP_DB.pg_dump
```

Restore filestore:

```bash
docker volume inspect odoo-190_odoo-web-data
```

Copy the filestore archive to the server, then extract it so the final folder is:

```text
/root/.local/share/Odoo/filestore/FiberaFRP_DB
```

A typical command is:

```bash
docker run --rm -v odoo-190_odoo-web-data:/data -v /path/to/backups:/backup alpine sh -c "mkdir -p /data/filestore && tar -xzf /backup/FiberaFRP_DB_filestore.tar.gz -C /data/filestore"
```

Start again:

```bash
docker compose up -d
```

## 5. Fresh Database Flow

Use this when creating a clean client or test DB.

1. Open `/web/database/manager`.
2. Create the new database.
3. Log in and install required custom addons:
   - `elsx_client_restrictions`
   - `elsx_whatsapp_marketing`
   - `elsx_tally_integration`
4. Create a WhatsApp Account manually.
5. Fill Meta credentials, webhook token, app secret, phone ID, and WABA ID.
6. Open the WhatsApp account and click `Initialize Defaults`.
7. Configure Tally settings only after confirming where Tally runs.

Fresh databases must not reuse live Meta credentials unless that is deliberate.

## 6. WhatsApp Production Webhook

For production, expose Odoo through HTTPS using a reverse proxy such as Nginx,
Traefik, or Caddy.

The Docker config loads `elsx_whatsapp_marketing` in `server_wide_modules`
because Meta verifies the webhook before an Odoo browser session has selected a
database. The webhook controller then opens the explicit database from
`?db=FiberaFRP_DB`.

Meta should call the public HTTPS callback URL for the active WhatsApp account.
For the current live database, use the database-pinned URL:

```text
https://fibera.elsxglobal.com/whatsapp/webhook?db=FiberaFRP_DB
```

After pulling code or restoring the live database, run:

```bash
bash deploy/configure_live_db.sh FiberaFRP_DB
```

If there are multiple WhatsApp accounts in the live database, pass the Odoo
WhatsApp account ID as the second argument to force the primary receiver:

```bash
bash deploy/configure_live_db.sh FiberaFRP_DB 1
```

If Meta verification is failing because the database token does not match the
token entered in Meta, pass the verify token as the third argument:

```bash
bash deploy/configure_live_db.sh FiberaFRP_DB 1 elsx_verify_2024
```

After changing domains, verify:

- Webhook verification succeeds.
- Incoming customer message appears in Team Inbox.
- Delivery/read status updates appear.
- The active WhatsApp account shows connected/verified.

## 7. Tally on Ubuntu Docker

If Tally runs on the Docker host or another LAN machine, configure the Tally
Gateway URL in Odoo accordingly.

Common values:

```text
http://host.docker.internal:9000
http://LAN_IP_OF_TALLY_MACHINE:9000
```

This Compose file includes Linux host-gateway support for
`host.docker.internal`. If the Tally desktop is on Windows or another machine,
the LAN IP is usually clearer.

For first demos, XML export remains safer than live gateway sync because it does
not depend on Docker-to-desktop network routing.

## 8. Verification

Run:

```bash
bash deploy/verify_ubuntu_docker.sh
```

Manual acceptance checks:

- `docker compose config` passes.
- Odoo opens on port `8069`.
- `/web/database/manager` opens.
- Existing/restored DB logs in.
- A test DB can be created if needed.
- WhatsApp Marketing opens.
- Team Inbox opens and can switch chats.
- Incoming WhatsApp message appears.
- Dashboard loads live counts.
- Template and campaign screens open.
- Tally sync/export path works.

## 9. Production-Safe Update Path

Use this path for the live `FiberaFRP_DB` when client data is already present.
It creates an encrypted backup first, builds the Odoo image, upgrades only the
safety modules requested by the script, restarts Odoo/WhatsApp sidecar, and
prints health checks. It never runs `docker compose down -v` and never uninstalls
modules.

```bash
cd ~/Desktop/FiberaFRP/FibraFRP-client-repo/odoo-19.0
git pull origin main
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE
bash deploy/safe_production_update.sh FiberaFRP_DB
docker compose ps
docker logs --tail 250 odoo_app
```

To include a specific outside/custom module install in the same controlled run,
copy the addon into `custom_addons`, confirm it is compatible with Odoo 19, then
pass it through `EXTRA_INSTALL_MODULES`. Add it to `EXTRA_UPGRADE_MODULES` too
when the module already exists in the database and needs XML/schema refresh:

```bash
EXTRA_INSTALL_MODULES=my_new_module EXTRA_UPGRADE_MODULES=my_new_module bash deploy/safe_production_update.sh FiberaFRP_DB
```

To upgrade an already installed module without installing anything new:

```bash
EXTRA_UPGRADE_MODULES=elsx_whatsapp_marketing bash deploy/safe_production_update.sh FiberaFRP_DB
```

If an outside module still cannot install, check its manifest dependencies,
Python package requirements, Odoo version compatibility, XML view inheritance,
and whether its technical name is present in the configured addon path. The
ELSx module guard blocks protected uninstalls only; normal installs are still
handled by Odoo.

Face attendance is installed as a separate addon but remains disabled until an
administrator enables it in Settings. Normal Attendances keep working as before.
The local recognition sidecar is also disabled by default through a Docker
profile. Start it only after testing on a staging copy:

```bash
docker compose --profile face up -d face_sidecar
```

The SaaS admin console is installed as `elsx_saas` by the same safe update. It
appears only for system administrators under **ELSx SaaS Admin > Tenants**. It
records tenant lifecycle, enabled apps, limits, safety checklist, and deployment
plan. It does not create/drop databases from the browser.

Production smoke checks after this update:

- Login works.
- WhatsApp Inbox opens and receives a test inbound message.
- CRM leads and WhatsApp links open.
- Invoices/accounting open.
- Campaign/template previews open.
- Existing Attendances open and normal check-in works.
- Attendance kiosk links use the current tenant/domain, for example
  `localhost` locally and `fibera.elsxglobal.com` in production, with the
  correct `db=` query for multi-database SaaS routing.
- Face Attendance settings are visible but disabled.
- ELSx SaaS Admin opens for system administrators.
- Protected module uninstall is blocked with a clear warning.

## 10. Updating Custom Modules Across All Databases

Odoo stores module XML views, menus, actions, and fields inside each database.
After pulling code, every database that uses WhatsApp Marketing must receive a
module upgrade. Updating only one database leaves other databases with old stored
views and can keep errors such as missing campaign fields alive.

For one production database, use the backup-first updater and pass the database
name explicitly:

```bash
git pull origin main
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo
export BACKUP_PASSPHRASE
bash deploy/safe_production_update.sh FiberaFRP_DB
```

For all application databases on the server, use the all-DB updater. It requires
an explicit confirmation flag so it cannot run tenant-wide by accident:

```bash
git pull origin main
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo
export BACKUP_PASSPHRASE
CONFIRM_ALL_DBS=YES bash deploy/safe_update_all_dbs.sh
```

Both safe scripts:

- Starts PostgreSQL.
- Creates encrypted backups before module changes.
- Builds the Odoo image.
- Stops Odoo and the WhatsApp sidecar only while upgrades run.
- Installs/upgrades the configured custom modules.
- Starts Odoo and the sidecar again.
- Never runs `docker compose down -v`.
- Never deletes databases, filestores, records, credentials, invoices, WhatsApp
  messages, or customer data.

To upgrade only one module across all databases, override the module list:

```bash
INSTALL_MODULES=elsx_whatsapp_marketing \
UPGRADE_MODULES=elsx_whatsapp_marketing \
CONFIRM_ALL_DBS=YES \
bash deploy/safe_update_all_dbs.sh
```

To exclude additional databases from an all-DB update, pass a comma-separated
list:

```bash
DB_NAME_EXCLUDES=postgres,test_old \
CONFIRM_ALL_DBS=YES \
bash deploy/safe_update_all_dbs.sh
```

After any upgrade, verify:

```bash
docker compose ps
docker logs --tail 200 odoo_app
```

Then open the active client databases and check Login, WhatsApp Inbox,
Campaigns, Templates, Flow Builder, Dashboard, CRM, Invoicing, Attendance, and
Face Attendance. Start the face sidecar only for databases where Face Attendance
is approved:

```bash
docker compose --profile face up -d face_sidecar
```

## 11. What Is Not in Git

The Git repository contains application code and deployment files. It does not
contain:

- Docker volumes.
- PostgreSQL database contents.
- Odoo filestore.
- Live Meta tokens.
- Tally credentials.
- Production SSL certificates.

These must be restored or configured on each deployment target.
