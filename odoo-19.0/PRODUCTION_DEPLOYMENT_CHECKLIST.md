# Production Deployment Checklist

This repo contains live-client Odoo code and Docker volumes may contain client
database and filestore data. Do not run destructive Docker commands such as
`docker compose down -v`, `docker volume rm`, or database restore commands
unless a restore is explicitly intended and a verified backup exists.

## Safe Default Path

1. Keep client data in the named Docker volumes:
   - `odoo-db-data` for PostgreSQL data.
   - `odoo-web-data` for the Odoo filestore.
   - `odoo-db-backups` for optional backup dumps.
2. Validate host and compose syntax without changing services:
   `sh deploy/verify_docker_host.sh`
3. Build and start core services only after a backup window is approved:
   `docker compose up -d --build`

   For the hardened production compose file, use:
   `docker compose -f docker-compose.prod.yml up -d --build`

   For Alpine Proxmox LXC hosts that fail on
   `net.ipv4.ip_unprivileged_port_start`, use:
   `docker compose -f docker-compose.alpine-lxc.yml up -d --build`
4. Enable the WhatsApp sidecar only when its secrets are configured and approved:
   `docker compose -f docker-compose.prod.yml --profile whatsapp up -d --build sidecar`
5. Upgrade a client database only through the encrypted-backup path:
   `BACKUP_PASSPHRASE=... bash deploy/safe_production_update.sh <database_name>`

## Ubuntu And Alpine Hosts

- Ubuntu 24.04: install Docker Engine with the Compose plugin, then run the
  verifier with `sh deploy/verify_docker_host.sh`.
- Alpine Linux: install Docker, the Compose plugin, `curl` or `wget`, and
  `bash` if you plan to run the existing `deploy/*.sh` maintenance scripts.
  Runtime containers are pinned by Docker images, so the host distribution does
  not change the Odoo/PostgreSQL runtime packages. Compose memory and CPU limits
  are intentionally not set, to avoid low-memory install failures on Alpine hosts.

  Alpine package baseline:

  ```sh
  apk update
  apk add git docker docker-cli-compose bash curl
  rc-service docker start
  rc-update add docker default
  ```

- Alpine Proxmox LXC: first run
  `sh deploy/verify_alpine_docker_runtime.sh`. If Docker reports
  `net.ipv4.ip_unprivileged_port_start`, the host is blocking Docker network
  namespace sysctls before Odoo starts. Use an Alpine VM/bare-metal host,
  enable nested Docker support for the Proxmox CT, or run the fallback compose
  file with host networking:
  `docker compose -f docker-compose.alpine-lxc.yml up -d --build`.

  The fallback keeps the same named volumes (`odoo-db-data`, `odoo-web-data`,
  and `odoo-db-backups`) but does not create an internal Docker bridge network.
  PostgreSQL binds to `127.0.0.1`; ports `5432`, `8069`, `3000`, and optional
  `8071` must be free on the Alpine LXC host.

## Production Compose

Use `docker-compose.prod.yml` for production rollouts. It avoids bind-mounting
the entire repository into the Odoo container, builds the WhatsApp sidecar as an
image instead of installing dependencies into the working tree at startup, keeps
optional sidecars behind profiles, and reads production secrets from `.env`.

The existing `docker-compose.yml` is still suitable for current/local operation
and has not been changed in a way that restarts or migrates live data.


## Pull And Update Without Touching Client Data

A normal `git pull` changes repository files only. It does not modify Docker
named volumes, PostgreSQL databases, Odoo filestore files, or client records.
Client data is touched only when an operator runs database update, restore,
uninstall, or volume-delete commands.

Use this production-safe sequence after pulling code:

```bash
git pull origin main
sh deploy/verify_docker_host.sh
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE && echo
export BACKUP_PASSPHRASE
bash deploy/safe_production_update.sh YOUR_CLIENT_DB
```

The safe update script refuses to guess a database, requires an encrypted backup,
keeps Docker volumes intact, does not uninstall modules, and leaves SaaS runtime
metadata disabled after the update. Do not use `docker compose down -v`,
`docker volume rm`, `dropdb`, or restore scripts unless a destructive restore is
explicitly approved.
## Client Data Safety

- Never delete Docker volumes during updates.
- Never let scripts guess a live database name.
- Take and verify an encrypted backup before module install or upgrade.
- Keep the optional face sidecar disabled unless the client explicitly approves
  it with `--profile face`.
- Treat `odoo.docker.conf` and `.env` as secrets-bearing files. Rotate exposed
  passwords during an approved maintenance window.