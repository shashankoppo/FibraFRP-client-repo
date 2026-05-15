# ELSX WhatsApp Marketing — Codebase State Reference
## Module: `elsx_whatsapp_marketing` | Odoo 19.0 | v19.0.2.6.0

---

## 1. MODULE STRUCTURE

```
elsx_whatsapp_marketing/
├── __manifest__.py              # Module manifest, depends: base, crm, contacts, mail, sale, account
├── __init__.py
├── controllers/
│   └── whatsapp_webhook.py      # 729 lines — Meta Cloud API webhook receiver + media proxy
├── models/
│   ├── whatsapp_account.py      # 1084 lines — Core API config, send_message gateway, template sync, sample generator
│   ├── whatsapp_message.py      # 204 lines — Message model, action_send, auto-partner linking
│   ├── whatsapp_chat.py         # 608 lines — Conversation model, _compute_history_html, AI draft reply
│   ├── whatsapp_template.py     # 840 lines — Template CRUD, Meta submission, preview, variables, carousel cards
│   ├── whatsapp_campaign.py     # 562 lines — Campaign engine, queue processor, global cron, A/B stubs
│   ├── whatsapp_campaign_participant.py # 68 lines — Drip campaign participant + step processor
│   ├── whatsapp_campaign_step.py      # ~30 lines — Campaign step (delay + template/text)
│   ├── whatsapp_bot.py          # ~100 lines — Bot rules (keyword → action)
│   ├── whatsapp_bot_flow.py     # 612 lines — Multi-step bot flows with trigger engine
│   ├── whatsapp_analytics.py    # 393 lines — SQL VIEW for message stats + dashboard compute methods
│   ├── whatsapp_compliance.py   # 275 lines — GDPR policies, consent logs, quiet hours, DND lists
│   ├── whatsapp_scheduling.py   # 283 lines — Scheduled messages with timezone + recurrence
│   ├── whatsapp_contact.py      # ~40 lines — WhatsApp contact extension
│   ├── whatsapp_contact_segment.py # ~220 lines — Contact segmentation engine
│   ├── whatsapp_media_library.py   # ~240 lines — Reusable media assets
│   ├── whatsapp_quick_reply.py     # ~25 lines — Quick reply templates
│   ├── whatsapp_sample_template.py # ~500 lines — Industry sample templates
│   ├── whatsapp_webhook_log.py     # 29 lines — Webhook audit log model
│   ├── whatsapp_chat_note.py       # ~25 lines — Internal notes on chats
│   ├── res_partner.py           # ~60 lines — Partner extension (whatsapp_opted_in, etc.)
│   ├── sale_order.py            # ~60 lines — Sale order WhatsApp notifications
│   ├── account_move.py          # ~50 lines — Invoice WhatsApp notifications
│   └── crm_lead.py             # ~30 lines — CRM lead WhatsApp integration
├── views/
│   ├── whatsapp_chat_views.xml         # 38742 bytes — Main chat UI (sidebar + chat + profile panel)
│   ├── whatsapp_campaign_views.xml     # 16504 bytes — Campaign form/tree/kanban
│   ├── whatsapp_menu.xml               # 13566 bytes — Full menu structure
│   ├── whatsapp_account_views.xml      # 11028 bytes — Account config form
│   ├── whatsapp_compliance_views.xml   # 10052 bytes — Compliance/GDPR views
│   ├── whatsapp_template_views.xml     # 8086 bytes — Template editor + preview
│   ├── whatsapp_bot_flow_views.xml     # 6732 bytes — Bot flow builder
│   ├── whatsapp_scheduling_views.xml   # 5131 bytes — Scheduled message views
│   ├── whatsapp_message_views.xml      # 5037 bytes — Message log views
│   └── [7 more view files]
├── static/src/
│   ├── css/whatsapp.css                # Main stylesheet (glassmorphic theme)
│   ├── css/whatsapp_bot_flow_builder.css
│   ├── js/whatsapp_widget.js           # 425 lines — OWL service for real-time + chat interactions
│   ├── js/whatsapp_bot_flow_builder.js # Visual flow builder
│   ├── js/whatsapp_dashboard.js        # Dashboard client action
│   └── xml/whatsapp_dashboard.xml      # Dashboard template
├── wizard/
│   ├── send_whatsapp_wizard.py         # 127 lines — Send message wizard (template/text/media)
│   ├── whatsapp_import_wizard.py       # ~130 lines — Contact import from CSV
│   └── whatsapp_new_chat_wizard.py     # ~50 lines — New chat dialog
├── security/
│   ├── whatsapp_security.xml           # Security groups
│   └── ir.model.access.csv            # ACL rules
└── data/
    ├── whatsapp_cron.xml              # 2 crons: drip campaigns (15min) + broadcast queue (1min)
    └── whatsapp_templates.xml         # Default data
```

---

## 2. CORE ARCHITECTURE

### Data Flow
```
[User/Campaign] → send_message() → Meta Cloud API → Webhook → _process_inbound_message() → Bus → Widget
     ↓                                                                    ↓
  whatsapp.message (PostgreSQL)                              whatsapp.webhook.log (audit)
     ↓
  whatsapp.chat (conversation grouping)
```

