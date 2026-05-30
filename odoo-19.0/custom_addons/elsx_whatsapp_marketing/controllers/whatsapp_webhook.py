import odoo
from odoo import http, fields, api
from odoo.http import request, Response
from odoo.modules.registry import Registry
import json
import hashlib
import hmac
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

_logger = logging.getLogger(__name__)

WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix='wa-webhook')


def _mask_secret(value):
    value = str(value or '')
    if not value:
        return ''
    if len(value) <= 8:
        return '***'
    return f"{value[:3]}...{value[-3:]}"


class WebhookSerializationRetry(Exception):
    """Raised when a webhook row is busy and the event should be retried."""


def _get_env(db_name=None, payload=None):
    """Get a fresh Odoo environment for webhook context (no request session)"""
    db_name = db_name or request.session.db or getattr(request, 'db', None)

    from odoo.service import db as db_service
    dbs = db_service.list_dbs()

    # 0. Multi-tenant phone_number_id matching
    if payload:
        try:
            meta = payload.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('metadata', {})
            phone_number_id = meta.get('phone_number_id')
            if phone_number_id:
                for db in dbs:
                    try:
                        registry = Registry(db)
                        if 'whatsapp.account' in registry.models:
                            cr = registry.cursor()
                            env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                            if env['whatsapp.account'].sudo().search_count([('phone_number_id', '=', phone_number_id)]):
                                return env, cr, db
                            cr.close()
                    except Exception:
                        continue
        except Exception:
            pass

    # 1. Try specified/guessed DB
    if db_name and db_name in dbs:
        try:
            registry = Registry(db_name)
            if 'whatsapp.account' in registry.models:
                cr = registry.cursor()
                return api.Environment(cr, odoo.SUPERUSER_ID, {}), cr, db_name
        except Exception:
            pass

    # 2. Iterate through all DBs, looking for the marked "Primary Webhook DB"
    for db in dbs:
        try:
            registry = Registry(db)
            if 'whatsapp.account' in registry.models:
                cr = registry.cursor()
                env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                # Check if this DB is marked as primary
                primary_acc = env['whatsapp.account'].sudo().search([('is_primary_webhook_db', '=', True)], limit=1)
                if primary_acc:
                    return env, cr, db
                cr.close()
        except Exception:
            continue

    # 3. Final fallback: search for ANY DB with our model
    for db in dbs:
        try:
            registry = Registry(db)
            if 'whatsapp.account' in registry.models:
                cr = registry.cursor()
                return api.Environment(cr, odoo.SUPERUSER_ID, {}), cr, db
        except Exception:
            continue

    # 4. Critical failure
    return None, None, None


def _find_account(env, account_id, payload):
    """Find the matching WhatsApp account from the payload"""
    if account_id:
        account = env['whatsapp.account'].sudo().browse(int(account_id))
        if account.exists():
            return account

    # Try metadata phone_number_id
    try:
        meta = payload.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('metadata', {})
        phone_number_id = meta.get('phone_number_id')
        if phone_number_id:
            account = env['whatsapp.account'].sudo().search([('phone_number_id', '=', phone_number_id)], limit=1)
            if account.exists():
                return account
    except Exception:
        pass

    # Fallback: configured default account, then first active account.
    return env['whatsapp.account'].sudo()._get_default_account()


