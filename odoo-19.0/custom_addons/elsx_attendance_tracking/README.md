# ELSx Attendance Tunnel Tracking

This addon improves standard Odoo Attendances tracking when users check in/out through a public tunnel, reverse proxy, Cloudflare, Nginx, or Docker host gateway.

## What it fixes

- Reads the real client IP from safe proxy/tunnel headers such as `CF-Connecting-IP`, `True-Client-IP`, `X-Real-IP`, and `X-Forwarded-For`.
- Falls back to Odoo GeoIP or the direct request IP when no forwarded public IP is available.
- Keeps standard check-in/check-out behavior unchanged.
- Shows attendance location and IP columns in the Attendances list view.

## Required setting

Open **Attendances > Configuration > Settings** and enable **Device & Location Tracking**.

For GPS location, the browser must allow location permission and the attendance page should be served over HTTPS. If the browser denies GPS, Odoo can still store the best available IP address, but map location may remain `Unknown`.

## Deployment

Install or upgrade this addon only on databases where Attendances are used:

```bash
docker compose run --rm -T --no-deps odoo python3 /opt/odoo/odoo-bin -c /etc/odoo/odoo.conf -d YOUR_DB_NAME -i elsx_attendance_tracking --stop-after-init
docker compose up -d
```
