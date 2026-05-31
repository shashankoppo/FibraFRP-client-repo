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

## 9. Updating Custom Modules Across All Databases

Odoo stores module XML views, menus, actions, and fields inside each database.
After pulling code, every database that uses WhatsApp Marketing must receive a
module upgrade. Updating only one database leaves other databases with old stored
views and can keep errors such as missing campaign fields alive.

For normal WhatsApp Marketing deployments, run:

```bash
git pull origin main
docker compose down
docker compose build odoo
bash deploy/upgrade_module_all_dbs.sh elsx_whatsapp_marketing
```

For the current production database, prefer the live helper after build:

```bash
git pull origin main
docker compose build odoo
bash deploy/configure_live_db.sh FiberaFRP_DB 1 elsx_verify_2024
```

The script:

- Starts PostgreSQL.
- Stops Odoo and the sidecar while upgrades run.
- Lists all non-template application databases.
- Runs `-u elsx_whatsapp_marketing` once per database.
- Starts Odoo and the sidecar again.

To exclude additional databases, pass a comma-separated list:

```bash
DB_NAME_EXCLUDES=postgres,test_old bash deploy/upgrade_module_all_dbs.sh elsx_whatsapp_marketing
```

After the upgrade, verify:

```bash
docker logs --tail 200 odoo_app
```

Then open WhatsApp Marketing and check Campaigns, Templates, Flow Builder,
Team Inbox, and Dashboard in every active client database.

## 10. What Is Not in Git

The Git repository contains application code and deployment files. It does not
contain:

- Docker volumes.
- PostgreSQL database contents.
- Odoo filestore.
- Live Meta tokens.
- Tally credentials.
- Production SSL certificates.

These must be restored or configured on each deployment target.
