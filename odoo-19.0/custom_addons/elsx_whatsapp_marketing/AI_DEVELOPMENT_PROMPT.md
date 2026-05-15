# MASTER DEVELOPMENT PROMPT — ELSX WhatsApp Marketing Module
# Feed this ENTIRE file + CODEBASE_STATE.md to any AI coding assistant.

---

## YOUR ROLE
You are an elite Odoo 19 enterprise developer and Meta Cloud API specialist. You are working on the `elsx_whatsapp_marketing` custom module inside an Odoo 19.0 codebase. Your goal is to transform this module into an enterprise-grade WhatsApp Business Platform that surpasses Twilio and WATI in features, performance, and UX.

## CRITICAL RULES — NEVER BREAK THESE
1. **NEVER modify Odoo core modules** (`base`, `web`, `mail`, `crm`, `sale`, `account`). Only work inside `custom_addons/elsx_whatsapp_marketing/`.
2. **Use Odoo's inheritance** (`_inherit`) when extending core models like `res.partner`, `sale.order`, `account.move`.
3. **Test every Python change** by restarting Odoo with `--update=elsx_whatsapp_marketing`. Validate XML changes don't break module install.
4. **Preserve all existing functionality**. Don't delete working features. Fix bugs surgically — don't rewrite entire files unless absolutely necessary.
5. **All Meta Cloud API calls** must go through `whatsapp.account.send_message()` as the single gateway. Don't scatter raw `requests.post()` calls across models.
6. **All bus notifications** must use channel `'elsx_whatsapp_channel'` — the widget only subscribes to this.
7. **Security model access** must be declared in `security/ir.model.access.csv` for every new model.
8. **New assets** (JS/CSS/XML) must be registered in `__manifest__.py` under `web.assets_backend`.

## REFERENCE FILE
Read `CODEBASE_STATE.md` in this same directory FIRST. It contains:
- Complete module file structure with line counts
- Core architecture diagram and data flow
- All 12 verified bugs with exact file:line references
- Missing Meta API parameters table
- send_message() gateway signature
- Cron job inventory (including 3 missing crons)

---

## PHASE 1: BUG FIXES (Do These FIRST — In This Exact Order)

### 1.1 Fix `_logger` crash in `whatsapp_campaign_participant.py`
- Add `import logging` and `_logger = logging.getLogger(__name__)` at top of file
- This is a 2-line fix that prevents the entire drip campaign cron from crashing

### 1.2 Fix double bot trigger in `whatsapp_message.py`
- DELETE lines 126-133 (the `for msg in messages: if msg.direction == 'inbound'...` block in `create()`)
- The webhook handler at `whatsapp_webhook.py:380-406` already handles bot triggering CORRECTLY (it tries rules first, then flows only if no rule fired)
- The model `create()` fires flows a SECOND time unconditionally, causing duplicate bot replies

### 1.3 Fix bus channel mismatch in `whatsapp_webhook.py`
- At line 509-513, change:
  ```python
  env['bus.bus']._sendone(
      f'whatsapp_chat_{msg.chat_id_ref.id}',  # WRONG channel
      'whatsapp_status_update',
      {'chat_id': msg.chat_id_ref.id, 'message_id': msg.id, 'status': new_status}
  )
  ```
  To:
  ```python
  env['bus.bus']._sendone(
      'elsx_whatsapp_channel',  # CORRECT — matches widget subscription
      'whatsapp_status_update',
      {'chat_id': msg.chat_id_ref.id, 'message_id': msg.id, 'status': new_status}
  )
  ```

### 1.4 Remove 2 duplicate `action_sync_templates` from `whatsapp_account.py`
- DELETE the method defined at lines 268-330 (first version — basic, no language normalization)
- DELETE the method defined at lines 440-499 (second version — has language normalization but gets shadowed)
- KEEP the method at lines 771-864 (third version — most complete with button extraction)
- THEN ADD to the kept version (L771+): `meta_template_name`, `language_code`, and `_normalize_language_selection()` calls from the L440 version. Specifically, add these to the `vals` dict:
  ```python
  'meta_template_name': name,
  'language_code': language,
  'language': self.env['whatsapp.template']._normalize_language_selection(language),
  ```

### 1.5 Remove duplicate `action_duplicate` from `whatsapp_template.py`
- DELETE lines 585-604 (the second definition that uses context defaults)
- KEEP lines 515-532 (the first definition that uses `self.copy()` — preserves all related records)

