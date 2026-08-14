# WhatsApp Product Capability Matrix

Audited on 2026-08-14 against the current module, Meta's official WhatsApp
Business Platform collection, and current public product documentation from
AiSensy, WATI, and Twilio.

## Current Coverage

| Capability | Status | Current implementation |
| --- | --- | --- |
| Cloud API accounts and webhooks | Covered | Multi-account credentials, health snapshots, webhook and API logs |
| Templates | Covered | Sync, approval state, variables, media headers, buttons, carousel cards, audits |
| Broadcast campaigns | Covered | Segments, scheduling, batching, A/B variants, retries, delivery/read metrics |
| Campaign automation | Covered | Drip steps, participants, reply rules, CRM/form/payment/assignment actions |
| Shared team inbox | Covered | Assignment, notes, states, snooze/resolve, SLA state, agent performance |
| Bot automation | Covered | Keyword rules, visual flow graph, branches, logs, tests, human handoff |
| CRM and ERP integration | Covered | Contacts, leads, quotations, orders, invoices, reminders, payment links |
| Consent and compliance | Covered | Opt-in/out, consent logs, quiet hours, retention policies, DND controls |
| Analytics and diagnostics | Covered | Campaign, inbox, agent, webhook, account health, cost and delivery reporting |
| Media handling | Covered | Upload/download, protected Meta URL recovery, media library, size validation |
| Contact import | Covered in 19.0.4.1.0 | Flexible CSV/XLS/XLSX, preview, duplicates, tags, consent, attributes, row report |
| Interactive messages | Covered | Buttons, lists, CTA URL, products, product lists, catalog payloads |
| Inbound rich events | Covered | Reactions, location, contacts, stickers, orders, edits, revocations, Flow replies |

## Remaining Product Gaps

| Priority | Capability | Gap |
| --- | --- | --- |
| P0 | Regression coverage | Large operational surface still needs model, webhook, campaign, bot, and security suites |
| P0 | Import/export governance | Add scheduled exports, import audit records, and administrator retention controls |
| P1 | CTWA attribution | Persist Meta referral/ad identifiers and connect them to lead/campaign ROI |
| P1 | Click tracking | First-party tracked links and per-recipient click events are not complete |
| P1 | Native Meta Flows lifecycle | Inbound Flow replies exist; create, publish, version, endpoint, and health tooling is incomplete |
| P1 | Commerce operations | Catalog payloads and inbound order creation exist; catalog sync, checkout state, refunds, and reconciliation remain |
| P1 | Quality operations | Add CSAT/CX scoring, SLA escalation rules, transcript export, and scheduled inbox reports |
| P2 | WhatsApp calling | Calling consent, inbound/outbound call lifecycle, recording policy, and call analytics are absent |
| P2 | Multi-channel inbox | Instagram, Messenger, RCS, SMS, and email are outside this WhatsApp-focused module |
| P2 | Mobile agent experience | Responsive web inbox exists; there is no dedicated native agent application |

## Compatibility Rules

1. Never replace an existing relation table or reuse a field for a different data type.
2. New database fields must be nullable or have a backward-compatible default.
3. Existing contacts, messages, campaigns, templates, credentials, and attachments must not be deleted by upgrades.
4. Imports update missing data by default, process rows in savepoints, and preserve existing tags.
5. Every production upgrade uses encrypted database and filestore backups before module loading.
6. New Meta capabilities must retain the raw webhook/API payload for forward compatibility and diagnostics.

## Reference Sources

- Meta WhatsApp Business Platform: https://www.postman.com/meta/whatsapp-business-platform/overview
- Meta Cloud API collection: https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api
- AiSensy features: https://aisensy.com/features
- WATI platform overview: https://support.wati.io/en/articles/11375155-what-is-wati-platform-overview-and-key-features
- WATI feature comparison: https://www.wati.io/en/pricing-comparison/
- Twilio WhatsApp feature support: https://help.twilio.com/articles/360058369633-Which-WhatsApp-features-are-supported-by-the-Twilio-API-for-WhatsApp-
- Twilio WhatsApp Flows: https://www.twilio.com/docs/content/whatsapp-flows
- Twilio catalogs: https://www.twilio.com/docs/content/twilio-catalog
