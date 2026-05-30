# WhatsApp + AI Stabilization Baseline

Captured during the stabilization pass on 2026-05-25.

## Active Scope

- Active installed custom modules observed in the database: `elsx_ai_marketing`, `elsx_client_restrictions`, `elsx_partner_autocomplete`, `elsx_whatsapp_marketing`.
- AI addon directories exist, but only `elsx_ai_marketing` is installed. `elsx_ai_ocr` and `elsx_bank_ai` remain uninstalled.
- The active stabilization work is scoped to `elsx_whatsapp_marketing` plus the installed `elsx_ai_marketing` bridge so draft-only AI behavior stays aligned.

## Risk Inventory

- Worktree is broadly dirty, including many core addon manifest and metadata changes. Those unrelated changes are intentionally not touched by this pass.
- WhatsApp frontend assets were heavy and previously loaded remote backend assets for fonts and Socket.IO.
- Team Inbox history rendering previously defaulted to 100 messages and could recompute large HTML fragments on chat switches.
- Existing AI modules contained placeholder/demo behavior, direct synchronous API calls, and direct record writes. They remain inactive until converted.
- Campaign/message crons needed duration and queue-size logging for operational visibility.

## Stabilization Defaults

- `whatsapp.realtime.mode`: `bus`
- `whatsapp.history.initial.limit`: `50`
- `elsx_ai.enabled`: `False`
- `elsx_ai.auto_write`: `False`

## Recovery Rules

- Do not add new WhatsApp/AI features until static checks, module upgrade, and browser smoke checks are green.
- All AI output must be traceable through `elsx.ai.job`; no automatic customer send is allowed.
- Sidecar Socket mode is optional and only used when explicitly selected in Settings.
- Keep custom modules intact and avoid changes outside the active stabilization scope unless explicitly approved.