### 1.6 Fix `action_send` kwargs crash in `whatsapp_message.py`
- Replace lines 182-190 with safe dispatch logic:
  ```python
  kwargs = {
      'existing_message': record,
      'partner_id': record.partner_id.id if record.partner_id else False,
  }
  if record.message_type == 'template':
      kwargs['template'] = payload
  elif record.message_type == 'interactive':
      kwargs['interactive'] = payload
  elif record.message_type == 'text':
      kwargs['body'] = payload.get('body', record.body)
  elif record.message_type in ('image', 'video', 'document', 'audio'):
      kwargs['body'] = record.caption or record.body
      # media_url contains Meta handle for inbound, media_file for outbound
      if record.media_file:
          kwargs['media_file'] = record.media_file
          kwargs['media_filename'] = record.media_filename
      elif record.media_url:
          kwargs['media_url'] = record.media_url

  record.account_id.send_message(
      record.phone_number,
      message_type=record.message_type,
      **kwargs
  )
  ```

### 1.7 Build media upload pipeline in `whatsapp_account.py`
- Add method `_upload_media_to_meta(self, binary_data, filename, media_type)`:
  - Decode base64 binary
  - POST to `https://graph.facebook.com/{api_version}/{phone_number_id}/media`
  - Return media handle ID
- In `send_message()`, before building the API payload, check if `kwargs.get('media_file')` exists. If so, upload it and use the returned handle.

### 1.8 Fix `campaign_id` kwarg in `whatsapp_account.send_message()`
- In the `vals` dict construction (around line 576-584), add:
  ```python
  'campaign_id': kwargs.get('campaign_id', False),
  ```
- This ensures campaign analytics track correctly

### 1.9 Fix `cr.commit()` in `whatsapp_campaign.py`
- Replace `self.env.cr.commit()` calls at lines 523, 527, 534 with proper pattern:
  ```python
  # Instead of self.env.cr.commit(), use:
  # For cron context, Odoo auto-commits after each cron run.
  # Process in smaller batches and let the cron framework handle commits.
  ```
- Or wrap each message send in `with self.env.cr.savepoint():`

### 1.10 Fix phone normalization
- Add `default_country_code` field to `whatsapp.account` (Char, default='91')
- In `whatsapp_message.py:139` and `send_whatsapp_wizard.py:30-31`, replace hardcoded `'91'` with account's `default_country_code`

---

## PHASE 2: SECURITY & RELIABILITY

### 2.1 Webhook HMAC Signature Verification
- Add `app_secret` field to `whatsapp.account`
- In `whatsapp_webhook.py._handle_post()`, before processing:
  ```python
  import hmac, hashlib
  signature = request.httprequest.headers.get('X-Hub-Signature-256', '')
  expected = 'sha256=' + hmac.new(
      account.app_secret.encode(), raw_body, hashlib.sha256
  ).hexdigest()
  if not hmac.compare_digest(signature, expected):
      return Response('Invalid signature', status=403)
  ```

### 2.2 Exponential Backoff Retry Engine
- Add fields to `whatsapp.message`: `retry_count` (Integer, default=0), `next_retry_at` (Datetime)
- In `send_message()`, on failure with retryable HTTP status (429, 500, 503):
  ```
  Attempt 1: immediate
  Attempt 2: 1s + random jitter
  Attempt 3: 4s + random jitter
  Attempt 4: 16s + random jitter
  Attempt 5: 64s + random jitter → then mark as permanently failed
  ```
- Add cron job to retry messages where `next_retry_at <= now() AND retry_count < 5`

### 2.3 Rate Limiter
- Add `rate_limit_tps` field to `whatsapp.account` (Integer, default=80)
- Implement simple token bucket in `send_message()`:
  ```python
  # Check messages sent in last second
  recent = self.env['whatsapp.message'].search_count([
      ('account_id', '=', self.id),
      ('sent_date', '>=', fields.Datetime.now() - timedelta(seconds=1)),
      ('status', 'in', ['sent', 'delivered', 'read']),
  ])
  if recent >= self.rate_limit_tps:
      # Queue instead of send
      message.write({'status': 'queued'})
      return message
  ```

---

## PHASE 3: UX SUPREMACY