class WhatsAppWebhook(http.Controller):
    SERIALIZATION_RETRY_DELAYS = (0.05, 0.15, 0.35, 0.75)
    STATUS_ORDER = {
        'draft': 0,
        'queued': 1,
        'sent': 2,
        'delivered': 3,
        'read': 4,
    }

    def _is_serialization_failure(self, exc):
        """PostgreSQL asks for a transaction retry when concurrent webhook workers touch the same row."""
        if isinstance(exc, WebhookSerializationRetry):
            return True
        seen = set()
        current = exc
        while current and id(current) not in seen:
            seen.add(id(current))
            text = str(current)
            if (
                current.__class__.__name__ == 'SerializationFailure'
                or 'could not serialize access due to concurrent update' in text
            ):
                return True
            current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)
        return False

    # =========================================================
    # MAIN ROUTE — Handles ALL Meta webhook calls
    # =========================================================
    @http.route([
        '/whatsapp/webhook/<int:account_id>',
        '/whatsapp/webhook',
    ], type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def whatsapp_webhook(self, account_id=None, **kwargs):
        """Unified handler: GET = hub.verify, POST = event dispatch"""
        _logger.info(f'[WH-HIT] Method={request.httprequest.method} Path={request.httprequest.path} AccountID={account_id}')
        if request.httprequest.method == 'GET':
            return self._handle_verification(account_id)
        return self._handle_post(account_id)

    # =========================================================
    # GET — Webhook Verification (hub.challenge handshake)
    # =========================================================
    def _handle_verification(self, account_id):
        params = request.params
        mode = params.get('hub.mode') or params.get('hub_mode', '')
        token = params.get('hub.verify_token') or params.get('hub_verify_token', '')
        challenge = params.get('hub.challenge') or params.get('hub_challenge', '')

        _logger.info('[WH-VERIFY] mode=%s token=%s account_id=%s', mode, _mask_secret(token), account_id)

        if mode != 'subscribe' or not token or not challenge:
            return request.make_response('Bad Request', status=400)

        # DB lookup only. No hard-coded fallback verify token is accepted.
        try:
            env, cr, _ = _get_env()
            try:
                domain = [('webhook_verify_token', '=', token), ('active', '=', True)]
                if account_id:
                    domain.append(('id', '=', account_id))
                account = env['whatsapp.account'].sudo().search(domain, limit=1)
                if account.exists():
                    _logger.info(f'[WH-VERIFY] Accepted for account {account.id} ({account.name})')
                    account.sudo().write({'webhook_status': 'verified', 'webhook_last_error': False})
                    return request.make_response(challenge, headers=[('Content-Type', 'text/plain')])
            finally:
                cr.close()
        except Exception as e:
            _logger.error(f'[WH-VERIFY] DB lookup failed: {e}')

        _logger.warning('[WH-VERIFY] REJECTED - no matching account for token %s', _mask_secret(token))
        return request.make_response('Verification Failed', status=403)

    def _verify_meta_signature(self, account, raw_body, signature):
        """Validate Meta X-Hub-Signature-256 against the exact raw request body."""
        if not account:
            return False, 'No matching account', 403
        if account.skip_webhook_hmac:
            _logger.warning('[WH-HMAC] Signature check skipped for account %s (debug mode).', account.id)
            return True, None, None
        if not account.app_secret:
            account.sudo().write({
                'webhook_status': 'failed',
                'webhook_last_error': 'Missing Meta app secret for HMAC verification',
            })
            return False, 'Missing Meta app secret', 403
        if not signature:
            account.sudo().write({
                'webhook_status': 'failed',
                'webhook_last_error': 'Missing X-Hub-Signature-256 header',
            })
            return False, 'Missing signature header', 400

        if isinstance(raw_body, str):
            raw_body = raw_body.encode('utf-8')
        expected_sig = 'sha256=' + hmac.new(
            account.app_secret.encode('utf-8'),
            raw_body or b'',
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            account.sudo().write({
                'webhook_status': 'failed',
                'webhook_last_error': 'Invalid HMAC Signature',
            })
            return False, 'Invalid signature', 403
        return True, None, None

    # =========================================================
    # POST — Event Dispatch
    # =========================================================
    def _handle_post(self, account_id):
        try:
            raw_body = request.httprequest.data or b''
            raw_data = raw_body.decode('utf-8')
            payload = json.loads(raw_data)

            # Must be whatsapp_business_account object
            if payload.get('object') != 'whatsapp_business_account':
                return request.make_response('OK', status=200)

            env, cr, db_name = _get_env(payload=payload)
            if not cr:
                return request.make_response('Database Unavailable', status=503)

            try:
                with cr:
                    account = _find_account(env, account_id, payload)

                    ok, message, status = self._verify_meta_signature(
                        account,
                        raw_body,
                        request.httprequest.headers.get('X-Hub-Signature-256', ''),
                    )
                    if not ok:
                        return request.make_response(message, status=status)

                    # 1. Instantly log the webhook for queuing (WABA Best Practice)
                    # We store it as 'received' and instantly return 200 OK.
                    log_record = env['whatsapp.webhook.log'].sudo().create({
                        'account_id': account.id if account else False,
                        'event_type': 'waba_webhook',
                        'raw_payload': raw_data,
                        'status': 'received'
                    })
                    log_id = log_record.id
                    cr.commit()

                # 2. Queue webhook processing with a bounded worker pool.
                # This keeps Meta responses fast without spawning unlimited DB cursors.
                def process_webhook_thread(db_name, log_id, account_id):
                    try:
                        registry = Registry(db_name)
                        with registry.cursor() as thread_cr:
                            thread_env = api.Environment(thread_cr, odoo.SUPERUSER_ID, {})
                            thread_log = thread_env['whatsapp.webhook.log'].browse(log_id)
                            thread_acc = thread_env['whatsapp.account'].browse(account_id) if account_id else None
                            payload_json = json.loads(thread_log.raw_payload)

                            for entry in payload_json.get('entry', []):
                                for change in entry.get('changes', []):
                                    field = change.get('field', '')
                                    value = change.get('value') or {}
                                    try:
                                        self._dispatch_change(thread_env, thread_acc, field, value, thread_log.raw_payload)
                                    except Exception as dispatch_err:
                                        _logger.error(f'[WH-DISPATCH-THREAD] Failure: {dispatch_err}', exc_info=True)

                            thread_log.sudo().write({'status': 'processed'})
                            thread_cr.commit()
                    except Exception as e:
                        _logger.error(f'[WH-THREAD-CRASH] Webhook processing failed: {e}', exc_info=True)

                WEBHOOK_EXECUTOR.submit(process_webhook_thread, db_name, log_id, account.id if account else None)

                # 3. Return 200 OK instantly (< 50ms)
                return request.make_response('OK', status=200)

            except Exception as inner_err:
                _logger.error(f'[WH-INNER] Fatal processing error: {inner_err}', exc_info=True)
                return request.make_response('Processing Error', status=500)
            finally:
                cr.close()

        except json.JSONDecodeError:
            _logger.error('[WH-POST] Invalid JSON body')
            return request.make_response('Bad JSON', status=400)
        except Exception as e:
            _logger.error(f'[WH-POST] Fatal error: {e}', exc_info=True)
            return request.make_response('Internal Error', status=500)

    # =========================================================
    # DISPATCHER — Routes each "field" type to its handler
    # =========================================================
    def _dispatch_change(self, env, account, field, value, raw_data):
        """Route each webhook change to the right processor"""
        _logger.info(f'[WH-DISPATCH] field={field} account={account.id if account else None}')

        # Log every event for audit
        self._log_event(env, account, field, value, raw_data)
        self._touch_account_webhook(env, account)

        handlers = {
            'messages': self._handle_messages_field,
            'message_status': self._handle_messages_field,
            'message_status_update': self._handle_messages_field,
            'typing': self._handle_typing_event,
            'account_alerts': self._handle_account_alerts,
            'account_review_update': self._handle_account_review_update,
            'account_update': self._handle_account_update,
            'business_capability_update': self._handle_business_capability_update,
            'message_template_status_update': self._handle_template_status_update,
            'message_template_quality_update': self._handle_template_quality_update,
            'message_template_components_update': self._handle_template_components_update,
            'phone_number_name_update': self._handle_phone_name_update,
            'phone_number_quality_update': self._handle_phone_quality_update,
            'security': self._handle_security_event,
            'template_category_update': self._handle_template_category_update,
        }

        handler = handlers.get(field)
        if handler:
            try:
                handler(env, account, value)
            except Exception as e:
                _logger.error(f'[WH-DISPATCH] Handler for field={field} failed: {e}', exc_info=True)
                self._update_log_error(env, field, value, str(e))
        else:
            _logger.info(f'[WH-DISPATCH] No handler for field={field}, ignoring')

    # =========================================================
    # HANDLER: messages field — contains inbound msgs + statuses
    # =========================================================
    def _handle_messages_field(self, env, account, value):
        """Process the 'messages' field: inbound messages + delivery statuses"""
        contacts = {c['wa_id']: c.get('profile', {}).get('name', '') for c in value.get('contacts', [])}

        # --- Inbound messages ---
        for msg_data in value.get('messages', []):
            try:
                self._process_inbound_message(env, account, msg_data, contacts, value)
            except Exception as e:
                _logger.error(f'[WH-MSG] Processing message failed: {e}', exc_info=True)

        # --- Delivery status updates ---
        for status_data in value.get('statuses', []):
            try:
                self._process_status_update(env, account, status_data)
            except Exception as e:
                _logger.error(f'[WH-STATUS] Processing status failed: {e}', exc_info=True)

        # --- Value-level errors (system errors) ---
        for error in value.get('errors', []):
            _logger.error(f'[WH-ERROR] System error from Meta: {error}')

        for typing_data in value.get('typing', []):
            self._handle_typing_event(env, account, {'typing': [typing_data], 'metadata': value.get('metadata', {})})

    # =========================================================
    # INBOUND MESSAGE PROCESSOR (all types)
    # =========================================================
    def _process_inbound_message(self, env, account, msg_data, contacts, value):
        phone_number = msg_data.get('from', '')
        wamid = msg_data.get('id', '')
        msg_type = msg_data.get('type', 'text')
        timestamp = msg_data.get('timestamp')

        if not account:
            _logger.error('[WH-MSG] No WhatsApp account matched inbound payload; skipping message %s', wamid)
            return

        self._touch_account_webhook(env, account, inbound=True)

        phone_number = env['whatsapp.message'].sudo()._normalize_phone(phone_number, account=account, strict=False)

        # --- Duplicate guard ---
        if wamid and env['whatsapp.message'].sudo().search_count([('message_id', '=', wamid)]):
            _logger.info(f'[WH-MSG] Duplicate wamid={wamid}, skipping')
            return

        # --- Resolve or create partner ---
        contact_name = contacts.get(phone_number, phone_number)
        partner = env['whatsapp.message'].sudo()._find_partner_by_phone(phone_number)
        if not partner and contact_name and contact_name != phone_number:
            create_vals = {'name': contact_name, 'phone': phone_number}
            if 'mobile' in env['res.partner']._fields:
                create_vals['mobile'] = phone_number
            partner = env['res.partner'].sudo().create(create_vals)
            _logger.info(f'[WH-MSG] Auto-created partner "{contact_name}" for {phone_number}')

        # --- Build base vals ---
        vals = {
            'account_id': account.id,
            'phone_number': phone_number,
            'message_id': wamid,
            'message_type': msg_type if msg_type in ('text', 'image', 'video', 'document', 'audio', 'template', 'interactive') else 'text',
            'direction': 'inbound',
            'status': 'delivered',
            'raw_data': json.dumps(msg_data),
        }
        if partner:
            vals['partner_id'] = partner.id

        # (Profile update happens after message creation so chat is guaranteed to exist)

        # --- Replied-to context ---
        context = msg_data.get('context', {})
        if context:
            parent_wamid = context.get('id')
            if parent_wamid:
                vals['parent_message_id'] = parent_wamid
                parent = env['whatsapp.message'].sudo().search([('message_id', '=', parent_wamid)], limit=1)
                if parent:
                    vals['parent_id'] = parent.id

        # --- Parse body by type ---
        body = self._extract_body(msg_data, msg_type, vals)
        vals['body'] = body

        # --- Special type: reaction ---
        if msg_type == 'reaction':
            reaction = msg_data.get('reaction', {})
            emoji = reaction.get('emoji', '')
            reacted_to_wamid = reaction.get('message_id', '')
            vals['body'] = f'[Reaction: {emoji}]'
            vals['button_payload'] = reacted_to_wamid
            reacted_msg = env['whatsapp.message'].sudo().search([('message_id', '=', reacted_to_wamid)], limit=1)
            if reacted_msg:
                vals['parent_id'] = reacted_msg.id

        # --- Special type: location ---
        elif msg_type == 'location':
            loc = msg_data.get('location', {})
            lat = loc.get('latitude', '')
            lng = loc.get('longitude', '')
            name = loc.get('name', '')
            address = loc.get('address', '')
            vals['body'] = f'[Location: {name or ""}] {address or ""} ({lat},{lng})'

        # --- Special type: contacts shared ---
        elif msg_type == 'contacts':
            shared_contacts = msg_data.get('contacts', [])
            names = [c.get('name', {}).get('formatted_name', 'Unknown') for c in shared_contacts]
            vals['body'] = f'[Contacts shared: {", ".join(names)}]'

        # --- Special type: sticker ---
        elif msg_type == 'sticker':
            sticker = msg_data.get('sticker', {})
            vals['body'] = '[Sticker]'
            vals['media_url'] = sticker.get('id', '')

        # --- Special type: order ---
        elif msg_type == 'order':
            order = msg_data.get('order', {})
            catalog_id = order.get('catalog_id', '')
            items = order.get('product_items', [])

            order_text = f'[Order from catalog {catalog_id}: {len(items)} item(s)]\n'
            sale_order_lines = []

            for item in items:
                retailer_id = item.get('product_retailer_id', '')
                qty = item.get('quantity', 1)
                price = item.get('item_price', 0)

                product = env['product.product'].sudo().search([
                    '|', ('default_code', '=', retailer_id), ('barcode', '=', retailer_id)
                ], limit=1)

                if product:
                    order_text += f'- {qty}x {product.name} ({retailer_id})\n'
                    sale_order_lines.append((0, 0, {
                        'product_id': product.id,
                        'product_uom_qty': qty,
                        'price_unit': price,
                    }))
                else:
                    order_text += f'- {qty}x Unknown Product ({retailer_id})\n'

            vals['body'] = order_text

            if sale_order_lines and partner:
                try:
                    sale_order = env['sale.order'].sudo().create({
                        'partner_id': partner.id,
                        'order_line': sale_order_lines,
                        'origin': f'WhatsApp Catalog {catalog_id}',
                    })
                    vals['sale_order_id'] = sale_order.id
                    vals['body'] += f'\nGenerated Sale Order: {sale_order.name}'

                    # Send auto-confirmation
                    env['whatsapp.message'].sudo().create({
                        'account_id': account.id,
                        'phone_number': phone_number,
                        'partner_id': partner.id,
                        'message_type': 'text',
                        'body': f'Thank you for your order! Your order {sale_order.name} has been received and is being processed.',
                        'direction': 'outbound',
                        'is_automated': True,
                    }).action_send()
                except Exception as e:
                    _logger.error(f'[WH-ORDER] Failed to create sale order: {e}')

        # --- Special type: unsupported ---
        elif msg_type == 'unsupported':
            errors = msg_data.get('errors', [])
            err_desc = errors[0].get('title', 'Unsupported message') if errors else 'Unsupported message type'
            vals['body'] = f'[Unsupported: {err_desc}]'

        # --- Special type: system ---
        elif msg_type == 'system':
            sys_data = msg_data.get('system', {})
            vals['body'] = f'[System: {sys_data.get("body", "event")}]'

        # --- Special type: revoke (deleted) ---
        elif msg_type == 'revoke':
            revoke = msg_data.get('revoke', {})
            revoked_wamid = revoke.get('id', '')
            vals['body'] = '[Message deleted]'
            # Mark the original message
            orig = env['whatsapp.message'].sudo().search([('message_id', '=', revoked_wamid)], limit=1)
            if orig:
                orig.sudo().write({'body': '[Message deleted]', 'status': 'failed'})
            return  # Don't save a new message record for deletions

        # --- Special type: edit ---
        elif msg_type == 'edit':
            edit_data = msg_data.get('edit', {})
            edited_wamid = edit_data.get('id', '')
            new_text = edit_data.get('text', {}).get('body', '')
            orig = env['whatsapp.message'].sudo().search([('message_id', '=', edited_wamid)], limit=1)
            if orig:
                orig.sudo().write({'body': f'{new_text} (edited)', 'error_message': 'Edited by sender'})
            return  # Don't save a new record

        # --- Create the message record ---
        msg_record = env['whatsapp.message'].sudo().create(vals)
        _logger.info(f'[WH-MSG] Saved inbound {msg_type} from {phone_number} wamid={wamid}')

        # --- Download media if applicable ---
        if msg_type in ('image', 'video', 'document', 'audio'):
            msg_record.sudo().queue_media_download()

        # --- Send read receipt back to Meta ---
        try:
            self._send_read_receipt(account, wamid)
        except Exception as e:
            _logger.warning(f'[WH-MSG] Read receipt failed: {e}')

        # --- Mark chat as open (re-opens if resolved/snoozed) ---
        chat_id = False
        if msg_record.chat_id_ref:
            chat = msg_record.chat_id_ref
            chat_id = chat.id
            if chat.state in ('snoozed', 'resolved') or chat.is_archived:
                chat.sudo().write({'state': 'open', 'is_archived': False})

            # Industrial Assignment Guard: Ensure chat has an owner
            if not chat.assigned_user_id:
                chat.sudo()._auto_assign_agent()

        # --- Trigger WebSockets / Zero-Delay Push ---
        env['bus.bus']._sendone('elsx_whatsapp_channel', 'elsx_whatsapp_channel', {
            'chat_id': chat_id,
            'message_id': msg_record.id,
            'type': 'new_message'
        })

        # --- Update Chat & Partner Profile from Meta contacts data ---
        profile_name = contacts.get(phone_number, '')
        if profile_name and msg_record.chat_id_ref:
            update_vals = {'whatsapp_profile_name': profile_name}
            msg_record.chat_id_ref.sudo().write(update_vals)
            # Also update partner name if it was auto-created from phone (name == phone)
            if msg_record.partner_id:
                p = msg_record.partner_id
                if p.name == phone_number or p.name == ('+' + phone_number):
                    p.sudo().write({'name': profile_name})
            _logger.info(f'[WH-MSG] Updated profile name "{profile_name}" for {phone_number}')

        # --- Click-to-WhatsApp entry tracking ---
        try:
            env['whatsapp.campaign'].sudo().track_entry_message(msg_record)
        except Exception as e:
            _logger.warning(f'[CAMPAIGN-TRACKING] Entry tracking failed: {e}')

        # --- Automatic Opt-out Keyword Detection ---
        if body and account.opt_out_keywords:
            keywords = [k.strip().lower() for k in account.opt_out_keywords.split(',') if k.strip()]
            if body.strip().lower() in keywords:
                _logger.info(f'[COMPLIANCE] Opt-out keyword detected from {phone_number}')
                msg_record.sudo().write({'is_opt_out': True})
                if msg_record.partner_id:
                    if 'whatsapp_opt_in' in msg_record.partner_id._fields:
                        msg_record.partner_id.sudo().write({'whatsapp_opt_in': False})
                    env['whatsapp.consent.log'].sudo()._opt_out_partner(
                        msg_record.partner_id, account, reason=f"Keyword trigger: {body.strip()}"
                    )
                if msg_record.chat_id_ref:
                    msg_record.chat_id_ref.sudo().write({
                        'state': 'resolved',
                        'tag_ids': [(4, env.ref('elsx_whatsapp_marketing.whatsapp_tag_opted_out', raise_if_not_found=False).id)] if env.ref('elsx_whatsapp_marketing.whatsapp_tag_opted_out', raise_if_not_found=False) else []
                    })
                return # Stop further processing (bots, etc) for opt-out messages

        bot_enabled = env['ir.config_parameter'].sudo().get_param('whatsapp.enable.bot', 'True')
        bot_enabled = str(bot_enabled).lower() in ('true', '1', 'yes', 'on')

        # --- Campaign/template reply actions ---
        try:
            reply_rule = env['whatsapp.campaign'].sudo().process_inbound_reply(msg_record)
            if reply_rule:
                _logger.info(
                    f'[CAMPAIGN-REPLY] Rule "{reply_rule.name}" handled reply from {phone_number}'
                )
                return
        except Exception as e:
            _logger.error(f'[CAMPAIGN-REPLY] Reply action error: {e}', exc_info=True)

        if not bot_enabled:
            return

        # --- Resume pending flow conversations first ---
        pending_flow_resumed = False
        try:
            resumed_flow = env['whatsapp.bot.flow'].sudo().resume_for_message(msg_record)
            if resumed_flow:
                pending_flow_resumed = True
                _logger.info(f'[BOT-FLOW] Flow "{resumed_flow.name}" resumed for {phone_number}')
        except Exception as e:
            _logger.error(f'[BOT-FLOW] Flow resume error: {e}')

        # --- Fire bot rules ---
        bot_rule_fired = False
        try:
            if pending_flow_resumed:
                return
            bot_rules = env['whatsapp.bot.rule'].sudo().search([
                ('active', '=', True),
                '|', ('account_id', '=', account.id), ('account_id', '=', False)
            ], order='sequence asc')
            for rule in bot_rules:
                fired = rule.check_and_fire(
                    env, account, phone_number, body,
                    partner_id=vals.get('partner_id'),
                    chat_id=msg_record.chat_id_ref.id if msg_record.chat_id_ref else None
                )
                if fired:
                    _logger.info(f'[BOT] Rule "{rule.name}" fired for {phone_number}')
                    bot_rule_fired = True
                    break
        except Exception as e:
            _logger.error(f'[BOT] Rule engine error: {e}')

        if not bot_rule_fired:
            try:
                flow = env['whatsapp.bot.flow'].sudo().trigger_for_message(msg_record)
                if flow:
                    _logger.info(f'[BOT-FLOW] Flow "{flow.name}" triggered for {phone_number}')
            except Exception as e:
                _logger.error(f'[BOT-FLOW] Flow engine error: {e}')

    def _handle_typing_event(self, env, account, value):
        """Relay typing notifications to the live inbox when present in an upstream payload."""
        typing_items = value.get('typing') if isinstance(value, dict) else []
        for item in typing_items or []:
            phone_number = item.get('from') or item.get('phone_number') or ''
            if not phone_number:
                continue
            chat = env['whatsapp.chat'].sudo().search([
                ('account_id', '=', account.id if account else False),
                ('phone_number', '=', env['whatsapp.message'].sudo()._normalize_phone(phone_number, account=account, strict=False)),
            ], limit=1)
            env['bus.bus']._sendone('elsx_whatsapp_channel', 'whatsapp_typing', {
                'chat_id': chat.id if chat else False,
                'phone_number': phone_number,
                'is_typing': item.get('status', 'typing') == 'typing',
            })

    def _extract_body(self, msg_data, msg_type, vals):
        """Extract textual body and media metadata from a message payload"""
        if msg_type == 'text':
            return msg_data.get('text', {}).get('body', '')

        elif msg_type == 'image':
            img = msg_data.get('image', {})
            vals['media_url'] = img.get('id', '')
            return img.get('caption', '[Image]')

        elif msg_type == 'video':
            vid = msg_data.get('video', {})
            vals['media_url'] = vid.get('id', '')
            return vid.get('caption', '[Video]')

        elif msg_type == 'audio':
            aud = msg_data.get('audio', {})
            vals['media_url'] = aud.get('id', '')
            return '[Voice Note]' if aud.get('voice') else '[Audio]'

        elif msg_type == 'document':
            doc = msg_data.get('document', {})
            vals['media_url'] = doc.get('id', '')
            vals['media_filename'] = doc.get('filename', 'document')
            return doc.get('caption', f'[Document: {doc.get("filename", "")}]')

        elif msg_type == 'button':
            btn = msg_data.get('button', {})
            vals['button_text'] = btn.get('text', '')
            vals['button_payload'] = btn.get('payload', '')
            return btn.get('text', '[Button]')

        elif msg_type == 'interactive':
            inter = msg_data.get('interactive', {})
            itype = inter.get('type', '')
            if itype == 'button_reply':
                reply = inter.get('button_reply', {})
                vals['button_text'] = reply.get('title', '')
                vals['button_payload'] = reply.get('id', '')
                return reply.get('id', reply.get('title', '[Button Reply]'))  # Prefer ID for bot triggers
            elif itype == 'list_reply':
                reply = inter.get('list_reply', {})
                vals['list_item_id'] = reply.get('id', '')
                vals['list_item_title'] = reply.get('title', '')
                return reply.get('id', reply.get('title', '[List Reply]'))  # Prefer ID for bot triggers
            elif itype == 'nfm_reply':
                nfm = inter.get('nfm_reply', {})
                response_json_str = nfm.get('response_json', '{}')
                try:
                    response_data = json.loads(response_json_str)
                    formatted_text = f"[Flow Response: {nfm.get('name', 'Form')}]\n"
                    for k, v in response_data.items():
                        formatted_text += f"- {k}: {v}\n"
                    return formatted_text.strip()
                except Exception:
                    return f'[Flow Response: {nfm.get("name", "")}] - Data: {response_json_str}'
            return f'[Interactive: {itype}]'

        elif msg_type == 'template':
            tmpl = msg_data.get('template', {})
            return f'[Template: {tmpl.get("name", "")}]'

        return f'[{msg_type}]'

    # =========================================================
    # STATUS UPDATE PROCESSOR
    # =========================================================
    def _process_status_update(self, env, account, status_data):
        """Run each Meta status update in a small retryable transaction.

        Meta can deliver duplicate status webhooks within milliseconds. Odoo runs
        PostgreSQL in a strict isolation mode, so two background webhook threads
        updating the same message row can raise SerializationFailure. Retrying in
        a fresh cursor preserves delivered/read updates instead of crashing the
        webhook worker.
        """
        db_name = env.cr.dbname
        account_id = account.id if account else False
        last_error = None

        for attempt, delay in enumerate((0,) + self.SERIALIZATION_RETRY_DELAYS, start=1):
            if delay:
                time.sleep(delay)
            registry = Registry(db_name)
            with registry.cursor() as status_cr:
                status_env = api.Environment(status_cr, odoo.SUPERUSER_ID, {})
                status_account = status_env['whatsapp.account'].sudo().browse(account_id) if account_id else False
                try:
                    self._process_status_update_once(status_env, status_account, status_data)
                    status_cr.commit()
                    return
                except Exception as exc:
                    status_cr.rollback()
                    if self._is_serialization_failure(exc):
                        last_error = exc
                        _logger.info(
                            '[WH-STATUS] Serialization retry %s/%s for wamid=%s',
                            attempt,
                            len(self.SERIALIZATION_RETRY_DELAYS) + 1,
                            status_data.get('id'),
                        )
                        continue
                    raise

        _logger.error(
            '[WH-STATUS] Could not apply status update after retries wamid=%s error=%s',
            status_data.get('id'),
            last_error,
        )

    def _process_status_update_once(self, env, account, status_data):
        """Update outbound message delivery status from Meta"""
        wamid = status_data.get('id')
        new_status = status_data.get('status')  # sent | delivered | read | failed | deleted
        timestamp = status_data.get('timestamp')

        # Pricing / conversation info
        pricing = status_data.get('pricing', {})
        conversation = status_data.get('conversation', {})
        conv_origin = conversation.get('origin', {}).get('type', '')  # service | marketing | utility | authentication

        errors = status_data.get('errors', [])

        if not wamid or not new_status:
            return

        msg = env['whatsapp.message'].sudo().search([('message_id', '=', wamid)], limit=1)
        if not msg:
            _logger.debug(f'[WH-STATUS] No message found for wamid={wamid}')
            self._touch_account_webhook(env, account, status_wamid=wamid)
            return

        env.cr.execute('SELECT id FROM whatsapp_message WHERE id = %s FOR UPDATE SKIP LOCKED', [msg.id])
        if not env.cr.fetchone():
            raise WebhookSerializationRetry('Message row is locked by another webhook worker.')
        msg.invalidate_recordset([
            'status',
            'sent_date',
            'delivered_date',
            'read_date',
            'conversation_id',
            'conversation_type',
            'pricing_category',
            'pricing_model',
        ])

        status_dt = self._parse_meta_timestamp(timestamp) or fields.Datetime.now()
        old_status = msg.status or 'draft'
        old_rank = self.STATUS_ORDER.get(old_status, 0)
        new_rank = self.STATUS_ORDER.get(new_status, old_rank)
        should_update_status = (
            new_status == 'deleted'
            or (new_status == 'failed' and old_status not in ('delivered', 'read'))
            or new_rank >= old_rank
        )

        update_vals = {}
        if should_update_status:
            update_vals['status'] = new_status
        elif old_status != new_status:
            _logger.info(
                '[WH-STATUS] Ignoring out-of-order downgrade wamid=%s old=%s new=%s',
                wamid, old_status, new_status
            )
        if new_status == 'sent':
            if not msg.sent_date:
                update_vals['sent_date'] = status_dt
        elif new_status == 'delivered':
            if not msg.sent_date:
                update_vals['sent_date'] = status_dt
            if not msg.delivered_date:
                update_vals['delivered_date'] = status_dt
        elif new_status == 'read':
            if not msg.sent_date:
                update_vals['sent_date'] = status_dt
            if not msg.delivered_date:
                update_vals['delivered_date'] = status_dt
            update_vals['read_date'] = status_dt
        elif new_status == 'failed':
            if errors:
                err = errors[0]
                update_vals['error_message'] = f"[{err.get('code')}] {err.get('title', '')} — {err.get('message', '')}"
                message_model = env['whatsapp.message'].sudo()
                update_vals['error_message'] = message_model._format_meta_error(err)
                if message_model._is_non_retryable_meta_error_code(err.get('code')):
                    update_vals['next_retry_at'] = False
            else:
                update_vals['error_message'] = 'Message delivery failed'
        elif new_status == 'deleted':
            update_vals['body'] = '[Message deleted by sender]'

        if conversation.get('id'):
            update_vals['conversation_id'] = conversation.get('id')
        if conv_origin:
            update_vals['conversation_type'] = conv_origin
        if pricing.get('category'):
            update_vals['pricing_category'] = pricing.get('category')
        if pricing.get('pricing_model'):
            update_vals['pricing_model'] = pricing.get('pricing_model')

        if update_vals:
            msg.sudo().write(update_vals)
        self._touch_account_webhook(env, account, status_wamid=wamid)
        _logger.info(f'[WH-STATUS] wamid={wamid} → {new_status} (conversation_type={conv_origin})')

        # ENTERPRISE LOGIC: Trigger Real-Time UI Update for Status (Blue Ticks)
        try:
            if msg.chat_id_ref:
                env['bus.bus']._sendone(
                    'elsx_whatsapp_channel',
                    'whatsapp_status_update',
                    {
                        'chat_id': msg.chat_id_ref.id,
                        'message_id': msg.id,
                        'message_wamid': msg.message_id,
                        'status': msg.status,
                        'event_status': new_status,
                        'sent_date': str(msg.sent_date or ''),
                        'delivered_date': str(msg.delivered_date or ''),
                        'read_date': str(msg.read_date or ''),
                    }
                )
        except Exception as e:
            _logger.error(f'[WH-STATUS] Bus notification failed: {e}')

    def _parse_meta_timestamp(self, timestamp):
        """Convert Meta's UNIX timestamp string to a naive UTC datetime for Odoo."""
        if not timestamp:
            return False
        try:
            return datetime.utcfromtimestamp(int(timestamp))
        except Exception:
            return False

    def _touch_account_webhook(self, env, account, inbound=False, status_wamid=False):
        """Record webhook freshness for dashboard/account health diagnostics."""
        if not account or not account.exists():
            return
        now = fields.Datetime.now()
        vals = {
            'last_webhook_at': now,
            'webhook_status': 'verified',
            'webhook_last_error': False,
        }
        if inbound:
            vals['last_inbound_webhook_at'] = now
        if status_wamid:
            vals.update({
                'last_status_webhook_at': now,
                'last_status_wamid': status_wamid,
            })
        try:
            account.sudo().write(vals)
        except Exception as exc:
            _logger.warning('[WH-WEBHOOK] Failed to update account webhook freshness: %s', exc)

    # =========================================================
    # READ RECEIPT SENDER
    # =========================================================
    def _send_read_receipt(self, account, wamid):
        """Send a Mark as Read receipt to Meta for incoming messages"""
        import requests
        url = f'https://graph.facebook.com/{account.api_version}/{account.phone_number_id}/messages'
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'messaging_product': 'whatsapp',
            'status': 'read',
            'message_id': wamid,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        if resp.status_code != 200:
            _logger.warning(f'[READ-RECEIPT] Failed for {wamid}: {resp.text}')

    # =========================================================
    # ACCOUNT / SYSTEM EVENT HANDLERS
    # =========================================================
    def _handle_account_alerts(self, env, account, value):
        """Handle account_alerts — policy violations, WAB bans, etc."""
        alert_type = value.get('alert_type', 'UNKNOWN')
        notification_text = value.get('notification_text', '')
        _logger.warning(f'[WH-ALERT] Account Alert: type={alert_type} msg="{notification_text}" account={account.id if account else None}')

        if account:
            # Optionally downgrade quality rating on critical alerts
            if 'DISABLED' in alert_type.upper() or 'BANNED' in alert_type.upper():
                account.sudo().write({'status': 'error', 'quality_rating': 'RED'})

    def _handle_account_review_update(self, env, account, value):
        """Handle account_review_update — business verification status"""
        decision = value.get('decision', '')
        _logger.info(f'[WH-REVIEW] Account review decision: {decision}')
        if account and decision == 'APPROVED':
            account.sudo().write({'status': 'connected'})
        elif account and decision in ('REJECTED', 'DISABLED'):
            account.sudo().write({'status': 'error'})

    def _handle_account_update(self, env, account, value):
        """Handle account_update — display name, messaging limits, quality changes"""
        event = value.get('event', '')
        _logger.info(f'[WH-ACCT-UPDATE] Event: {event}')
        if not account:
            return
        if event == 'PHONE_NUMBER_NAME_UPDATE':
            new_name = value.get('display_phone_number', '')
            if new_name:
                account.sudo().write({'phone_number': new_name})
        elif 'MESSAGING_LIMIT' in event:
            limit = (
                value.get('new_tier')
                or value.get('current_limit')
                or value.get('messaging_limit_tier')
                or value.get('whatsapp_business_manager_messaging_limit')
                or ''
            )
            if limit:
                label = account._normalize_meta_limit_label(limit)
                limit_number = account._extract_meta_limit_number(limit)
                vals = {'messaging_limit': label or str(limit)}
                if limit_number:
                    vals['max_daily_limit'] = limit_number
                account.sudo().write(vals)

    def _handle_business_capability_update(self, env, account, value):
        """Handle business_capability_update — messaging window changes"""
        _logger.info(f'[WH-BUSI-CAP] Business capability update: {value}')
        if account:
            try:
                account.sudo().action_sync_meta_health()
            except Exception as exc:
                _logger.info('[WH-BUSI-CAP] Meta health refresh skipped: %s', exc)

    def _handle_template_status_update(self, env, account, value):
        """Handle message_template_status_update — template approved/rejected/paused"""
        template_name = value.get('message_template_name', '')
        template_id_meta = str(value.get('message_template_id', ''))
        event = value.get('event', '')
        reason = value.get('reason', '')

        _logger.info(f'[WH-TPL-STATUS] Template "{template_name}" event={event} reason={reason}')

        # Map Meta event to Odoo template status
        status_map = {
            'APPROVED': 'approved',
            'REJECTED': 'rejected',
            'PENDING_DELETION': 'paused',
            'FLAGGED': 'paused',
            'PAUSED': 'paused',
            'DISABLED': 'disabled',
        }
        odoo_status = status_map.get(event)

        if odoo_status:
            template = env['whatsapp.template'].sudo().search([
                '|', ('name', '=', template_name),
                ('template_id', '=', template_id_meta),
            ], limit=1)
            if template:
                vals = {
                    'status': odoo_status,
                    'meta_state': event,
                    'last_meta_event': event,
                    'last_meta_event_date': fields.Datetime.now(),
                }
                if reason:
                    vals['rejection_reason'] = reason
                    vals['meta_disabled_reason'] = reason
                template.sudo().write(vals)
                template.sudo()._log_meta_audit(event or 'status_update', status=odoo_status, reason=reason, raw_data=value)

    def _handle_template_quality_update(self, env, account, value):
        """Handle message_template_quality_update — quality score changes"""
        template_name = value.get('message_template_name', '')
        template_id_meta = str(value.get('message_template_id', '') or '')
        quality = value.get('new_quality_score', '')
        _logger.info(f'[WH-TPL-QUALITY] Template "{template_name}" new quality={quality}')
        quality_map = {
            'GREEN': 'green',
            'HIGH': 'green',
            'YELLOW': 'yellow',
            'MEDIUM': 'yellow',
            'RED': 'red',
            'LOW': 'red',
            'UNKNOWN': 'unknown',
        }
        quality_score = quality_map.get((quality or '').upper(), 'unknown')
        domain = []
        if account:
            domain.append(('account_id', '=', account.id))
        if template_id_meta:
            domain += ['|', ('template_id', '=', template_id_meta)]
        domain += ['|', ('meta_template_name', '=', template_name), ('name', '=', template_name)]
        template = env['whatsapp.template'].sudo().search(domain, limit=1)
        if template:
            template.sudo().write({
                'quality_score': quality_score,
                'meta_quality_rating': quality,
                'last_meta_event': 'quality_update',
                'last_meta_event_date': fields.Datetime.now(),
            })
            template.sudo()._log_meta_audit('quality_update', status=quality_score, raw_data=value)

    def _handle_template_components_update(self, env, account, value):
        """Handle message_template_components_update — auto-fill updates"""
        _logger.info(f'[WH-TPL-COMP] Template components updated: {value}')

    def _handle_phone_name_update(self, env, account, value):
        """Handle phone_number_name_update — display name review result"""
        decision = value.get('decision', '')
        display_phone = value.get('display_phone_number', '')
        _logger.info(f'[WH-PHONE-NAME] Phone name update: {display_phone} decision={decision}')

    def _handle_phone_quality_update(self, env, account, value):
        """Handle phone_number_quality_update — account quality rating change"""
        quality = value.get('current_limit', value.get('current_quality', ''))
        _logger.info(f'[WH-PHONE-QUALITY] Account quality update: {quality}')
        if account and quality:
            quality_map = {'HIGH': 'GREEN', 'MEDIUM': 'YELLOW', 'LOW': 'RED', 'UNKNOWN': 'UNKNOWN'}
            new_quality = quality_map.get(quality.upper(), 'UNKNOWN')
            vals = {'quality_rating': new_quality}
            limit = value.get('current_limit') or value.get('messaging_limit_tier') or value.get('whatsapp_business_manager_messaging_limit')
            if limit:
                label = account._normalize_meta_limit_label(limit)
                limit_number = account._extract_meta_limit_number(limit)
                vals['messaging_limit'] = label or str(limit)
                if limit_number:
                    vals['max_daily_limit'] = limit_number
            account.sudo().write(vals)

    def _handle_security_event(self, env, account, value):
        """Handle security webhook events — e.g. user_identity_changed"""
        event = value.get('event', '')
        _logger.warning(f'[WH-SECURITY] Security event: {event} | {value}')

    def _handle_template_category_update(self, env, account, value):
        """Handle template_category_update — Meta re-categorises a template"""
        template_name = value.get('message_template_name', '')
        new_category = value.get('new_category', '')
        _logger.info(f'[WH-TPL-CAT] Template "{template_name}" re-categorised to {new_category}')
        if template_name and new_category:
            template = env['whatsapp.template'].sudo().search([('name', '=', template_name)], limit=1)
            if template:
                template.sudo().write({
                    'template_category': new_category.lower(),
                    'last_meta_event': 'category_update',
                    'last_meta_event_date': fields.Datetime.now(),
                })
                template.sudo()._log_meta_audit('category_update', status=new_category, raw_data=value)

    # =========================================================
    # AUDIT LOG HELPERS
    # =========================================================
    def _log_event(self, env, account, field, value, raw_data):
        """Write a webhook log record for every received event"""
        try:
            phone = ''
            wamid = ''
            msgs = value.get('messages', [])
            if msgs:
                phone = msgs[0].get('from', '')
                wamid = msgs[0].get('id', '')
            statuses = value.get('statuses', [])
            if statuses:
                wamid = statuses[0].get('id', '')
                phone = statuses[0].get('recipient_id', '')

            env['whatsapp.webhook.log'].sudo().create({
                'account_id': account.id if account and account.exists() else False,
                'event_type': field,
                'field_type': field,
                'phone_number': phone,
                'message_id': wamid,
                'status': 'processed',
                'raw_payload': raw_data[:5000],
            })
        except Exception as e:
            _logger.warning(f'[WH-LOG] Failed to write webhook log: {e}')

    def _update_log_error(self, env, field, value, error_msg):
        """Update the most recent log entry for a field to error status"""
        try:
            log = env['whatsapp.webhook.log'].sudo().search(
                [('event_type', '=', field)], order='create_date desc', limit=1
            )
            if log:
                log.sudo().write({'status': 'error', 'error_detail': error_msg[:2000]})
        except Exception:
            pass

    # =========================================================
    # MEDIA PROXY — Serves Meta media via Odoo
    # =========================================================
    @http.route('/whatsapp/media/<string:media_id>', type='http', auth='user')
    def whatsapp_media_proxy(self, media_id, **kwargs):
        """Fetch media from Meta and serve it to the browser"""
        try:
            env, cr, _ = _get_env()
            with cr:
                account = env['whatsapp.account'].sudo()._get_default_account()
                if not account:
                    return request.not_found()

                import requests
                # 1. Get media URL from ID
                meta_url = f"https://graph.facebook.com/{account.api_version}/{media_id}"
                headers = {'Authorization': f'Bearer {account.access_token}'}
                resp = requests.get(meta_url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    return request.not_found()

                download_url = resp.json().get('url')
                if not download_url:
                    return request.not_found()

                # 2. Download the actual binary
                media_resp = requests.get(download_url, headers=headers, timeout=30)
                if media_resp.status_code != 200:
                    return request.not_found()

                return request.make_response(
                    media_resp.content,
                    headers=[
                        ('Content-Type', media_resp.headers.get('Content-Type', 'image/jpeg')),
                        ('Cache-Control', 'max-age=86400'),
                    ]
                )
        except Exception as e:
            _logger.error(f'[WH-MEDIA] Proxy failed: {e}')
            return request.not_found()

    # =========================================================
    # SIDECAR CALLBACK — Zero-Latency Asynchronous Ingress
    # =========================================================
    @http.route('/whatsapp/sidecar/receive', type='http', auth='none', methods=['POST'], csrf=False)
    def sidecar_receive(self, **kwargs):
        """
        Industrial Callback from Sidecar.
        Used when Sidecar receives Meta Webhook FIRST and forwards to Odoo.
        """
        secret = request.httprequest.headers.get('x-sidecar-key')

        # We need a valid environment to check config parameters in auth='none'
        env, cr, _ = _get_env()
        if not env:
            _logger.error('[SIDECAR-IN] Could not initialize environment for security check')
            return request.make_json_response({'status': 'error', 'message': 'System Initialization Error'}, status=500)

        try:
            expected_secret = env['ir.config_parameter'].sudo().get_param('whatsapp.sidecar.secret')
            if not expected_secret or secret != expected_secret:
                _logger.warning('[SIDECAR-IN] Unauthorized access attempt with secret %s', _mask_secret(secret))
                return request.make_json_response({'status': 'error', 'message': 'Unauthorized'}, status=403)
        finally:
            cr.close()

        raw_body = request.httprequest.data or b''
        signature = request.httprequest.headers.get('X-Hub-Signature-256', '')
        try:
            payload = json.loads(raw_body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return request.make_json_response({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        _logger.info('[SIDECAR-IN] Received payload for processing')

        # We reuse the POST logic by calling _handle_post with raw JSON
        # Since _handle_post normally reads from request.httprequest.data,
        # we'll create a small helper.
        result = self._process_payload_direct(payload, raw_body=raw_body, signature=signature)
        status = result.get('http_status') or (200 if result.get('status') in ('success', 'ignored') else 500)
        return request.make_json_response(result, status=status)

    def _process_payload_direct(self, payload, raw_body=None, signature=None):
        """Helper to process a JSON payload directly without re-reading from request"""
        if payload.get('object') != 'whatsapp_business_account':
            return {'status': 'ignored'}

        env, cr, _ = _get_env()
        with cr:
            # We'll use the same processing logic as _handle_post
            # but we need to pass the payload object
            try:
                # Find account
                account = _find_account(env, None, payload)
                if not account:
                    return {'status': 'error', 'message': 'No matching account'}

                if raw_body is not None:
                    ok, message, status = self._verify_meta_signature(account, raw_body, signature or '')
                    if not ok:
                        return {'status': 'error', 'message': message, 'http_status': status}

                # Process entries
                for entry in payload.get('entry', []):
                    for change in entry.get('changes', []):
                        field = change.get('field')
                        value = change.get('value') or {}
                        # Call standard dispatcher
                        self._dispatch_change(env, account, field, value, json.dumps(payload))
                cr.commit()
                return {'status': 'success'}
            except Exception as e:
                _logger.error(f'[SIDECAR-IN] Processing failed: {e}')
                return {'status': 'error', 'message': str(e)}
