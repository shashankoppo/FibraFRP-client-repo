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

- PostgreSQL dump, for example `qwerty.pg_dump`.
- Filestore archive, for example `qwerty_filestore.tar.gz`.

Stop Odoo while restoring:

```bash
docker compose stop odoo sidecar
```

Restore database:

```bash
docker compose exec -T db dropdb -U odoo --if-exists qwerty
docker compose exec -T db createdb -U odoo qwerty
docker compose exec -T db pg_restore -U odoo -d qwerty --clean --if-exists < /path/to/qwerty.pg_dump
```

Restore filestore:

```bash
docker volume inspect odoo-190_odoo-web-data
```

Copy the filestore archive to the server, then extract it so the final folder is:

```text
/root/.local/share/Odoo/filestore/qwerty
```

A typical command is:

```bash
docker run --rm -v odoo-190_odoo-web-data:/data -v /path/to/backups:/backup alpine sh -c "mkdir -p /data/filestore && tar -xzf /backup/qwerty_filestore.tar.gz -C /data/filestore"
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

## 9. What Is Not in Git

The Git repository contains application code and deployment files. It does not
contain:

- Docker volumes.
- PostgreSQL database contents.
- Odoo filestore.
- Live Meta tokens.
- Tally credentials.
- Production SSL certificates.

These must be restored or configured on each deployment target.