### 3.1 Fix `setInterval` Memory Leak in `whatsapp_widget.js`
- Store the interval ID and clear it on service destruction:
  ```javascript
  start() {
      this._refreshInterval = setInterval(() => { ... }, 10000);
  }
  destroy() {
      if (this._refreshInterval) clearInterval(this._refreshInterval);
      super.destroy();
  }
  ```

### 3.2 Add Missing Cron Jobs
Add to `data/whatsapp_cron.xml`:
```xml
<!-- Process Scheduled Messages -->
<record id="ir_cron_process_scheduled_messages" model="ir.cron">
    <field name="name">WhatsApp: Process Scheduled Messages</field>
    <field name="model_id" ref="model_whatsapp_scheduled_message"/>
    <field name="state">code</field>
    <field name="code">model._cron_send_scheduled()</field>
    <field name="interval_number">5</field>
    <field name="interval_type">minutes</field>
    <field name="active" eval="True"/>
</record>

<!-- Cleanup Old Webhook Logs -->
<record id="ir_cron_cleanup_webhook_logs" model="ir.cron">
    <field name="name">WhatsApp: Cleanup Old Webhook Logs</field>
    <field name="model_id" ref="model_whatsapp_webhook_log"/>
    <field name="state">code</field>
    <field name="code">model._cron_cleanup_old_logs()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
    <field name="active" eval="True"/>
</record>

<!-- Retry Failed Messages -->
<record id="ir_cron_retry_failed_messages" model="ir.cron">
    <field name="name">WhatsApp: Retry Failed Messages</field>
    <field name="model_id" ref="model_whatsapp_message"/>
    <field name="state">code</field>
    <field name="code">model._cron_retry_failed()</field>
    <field name="interval_number">2</field>
    <field name="interval_type">minutes</field>
    <field name="active" eval="True"/>
</record>
```

### 3.3 Wire Compliance to Send Pipeline
In `whatsapp_account.send_message()`, before sending, check:
```python
# Check DND list
policy = self.env['whatsapp.compliance.policy'].search([
    ('account_id', '=', self.id), ('active', '=', True)
], limit=1)
if policy and policy.respect_dnd_list:
    if partner and partner in policy.dnd_contact_ids:
        raise UserError("Contact is on Do Not Contact list.")

# Check quiet hours
if policy:
    quiet_hours = self.env['whatsapp.quiet.hours'].search([
        ('policy_id', '=', policy.id), ('active', '=', True)
    ])
    # ... check current time against quiet hours
```

---

## PHASE 4: ADVANCED FEATURES (Future)

### 4.1 OWL 2.0 Infinity Inbox
- Replace `_compute_history_html` with client-side OWL component
- Virtual scrolling — render only visible messages
- Lazy load on scroll-up
- Zero-flicker via bus-only updates

### 4.2 Multi-Agent Assignment
- New model `whatsapp.agent.assignment` (agent_id, chat_id, assigned_at)
- Round-robin auto-assignment on new inbound chat
- Manual transfer between agents

### 4.3 Node.js Sidecar
- Standalone service for: webhook reception (10K+ TPS), WebSocket fan-out, media transcoding
- Redis Pub/Sub bridge to Odoo
- Fallback to direct Meta API if sidecar is offline

---

## VALIDATION CHECKLIST
After each phase, verify:
- [ ] Module installs cleanly: `--init=elsx_whatsapp_marketing`
- [ ] Module updates cleanly: `--update=elsx_whatsapp_marketing`
- [ ] No Python import errors (check Odoo logs for `ImportError`, `NameError`)
- [ ] Template sync works (Account → Sync Templates button)
- [ ] Sending a text message works (Chat → type → send)
- [ ] Webhook receives inbound (send test message from WhatsApp to business number)
- [ ] Bot replies fire exactly ONCE per inbound
- [ ] Status updates (blue ticks) appear in real-time
- [ ] Campaign queue processes without `cr.commit` errors
- [ ] Drip campaign cron runs without `_logger` crash

---

## CONTEXT FILES TO READ FIRST
1. `CODEBASE_STATE.md` — Complete module state reference
2. `models/whatsapp_account.py` — Core gateway (READ FULLY)
3. `models/whatsapp_message.py` — Message model (READ FULLY)
4. `controllers/whatsapp_webhook.py` — Webhook handler (READ FULLY)
5. `static/src/js/whatsapp_widget.js` — Frontend service (READ FULLY)
6. `models/whatsapp_template.py` — Template engine (READ L1-240, L500-840)
7. `models/whatsapp_campaign.py` — Campaign engine (READ L380-534)
