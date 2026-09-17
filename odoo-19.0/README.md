# FibraFRP - Odoo 19.0 Community Edition

Welcome to the central repository for the FibraFRP custom Odoo 19.0 deployment. This document outlines the technical architecture, custom module ecosystem, connection points, and workflow required to maintain and develop this system.

## Alpine and Ubuntu Docker Deployment

Use [DEPLOYMENT_QUICKSTART.md](DEPLOYMENT_QUICKSTART.md) for the one-time VPS
configuration and permanent commands. Use [DEPLOYMENT_SAFETY.md](DEPLOYMENT_SAFETY.md)
for backups, existing-volume checks, failed-upgrade recovery and release gates.

From `odoo-19.0`, after configuration and release validation:

```bash
# Existing client DB: backup, upgrade installed modules, verify, start
git pull --ff-only origin main && docker compose run --rm --build deploy-prod

# Separate fresh VPS only: create the configured DB and explicit initial apps
git pull --ff-only origin main && docker compose run --rm --build deploy-new
```

The one-off Docker job handles build, guarded deployment and startup after the pull. Production
never creates a replacement database, installs new modules or uninstalls existing
ones. The fresh installer refuses an existing database/service. Configure
`NEW_INSTALL_MODULES` separately from production; these initial choices are
ignored on later updates.

Apps is password protected, including for administrators, through
`elsx_client_restrictions`. New installations must explicitly include that addon.
Production refuses a missing guard instead of silently installing it.

Ordinary `docker compose up -d --build` does not upgrade database schemas.
Do not use the older all-database refresh, CE-profile installation or
reinstall-recovery commands for routine client updates. Never delete client
volumes. No production release is approved until the restored-client and
Linux Docker rollout gates pass.

Keep existing VPS credentials, project names and volume identities unchanged.
Never commit client data, backups or secrets to Git. Retain an encrypted
database-plus-filestore backup and its encryption secret off the VPS.

---

## 🏗️ System Architecture & Tech Stack

This project uses Odoo 19.0 as its ERP/CRM engine, with PostgreSQL-backed messaging
queues and private ERP Bus notifications. The WhatsApp Node relay is migration-only.

### Core Technologies
- **Backend ERP**: Odoo 19.0 Community Edition (Dockerized)
- **Database**: PostgreSQL 15 in the default Compose stack
- **Real-Time Engine**: Odoo ERP Bus; messaging dispatch uses persistent queues
- **Frontend Framework**: OWL 2.0 (Odoo Web Library) & Native JS
- **API Integrations**: Meta / WhatsApp Cloud API v19.0+

### Key Connection Points
1. **ERP Bus and legacy relay**:
   - ERP Bus notifies authorized inbox sessions; it does not send bulk messages to Meta.
   - The WhatsApp sidecar is excluded from default startup. Keep an existing relay
     until callback routing and pending events have been verified and migrated.
2. **Meta Cloud Webhooks**:
   - Meta sends inbound messages and status updates (delivered/read) directly to `controllers/whatsapp_webhook.py`.
   - Signed events are persisted before acknowledgment, processed with account-scoped
     deduplication, and published to authorized inbox sessions through ERP Bus.
3. **Local Partner Autocomplete**:
   - Replaces Odoo's default paid IAP credit system. Intercepts `/iap/autocomplete` requests and routes them through a local fuzzy-search database.

---

## 📦 Custom Module Ecosystem

The `custom_addons` directory contains the proprietary logic developed specifically for FibraFRP. 
Third-party/OCA modules should live in `third_party_addons`, or in another
mounted directory added through `ODOO_EXTRA_ADDONS_PATH`. The default Docker and
local configs load:

```text
addons, odoo/addons, custom_addons, custom_addons/elsx_stubs, third_party_addons
```

Before installing outside modules, run:

```bash
python deploy/audit_addons_ready.py
```

The audit confirms every manifest is reachable from `addons_path` and that
manifest dependencies resolve against the official, custom, stub, and
third-party addon roots.

### Updates and Additional Apps

Use `docker compose run --rm --build deploy-prod` after pulling the reviewed revision,
not an automatic startup install flag. The host wrappers remain available as alternatives.
Put reviewed custom/third-party addons in the image's configured addon roots.
Installed addons are upgraded; newly added addons are not installed automatically.
A missing dependency blocks production preflight.

To intentionally add a new app to an existing client, first take a matching
database/filestore backup and test the app on an isolated restored copy. An
authorized administrator can then unlock Apps and use native Odoo installation
controls during an approved maintenance window. The permanent Apps guard cannot
be removed through those controls. See the quickstart for the password gate's
scope and expiry.

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
3. **Upgrade modules**:
   - For a safe all-module Docker refresh, run the deployment update script for the target database.
   - The update scripts now expand `all` to every installed module in each database before calling Odoo.
   - For UI-only testing, turn on Developer Mode, go to Apps -> Update Apps List, then upgrade the changed module.

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
