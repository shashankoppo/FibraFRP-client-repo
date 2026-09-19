# Cloudflare Tunnel And Client Evidence

Cloudflare Tunnel provides the browser's address to the local origin in the
`CF-Connecting-IP` header. The application accepts that value only when the
immediate peer is included in `ODOO_TRUSTED_PROXY_CIDRS`. It never trusts
`X-Forwarded-For` from the public internet.

## One-Time VPS Configuration

Run this on the VPS that runs both `cloudflared` and Docker:

```sh
cd /home/FibraFRP-client-repo/odoo-19.0
printf '\nODOO_TRUSTED_PROXY_CIDRS=172.17.0.1/32\nODOO_BIND_ADDRESS=127.0.0.1\n' >> .env
```

`172.17.0.1` is the usual Docker bridge gateway when host `cloudflared` reaches
the published Odoo port. Confirm it before deployment with:

```sh
docker inspect odoo_app --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'
```

Use the returned gateway as `ODOO_TRUSTED_PROXY_CIDRS`, with `/32` appended.
If `cloudflared` runs in a separate Docker container, do not use this host
example. Inspect its Odoo-network address and configure that exact address
with `/32`, or place the tunnel behind a dedicated reverse proxy network.

Configure the Cloudflare Tunnel route to the local origin, not the public
hostname:

```yaml
ingress:
  - hostname: erp.example.com
    service: http://127.0.0.1:8069
  - service: http_status:404
```

Validate a locally managed configuration before restarting it:

```sh
cloudflared tunnel ingress validate
sudo systemctl restart cloudflared
```

The localhost Docker binding prevents direct public access to port 8069 while
leaving the host's Cloudflare Tunnel able to reach Odoo. Do not enable it until
the tunnel and its local service route are confirmed healthy.

## Verify

After a user checks in or logs in through the public hostname, their new
Attendance row shows the real IP and a device label. A new Security Audit row
shows `Cloudflare Tunnel` as the IP source. Older records are unchanged.

## Safe Production Upgrade

The production runner only upgrades modules already installed in the configured
database. It backs up the existing database and matching filestore, refuses an
unknown target, and does not create a database or install/uninstall modules.

FiberaFRP:

```sh
cd /home/FibraFRP-client-repo/odoo-19.0 && export ODOO_AUTO_UPDATE_DB_NAME=FiberaFRP_DB LIVE_DB_NAME=FiberaFRP_DB && git pull --ff-only origin main && docker compose --profile deployment run --rm --build deploy-prod
```

Xenium:

```sh
cd /home/FibraFRP-client-repo/odoo-19.0 && export ODOO_AUTO_UPDATE_DB_NAME=Xenium_DB_DR LIVE_DB_NAME=Xenium_DB_DR && git pull --ff-only origin main && docker compose --profile deployment run --rm --build deploy-prod
```

Before either command, `git status --short` must be empty. Xenium's earlier
local commits and custom `requirements.txt` change must be reconciled first;
the production runner deliberately refuses a dirty or diverged checkout.