### Key Models & Relationships
- `whatsapp.account` → has_many → `whatsapp.template`, `whatsapp.chat`, `whatsapp.bot.flow`
- `whatsapp.chat` → has_many → `whatsapp.message` (via `chat_id_ref`)
- `whatsapp.campaign` → has_many → `whatsapp.message` (via `campaign_id`)
- `whatsapp.campaign` → has_many → `whatsapp.campaign.participant` → links to `whatsapp.campaign.step`
- `whatsapp.template` → has_many → `whatsapp.template.variable`, `whatsapp.template.card`
- `whatsapp.bot.flow` → has_many → `whatsapp.bot.flow.step`

### Meta Cloud API Integration Points
- **Outbound:** `whatsapp.account.send_message()` → POST `/{phone_id}/messages`
- **Inbound:** `/whatsapp/webhook` controller → `_handle_post()` → `_process_inbound_message()`
- **Status:** Webhook → `_handle_status_update()` → updates `whatsapp.message.status`
- **Templates:** `action_sync_templates()` → GET `/{waba_id}/message_templates`
- **Template Submit:** `action_submit_to_meta()` → POST `/{waba_id}/message_templates`
- **Media Proxy:** `/whatsapp/media/<media_id>` → proxies Meta media to browser

---

## 3. KNOWN BUGS (12 Total — All Verified)

| ID | File:Line | Severity | Description |
|----|-----------|----------|-------------|
| A1 | `whatsapp_message.py:189` | 🔴 CRITICAL | `**payload` kwargs splat crashes on media/template messages with unexpected keys |
| A2 | `whatsapp_account.py:268,440,771` | 🔴 CRITICAL | `action_sync_templates` defined 3 TIMES — only L771 executes, missing language normalization |
| A3 | `whatsapp_template.py:515,585` | 🟠 HIGH | `action_duplicate` defined 2 TIMES — L585 shadows L515, loses variable/card data |
| A4 | `whatsapp_webhook.py:509` → `widget.js:26` | 🔴 CRITICAL | Bus sends to `whatsapp_chat_{id}` but widget listens on `elsx_whatsapp_channel` — status updates lost |
| A5 | `whatsapp_message.py:128` + `webhook.py:402` | 🔴 CRITICAL | Bot flows triggered TWICE per inbound message — duplicate bot replies |
| A6 | `whatsapp_campaign_participant.py:49` | 🔴 CRITICAL | `_logger` used but NEVER imported — crashes entire drip campaign cron |
| A7 | `whatsapp_campaign.py:523,527,534` | 🟠 HIGH | Direct `self.env.cr.commit()` breaks Odoo transaction model |
| A8 | `whatsapp_widget.js:30-36` | 🟡 MEDIUM | `setInterval` never cleared — memory leak on repeated navigation |
| A9 | `whatsapp_widget.js:78-90` | 🟡 MEDIUM | Raw `fetch()` without CSRF token — will break with CSRF hardening |
| A10 | `whatsapp_message.py:179-180` | 🔴 CRITICAL | No media upload pipeline — outbound media messages silently fail |
| A11 | `whatsapp_message.py:139`, `wizard.py:30` | 🟡 MEDIUM | Phone normalization hardcodes India `91` prefix |
| A12 | `whatsapp_campaign_participant.py:46` | 🟠 HIGH | `campaign_id` kwarg silently dropped by `send_message()` — analytics broken |

---

## 4. MISSING META API PARAMETERS

| Parameter | Where Needed | Current State |
|-----------|-------------|---------------|
| `X-Hub-Signature-256` HMAC verify | Webhook POST handler | **NOT IMPLEMENTED** — security hole |
| `context.message_id` | Send reply messages | Not sent — replies appear as new messages |
| `preview_url: true` | Text messages with URLs | Not set — no link previews |
| `allow_category_change` | Template submission | Missing from payload |
| `code_expiration_minutes` | Auth template submission | Missing |
| `biz_opaque_callback_data` | send_message payload | Not implemented |
| Conversation billing data | Status webhook handler | Parsed but never stored |
| Template quality score | Quality webhook handler | Logged but not written to record |

---

## 5. send_message() GATEWAY SIGNATURE
```python
# whatsapp_account.py — THE central dispatch method
def send_message(self, to_number, message_type='text', **kwargs):
    # kwargs accepted: body, template, interactive, template_record,
    #                  template_name, language_code, partner_id, existing_message
    # kwargs NOT accepted (silently dropped): campaign_id, media_file, context
```

---

## 6. CRON JOBS
| Cron | Model | Method | Interval |
|------|-------|--------|----------|
| Process Drip Campaigns | `whatsapp.campaign.participant` | `process_drip_campaigns()` | Every 15 min |
| Process Broadcast Queue | `whatsapp.campaign` | `_cron_process_global_queue()` | Every 1 min |
| _(MISSING)_ Scheduled Messages | `whatsapp.scheduled.message` | _(no cron defined)_ | _(never runs)_ |
| _(MISSING)_ Webhook Log Cleanup | `whatsapp.webhook.log` | _(no method)_ | _(never runs)_ |
| _(MISSING)_ Message Cleanup | `whatsapp.message` | `_cleanup_old_messages()` exists but no cron | _(never runs)_ |
