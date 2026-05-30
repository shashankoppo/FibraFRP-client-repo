# AiSensy Parity And Delivery Audit

Date: 2026-05-27

## What Was Safely Fixed

- Dashboard live database metrics are active after restart.
- Dashboard reply and click rates are capped and contact-based so inbound volume cannot show impossible rates above 100%.
- Dashboard AI health now counts `done`, `reviewed`, and `applied` jobs instead of the non-existent `completed` job state.
- Production WhatsApp forms were added for Lead Enquiry, Support Ticket, Catalogue Request, Quote Request, and Feedback.
- Five inactive FiberaFRP business-flow blueprints were added for full business routing, quote qualification, support/warranty, payment/order follow-up, and feedback.
- The detailed user guide now includes step-by-step operating instructions, button meanings, workflow examples, form guidance, flow step meanings, and client demo checks.
- Static checks passed for Python, JavaScript, XML parsing, and access CSV model references.

## Live System Findings

- Dashboard RPC works, but the sync state is `Stale` because no recent webhook activity has arrived for more than 2 hours.
- One WhatsApp account is connected, but commerce setup is incomplete:
  - Missing Meta Catalog ID.
  - Missing Default Product Retailer ID.
  - Missing Shop / Catalogue URL.
  - Missing Commerce Manager URL.
- There are 39 templates, but only 13 are approved. Most advanced template examples are still draft records.
- Some approved templates still need button configuration review before client delivery.
- There are 7 active flows plus 5 inactive production blueprints. The new blueprints have zero flow-health warnings and must be reviewed before activation.
- Forms now include 5 production-ready templates:
  - Lead Enquiry: 9 fields.
  - Support Ticket: 8 fields.
  - Catalogue Request: 6 fields.
  - Quote Request: 9 fields.
  - Feedback: 5 fields.
- One older AI draft flow remains active and should still be reviewed because it was not changed without business approval.
- Payment links are enabled through Odoo invoice links, but there is no in-chat payment reconciliation view or payment status callback flow.
- AI is enabled and the default provider is NVIDIA NIM with successful test status. Other provider examples are present but missing API keys or base URLs.
- AI jobs are auditable and draft-only. There are historical failed jobs that should be reviewed from AI Jobs.
- Compliance policy records are empty, so consent/DND rules are not yet set up as client-ready policy data.
- Diagnostic snapshots are empty, so regular health snapshots should be generated before handover.

## AiSensy-Parity Gaps Still Requiring Configuration Or Confirmation

- Click-to-WhatsApp Ads Manager: current system tracks wa.me/source attribution, but does not create or manage Meta ads directly.
- WhatsApp payments: current system sends manual/Odoo invoice or quotation links, but does not yet reconcile Razorpay/PayU/UPI status inside WhatsApp profile views.
- Catalog commerce: backend and flow fields exist, but live account catalog/shop IDs are empty, so catalog/product sending cannot work until Meta Commerce data is provided.
- Forms/webviews: production form templates now exist with consent, file/location fields where useful, and CRM mapping defaults. Remaining work is user acceptance testing and client-specific wording/branding.
- Retargeting: campaigns and segments exist, but there is no polished "retarget non-clickers/non-payers/form abandoners" wizard yet.
- Flow builder: inactive business blueprints now cover the main customer journeys. User acceptance still needs end-to-end human testing for each node type after catalog/shop/payment data is configured.
- Template generation: AI draft support exists, but real Meta submission still needs approved template samples, media handles, and button validation.
- Guided onboarding: guide panels exist in several areas, but final client delivery should include a guided setup checklist per screen and "next best action" buttons tied to actual missing account/template/flow data.

## Do Not Auto-Change Without Approval

- Do not create or send live campaigns.
- Do not submit or modify approved Meta templates.
- Do not seed catalog IDs or product retailer IDs without the client's Meta Commerce Manager values.
- Do not activate or deactivate live flows without business confirmation.
- Do not enable AI auto-send or AI auto-write.
- Do not alter Odoo core or unrelated dirty worktree files.

## Recommended Next Delivery Actions

1. Fill commerce fields on the WhatsApp account from Meta Commerce Manager.
2. Review and fix approved template buttons, especially templates with invalid button warnings.
3. Review the older active AI draft flow and either repair or deactivate it after business confirmation.
4. Review the new inactive business-flow blueprints, assign final users/teams, test with an internal number, then activate only approved flows.
5. Create production-ready campaign presets only after opt-in audience and approved template confirmation.
6. Generate a diagnostic snapshot and review webhook freshness before client demo.
7. Run a human smoke test: inbox, template, document header, form link, payment link, catalog/product message, flow branch, campaign test send, dashboard refresh.
