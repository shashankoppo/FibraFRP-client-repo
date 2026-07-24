# Simple Server Commands

## Odoo Web Backup

Open:

```text
https://your-domain/web/database/manager
```

Choose **Backup**, enter the Odoo master password, select **ZIP**, and keep
**Include filestore** enabled. The ZIP contains the PostgreSQL dump, manifest,
and uploaded files. Store it securely outside this Git repository.

## New Server

After cloning the repository:

```bash
cd FibraFRP-client-repo/odoo-19.0
sh server.sh init
nano .env
sh server.sh start
```

Replace every placeholder in `.env` before running `start`.

To restore client data, open Database Manager, upload the ZIP, and preserve the
original database name. Then run:

```bash
sh server.sh apply
```

This restarts Odoo through the backup-first compatibility upgrade and starts
the WhatsApp sidecar only after Odoo is healthy.

## Existing Production Server

First download and verify the Odoo ZIP backup with its filestore. Then:

```bash
cd /path/to/FibraFRP-client-repo/odoo-19.0
sh server.sh update
```

Type `BACKUP` when prompted. The command:

1. Refuses to overwrite local tracked changes.
2. Pulls `origin/main` using fast-forward-only mode.
3. Stops the WhatsApp sidecar during the update.
4. Rebuilds and recreates services without deleting named volumes.
5. Runs the repository's automatic backup-first database upgrades.
6. Shows the final container state.

For automation after an independently verified web backup:

```bash
ODOO_WEB_BACKUP_CONFIRMED=YES sh server.sh update
```

Do not replace an existing production `.env`, change its Compose project name,
or run `docker compose down -v`.
