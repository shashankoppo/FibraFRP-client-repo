# FibraFRP — Odoo 19.0 Enterprise Architecture Blueprint

Welcome to the central repository for the FibraFRP custom Odoo 19.0 deployment. This document outlines the technical architecture, custom module ecosystem, connection points, and workflow required to maintain and develop this system.

## Ubuntu 24.04 Docker Deployment

Use [UBUNTU_24_DOCKER_DEPLOYMENT.md](UBUNTU_24_DOCKER_DEPLOYMENT.md) for
server setup, exact clone restore, fresh database setup, WhatsApp webhook checks,
Tally routing, and post-deploy verification.

For production updates with multiple databases, pull/build the code and run the
all-database module upgrade script so every database receives the latest stored
views, menus, and actions:

```bash
git pull origin main
docker compose down
docker compose build odoo
bash deploy/upgrade_module_all_dbs.sh elsx_whatsapp_marketing
```

For the current production/live database, use `FiberaFRP_DB` as the primary
database and mark only that database as the WhatsApp webhook receiver:

```bash
git pull origin main
docker compose build odoo
bash deploy/configure_live_db.sh FiberaFRP_DB 1 elsx_verify_2024
```

The second argument is the live WhatsApp account ID and the third argument is
the Meta webhook verify token. In Meta, use the callback URL printed by the
script, for example `https://fibera.elsxglobal.com/whatsapp/webhook?db=FiberaFRP_DB`.
The Docker config loads the WhatsApp webhook controller server-wide so Meta can
verify the URL before an Odoo browser session selects a database.

The live configuration script installs `elsx_attendance_tracking` if it is
missing. That also installs the standard Attendances dependency, then upgrades
the WhatsApp, branding, attendance tracking, and Tally custom modules.

---

## 🏗️ System Architecture & Tech Stack

This project is a hybrid system utilizing Odoo 19.0 as the core ERP and CRM engine, augmented by real-time microservices for high-performance communication.

### Core Technologies
- **Backend ERP**: Odoo 19.0 Enterprise (Dockerized)
- **Database**: PostgreSQL 16
- **Real-Time Engine**: Node.js Sidecar + Socket.io (Zero-latency WebSocket server)
- **Frontend Framework**: OWL 2.0 (Odoo Web Library) & Native JS
- **API Integrations**: Meta / WhatsApp Cloud API v19.0+

### Key Connection Points
1. **Node.js Sidecar (`node_sidecar:3000`)**: 
   - Acts as a high-speed relay between Odoo and the browser.
   - Listens to Odoo's internal `bus.bus` for outbound messages and pushes them instantly to the user's browser via WebSockets.
   - Connected via `whatsapp.sidecar.url` and `whatsapp.sidecar.secret` in the Global Settings.
2. **Meta Cloud Webhooks**:
   - Meta sends inbound messages and status updates (delivered/read) directly to `controllers/whatsapp_webhook.py`.
   - The webhook parses the JSON, validates the SHA256 signature, and triggers the Node.js sidecar for real-time UI updates.
3. **Local Partner Autocomplete**:
   - Replaces Odoo's default paid IAP credit system. Intercepts `/iap/autocomplete` requests and routes them through a local fuzzy-search database.

---

## 📦 Custom Module Ecosystem

The `custom_addons` directory contains the proprietary logic developed specifically for FibraFRP. 

### 1. `elsx_whatsapp_marketing` (Flagship Module)
The enterprise-grade WhatsApp Business console. Built to rival dedicated platforms like WATI.io or Intercom.

**Directory Breakdown**:
- `models/`: Python logic.
  - `whatsapp_account.py`: API Credentials & Webhook settings.
  - `whatsapp_message.py` & `whatsapp_chat.py`: Core messaging loop, data normalization, and attachment handling.
  - `whatsapp_webhook_log.py`: Security and payload auditing.
  - `whatsapp_compliance.py`: Team Member routing, GDPR rules, and quiet hours.
  - `res_config_settings.py`: Global application settings.
- `controllers/`: 
  - `whatsapp_webhook.py`: The high-throughput HTTP endpoint for Meta API.
- `static/src/`:
  - `js/whatsapp_widget.js`: The OWL/JS hybrid engine rendering the real-time Team Inbox.
  - `js/notification_tones.js`: Native Web Audio API synthesis for zero-dependency sound alerts.
- `views/`: XML definitions for menus, kanban boards, and forms. Note that the `whatsapp_menu.xml` is the entry point for all UI navigation.

### 2. `elsx_partner_autocomplete` (Infrastructure Module)
A highly optimized override for Odoo's default autocomplete behavior.
- **Why it exists**: Odoo 19 charges IAP credits for basic contact creation lookups. This module overrides `IapAutocompleteApi._request_partner_autocomplete`.
- **How it works**: Performs local regex and fuzzy matching against existing `res.partner` records (by VAT, name, or domain) before falling back to free public APIs, bypassing Odoo's billing entirely.

---

## ⚙️ Development Workflow & How to Work Here

When making changes to the system, strictly follow this workflow to ensure data integrity and cache invalidation.

### 1. Modifying Python Files (Backend)
If you change logic in `models/` or `controllers/`:
1. Save the file.
2. **Recompile Python Cache**: Run `python -m compileall odoo-19.0/custom_addons/` (If outside Docker).
3. **Restart Docker Container**: The Python backend loads into RAM. You must restart the Odoo container:
   ```bash
   docker compose restart odoo
   ```

### 2. Modifying XML Views or Menus
If you change layout XML files in `views/` or add fields:
1. Save the XML file.
2. **Increment Module Version**: Open `__manifest__.py` and bump the version number (e.g., `19.0.2.7.0` -> `19.0.2.8.0`).
3. **Upgrade via UI**: 
   - Turn on Developer Mode in Odoo.
   - Go to Apps -> Update Apps List.
   - Find the module and click **Upgrade**.

### 3. Modifying JavaScript/CSS (Frontend)
If you change OWL components, JS widgets, or CSS:
1. Save the asset file.
2. Ensure the asset is listed in the `'assets'` dictionary inside `__manifest__.py`.
3. Hard refresh your browser (`Ctrl + F5` or `Cmd + Shift + R`). Odoo automatically recompiles JS/CSS bundles in Developer Mode (with Assets). If not, restart the Docker container.

---

## 🔒 Security & Best Practices

- **Never** modify core Odoo files inside the `addons/` directory. Always use model inheritance (`_inherit`) inside `custom_addons/`.
- **Media Attachments**: Ensure outbound media is attached via `media_file` binary fields, which automatically generate `ir.attachment` records for real-time preview rendering.
- **Database Safety**: When writing raw SQL queries using `self.env.cr.execute`, always use parameterized inputs (`%s`) to prevent SQL injection.
