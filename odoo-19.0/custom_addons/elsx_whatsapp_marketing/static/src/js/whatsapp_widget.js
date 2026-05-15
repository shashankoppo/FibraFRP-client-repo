/** @odoo-module **/

import { registry } from "@web/core/registry";
import { playTone } from "./notification_tones.js";

// ============================================================
// WhatsApp Real-time Handler — Odoo 19 Compatible (v6.0)
// + Intelligent Scroll Locking
// + Scroll-to-Bottom FAB
// + Mobile Responsiveness
// ============================================================

const WA_NOTIFICATION_TYPES = [
    'elsx_whatsapp_channel',
    'whatsapp.chat',
    'whatsapp_status_update',
];

const SCROLL_THRESHOLD = 150; // px from bottom to consider "at bottom"

export class WhatsAppChatHandler {
    constructor(env, { bus_service, action }) {
        this.bus = bus_service;
        this.actionService = action;
        this.env = env;
        this._lastHtml = null;
        this._lastChatId = null;
        this._refreshInterval = null;
        this._presenceInterval = null;
        this._historyLimit = 100;
        this._isPaging = false;
        this._userIsAtBottom = true;
        this._notificationPreferencesByAccount = {};
        this._accountByChat = {};

        this._lastPlayedMessageId = new Set();
        
        console.log('[WhatsApp] Handler Service Initialized (v7.0)');

        // Add Floating FAB and Search event listeners
        this._initGlobalComponents();
        
        // Watch for chat switches (URL changes)
        window.addEventListener('hashchange', () => {
            console.log('[WhatsApp] Navigation detected, refreshing history...');
            setTimeout(() => this._surgicalRefresh(), 250);
        });

        // Periodic check to ensure components exist (Odoo DOM replacements)
        setInterval(() => this._initGlobalComponents(), 5000);

        try { this.init(); } catch (e) {
            console.warn('[WhatsApp] Service init error:', e);
        }
        try { this.initSocket(); } catch (e) {
            console.warn('[WhatsApp] Socket init error:', e);
        }
    }

    // ── Global UI Enhancements ─────────────────────────────────────
    _initGlobalComponents() {
        // 1. Inject Floating FAB (Global Interaction)
        if (!document.getElementById('wa_global_fab')) {
            console.log('[WhatsApp] Injecting Global FAB...');
            const fab = document.createElement('div');
            fab.id = 'wa_global_fab';
            fab.className = 'wa-floating-fab animate-bounce-in';
            fab.title = 'Open WhatsApp Team Inbox';
            fab.innerHTML = `
                <div class="wa-fab-icon shadow-lg">
                    <i class="fa fa-whatsapp"></i>
                    <span class="wa-fab-badge d-none">0</span>
                </div>
            `;
            fab.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                this._openTeamInbox();
            };
            document.body.appendChild(fab);
        }

        // 2. Delegate Search Input (Real-time Filtering)
        // Note: Event listener is already attached to document in constructor if we use delegation
    }

    async _openTeamInbox() {
        const action = await this._rpc('ir.model.data', 'xmlid_to_res_id', ['elsx_whatsapp_marketing.action_whatsapp_chat_inbox']);
        if (action) {
            window.location.hash = `#action=${action}&model=whatsapp.chat&view_type=form`;
        }
    }

    _filterSidebarChats(query) {
        const q = query.toLowerCase().trim();
        const items = document.querySelectorAll('.o_whatsapp_sidebar_item');
        items.forEach(item => {
            const name = item.querySelector('.o_whatsapp_chat_item_name')?.textContent?.toLowerCase() || '';
            const phone = item.closest('[data-chat-id]')?.textContent?.toLowerCase() || ''; // Fallback search in all text
            const matches = name.includes(q) || phone.includes(q);
            item.style.display = matches ? 'block' : 'none';
        });
    }

    // ── Sounds ─────────────────────────────────────────────────────
    async _playSound(type, chatId = null, messageId = null) {
        if (messageId) {
            if (this._lastPlayedMessageId.has(messageId)) return;
            this._lastPlayedMessageId.add(messageId);
            // Keep set small
            if (this._lastPlayedMessageId.size > 50) {
                const first = this._lastPlayedMessageId.values().next().value;
                this._lastPlayedMessageId.delete(first);
            }
        }

        try {
            const preferences = await this._getNotificationPreferences(chatId);
            if (!preferences?.notification_enabled) return;
            const toneName = type === 'sent'
                ? preferences.notification_sound_send
                : preferences.notification_sound_receive;
            if (toneName && toneName !== 'none') playTone(type, toneName);
        } catch (e) { /* audio not critical */ }
    }

    async _getNotificationPreferences(chatId = null) {
        chatId = chatId || this._getActiveChatId();
        if (!chatId) return null;
        let accountId = this._accountByChat[chatId];
        if (!accountId) {
            const chatData = await this._rpc('whatsapp.chat', 'read', [[chatId], ['account_id']]);
            const accountField = chatData?.[0]?.account_id;
            accountId = Array.isArray(accountField) ? accountField[0] : accountField;
            if (!accountId) return null;
            this._accountByChat[chatId] = accountId;
        }
        if (!this._notificationPreferencesByAccount[accountId]) {
            const accountData = await this._rpc('whatsapp.account', 'read', [
                [accountId], ['notification_enabled', 'notification_sound_receive', 'notification_sound_send'],
            ]);
            this._notificationPreferencesByAccount[accountId] = accountData?.[0] || null;
        }
        return this._notificationPreferencesByAccount[accountId];
    }

    // ── Socket.IO ──────────────────────────────────────────────────
    initSocket() {
        if (this.socket) {
            this.socket.disconnect();
        }

        // 1. Determine Socket URL with intelligent fallback
        let socketUrl = 'http://localhost:3000'; // Default
        const origin = window.location.origin;
        
        if (origin.includes('localhost')) {
            socketUrl = 'http://localhost:3000';
        } else {
            // Production / Cloudflared / Proxy logic
            // Replace port 8069 with 3000 if present, otherwise just change protocol for WSS if needed
            socketUrl = origin.replace('8069', '3000');
            // If the site is HTTPS, we might need WSS or a proxy. 
            // For now, try to match the origin's protocol
            if (origin.startsWith('https')) {
                // If on HTTPS but no port 3000 exposed via HTTPS, this may fail.
                // In Docker environments, usually 3000 is exposed via the same domain.
            }
        }

        console.log('[WhatsApp] Connecting to Socket Sidecar:', socketUrl);

        this.socket = io(socketUrl, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 10,
            reconnectionDelay: 2000,
            timeout: 10000,
        });

        this.socket.on('connect', () => {
            console.log('[WhatsApp] Socket.io Connected! ID:', this.socket.id);
            this._updateConnectionStatus('connected');
            this._touchPresence();
            this._surgicalRefresh();
        });
        this.socket.on('whatsapp_event', (data) => {
            const activeChatId = this._getActiveChatId();
            
            // 1. Refresh UI if it's for the current chat (or we are in list view)
            if (!activeChatId || activeChatId == data.chat_id) {
                this._surgicalRefresh();
            }

            // 2. Play sound for ALL inbound messages regardless of active chat
            if (data.type === 'new_message' && data.message?.direction === 'inbound') {
                this._playSound('received', data.chat_id, data.message?.id);
            }
        });
        this.socket.on('sync_required', () => this._surgicalRefresh());
        this.socket.on('whatsapp_typing', (data) => this._showTypingIndicator(data));
        this.socket.on('disconnect', () => this._updateConnectionStatus('disconnected'));
        this.socket.on('connect_error', () => this._updateConnectionStatus('error'));
    }

    _updateConnectionStatus(status) {
        const dot = document.getElementById('whatsapp_socket_status');
        if (!dot) return;
        dot.className = 'position-absolute bottom-0 end-0 border border-2 border-white rounded-circle';
        if (status === 'connected') {
            dot.style.background = '#22C55E';
            dot.classList.add('animate-pulse');
        } else if (status === 'reconnecting') {
            dot.style.background = '#F97316';
        } else {
            dot.style.background = '#EF4444';
        }
    }

    // ── Initialization ─────────────────────────────────────────────
    init() {
        for (const type of WA_NOTIFICATION_TYPES) {
            try {
                this.bus.subscribe(type, (payload) => this._onNotification(type, payload));
            } catch (e) {
                console.warn(`[WhatsApp] Could not subscribe to ${type}:`, e);
            }
        }
        try {
            this.bus.subscribe('whatsapp_typing', (payload) => this._showTypingIndicator(payload || {}));
        } catch (e) { /* non-fatal */ }
        try { this.bus.addChannel('elsx_whatsapp_channel'); } catch (e) { /* non-fatal */ }

        // Initial load of history
        setTimeout(() => {
            const hiddenField = document.querySelector('.wa-hidden-history-field');
            const mount = document.getElementById('wa-custom-history-mount');
            if (hiddenField && mount && hiddenField.innerHTML) {
                mount.innerHTML = hiddenField.innerHTML;
            }
            this._scrollToBottom(true);
            this._attachScrollListener();
            this._injectScrollFAB();
            this._injectMobileBackButton();
        }, 500);

        // Periodic sync every 10 seconds
        this._refreshInterval = setInterval(() => {
            if (!document.hidden) this._surgicalRefresh();
        }, 10000);

        // Presence heartbeat every 45 seconds
        this._presenceInterval = setInterval(() => this._touchPresence(), 45000);
        document.addEventListener('visibilitychange', () => this._touchPresence());

        // Global click handler
        document.addEventListener('click', this._handleGlobalClicks.bind(this), true);

        // Enter to Send
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                const textarea = e.target.closest('.wa-premium-input');
                if (textarea) {
                    e.preventDefault();
                    const sendBtn = document.querySelector('button[name="action_send_quick_reply"]');
                    if (sendBtn) sendBtn.click();
                }
            }
        });
    }

    // ── Scroll Intelligence ────────────────────────────────────────
    _attachScrollListener() {
        const historyDiv = document.querySelector('.wa-chat-history-content-container');
        if (!historyDiv || historyDiv._waScrollBound) return;
        historyDiv._waScrollBound = true;
        historyDiv.addEventListener('scroll', () => {
            const distFromBottom = historyDiv.scrollHeight - historyDiv.scrollTop - historyDiv.clientHeight;
            this._userIsAtBottom = distFromBottom < SCROLL_THRESHOLD;
            this._toggleScrollFAB(!this._userIsAtBottom);
        });
    }

    _scrollToBottom(force = false) {
        const historyDiv = document.querySelector('.wa-chat-history-content-container');
        if (!historyDiv) return;
        if (force || this._userIsAtBottom) {
            historyDiv.scrollTo({ top: historyDiv.scrollHeight, behavior: force ? 'auto' : 'smooth' });
            this._userIsAtBottom = true;
            this._toggleScrollFAB(false);
        }
    }

    // ── Scroll-to-Bottom FAB ───────────────────────────────────────
    _injectScrollFAB() {
        if (document.getElementById('wa_scroll_fab')) return;
        const chatHistory = document.getElementById('wa_chat_history');
        if (!chatHistory) return;

        const fab = document.createElement('button');
        fab.id = 'wa_scroll_fab';
        fab.type = 'button';
        fab.title = 'Jump to latest';
        fab.setAttribute('aria-label', 'Scroll to bottom');
        fab.innerHTML = '<i class="fa fa-chevron-down"></i>';
        fab.style.cssText = [
            'position:absolute', 'bottom:90px', 'right:24px', 'z-index:50',
            'width:40px', 'height:40px', 'border-radius:50%',
            'background:rgba(255,255,255,.95)', 'border:1px solid #e0e0e0',
            'box-shadow:0 2px 8px rgba(0,0,0,.18)', 'cursor:pointer',
            'display:none', 'align-items:center', 'justify-content:center',
            'color:#54656f', 'font-size:16px',
            'transition:opacity .2s, transform .2s',
        ].join(';');
        fab.addEventListener('click', () => this._scrollToBottom(true));
        chatHistory.style.position = 'relative';
        chatHistory.appendChild(fab);
    }

    _toggleScrollFAB(show) {
        const fab = document.getElementById('wa_scroll_fab');
        if (!fab) return;
        fab.style.display = show ? 'flex' : 'none';
    }

    // ── Mobile Back Button ─────────────────────────────────────────
    _injectMobileBackButton() {
        if (document.getElementById('wa_mobile_back_btn')) return;
        if (window.innerWidth > 991) return;
        const header = document.querySelector('.o_whatsapp_panel_header_premium');
        if (!header) return;

        const btn = document.createElement('button');
        btn.id = 'wa_mobile_back_btn';
        btn.type = 'button';
        btn.className = 'btn btn-link p-0 me-2 text-dark d-lg-none';
        btn.innerHTML = '<i class="fa fa-arrow-left" style="font-size:1.2rem;"></i>';
        btn.title = 'Back to Chats';
        btn.addEventListener('click', () => {
            const sidebar = document.querySelector('.wa-left-sidebar');
            const main = document.querySelector('.o_whatsapp_chat_main');
            const rightSidebar = document.querySelector('.wa-right-sidebar');
            if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
            if (main) main.classList.add('d-none');
            if (rightSidebar) rightSidebar.classList.add('d-none');
        });
        header.querySelector('.d-flex')?.prepend(btn);
    }

    // ── Notification Handler ───────────────────────────────────────
    _onNotification(type, payload) {
        if (type === 'whatsapp_typing') {
            this._showTypingIndicator(payload || {});
            return;
        }
        
        // Play sound for inbound messages from Bus notifications (backup to Socket.IO)
        if (payload?.type === 'new_message' && payload?.chat_id) {
            this._playSound('received', payload.chat_id, payload.message_id);
        }

        this._surgicalRefresh();
    }

    // ── Click Handler ──────────────────────────────────────────────
    _handleGlobalClicks(e) {
        // Load More
        const loadMoreBtn = e.target.closest('button[name="action_load_more"]');
        if (loadMoreBtn) {
            e.preventDefault(); e.stopPropagation();
            this._historyLimit += 100;
            this._isPaging = true;
            this._hardRefresh();
            return;
        }
        // Media Lightbox
        const lightbox = e.target.closest('.wa-lightbox-trigger');
        if (lightbox) {
            e.preventDefault(); e.stopPropagation();
            this._openLightbox(lightbox.getAttribute('href') || lightbox.getAttribute('src'));
            return;
        }
        // Sidebar chat switch — also handle mobile view toggle
        const sidebarItem = e.target.closest('.o_whatsapp_sidebar_item');
        if (sidebarItem) {
            const chatId = parseInt(sidebarItem.getAttribute('data-chat-id'));
            if (chatId) {
                this._lastChatId = chatId;
                this._lastHtml = null;
                this._historyLimit = 100;
                this._userIsAtBottom = true;
                this._surgicalRefresh(chatId);
                // Mobile: hide sidebar, show chat
                if (window.innerWidth <= 991) {
                    const sidebar = document.querySelector('.wa-left-sidebar');
                    const main = document.querySelector('.o_whatsapp_chat_main');
                    if (sidebar) { sidebar.classList.add('d-none'); sidebar.classList.remove('d-flex'); }
                    if (main) main.classList.remove('d-none');
                }
            }
            return;
        }
        // Send message
        const sendBtn = e.target.closest('button[name="action_send_quick_reply"]');
        if (sendBtn) {
            const input = document.querySelector('.wa-premium-input textarea') || document.querySelector('.wa-premium-input');
            if (input && input.value.trim()) {
                e.preventDefault(); e.stopPropagation();
                this._sendRPC('action_send_quick_reply', input.value);
            }
            return;
        }
        // Internal note
        const noteBtn = e.target.closest('button[name="action_send_internal_note"]');
        if (noteBtn) {
            const input = document.querySelector('.wa-premium-input textarea') || document.querySelector('.wa-premium-input');
            if (input && input.value.trim()) {
                e.preventDefault(); e.stopPropagation();
                this._sendRPC('action_send_internal_note', input.value);
            }
            return;
        }
        // Emoji picker toggle
        const emojiBtn = e.target.closest('#wa_emoji_trigger');
        if (emojiBtn) {
            e.preventDefault(); e.stopPropagation();
            this._toggleEmojiPicker(emojiBtn);
        }
    }

    // ── Hard Refresh ───────────────────────────────────────────────
    _hardRefresh() {
        this.actionService.doAction('elsx_whatsapp_marketing.action_whatsapp_console_direct', {
            stackPosition: 'replaceCurrentAction',
            additionalContext: { wa_history_limit: this._historyLimit },
        });
    }

    // ── Surgical Refresh (scroll-aware) ────────────────────────────
    async _surgicalRefresh(forceChatId = null) {
        const historyDiv = document.querySelector('.wa-chat-history-content-container');
        const chatId = forceChatId || this._getActiveChatId();
        if (!historyDiv || !chatId) return;

        // Remember scroll position BEFORE updating DOM
        const prevScrollTop = historyDiv.scrollTop;
        const prevScrollHeight = historyDiv.scrollHeight;

        try {
            const response = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: this._rpcHeaders(),
                body: JSON.stringify({
                    jsonrpc: '2.0', method: 'call', id: Date.now(),
                    params: {
                        model: 'whatsapp.chat',
                        method: 'read',
                        args: [[chatId], ['history_html', 'unread_count', 'display_name']],
                        kwargs: { context: { wa_history_limit: this._historyLimit } },
                    },
                }),
            });
            const data = await response.json();
            if (data.result && data.result[0]) {
                const res = data.result[0];
                if (this._lastHtml !== res.history_html) {
                    const mount = document.getElementById('wa-custom-history-mount');
                    if (mount) {
                        mount.innerHTML = res.history_html;
                    } else {
                        historyDiv.innerHTML = res.history_html;
                    }
                    this._lastHtml = res.history_html;

                    // Scroll logic: respect user position
                    if (this._isPaging) {
                        // Keep position when loading older messages
                        const addedHeight = historyDiv.scrollHeight - prevScrollHeight;
                        historyDiv.scrollTop = prevScrollTop + addedHeight;
                        this._isPaging = false;
                    } else if (this._userIsAtBottom || forceChatId) {
                        // Auto-scroll only if user was already at bottom or switching chats
                        setTimeout(() => this._scrollToBottom(true), 30);
                    }
                    // Otherwise: don't touch scroll — user is reading history

                    this._attachScrollListener();
                    this._injectScrollFAB();
                }
            }
        } catch (e) { /* non-fatal — polling will retry */ }
    }

    // ── Send Message via RPC ───────────────────────────────────────
    async _sendRPC(method, text) {
        const chatId = this._getActiveChatId();
        if (!chatId) return;
        try {
            await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: this._rpcHeaders(),
                body: JSON.stringify({
                    jsonrpc: '2.0', method: 'call', id: Date.now(),
                    params: {
                        model: 'whatsapp.chat',
                        method: method,
                        args: [[chatId]],
                        kwargs: { context: { default_quick_reply_text: text } },
                    },
                }),
            });
            const input = document.querySelector('.wa-premium-input textarea') || document.querySelector('.wa-premium-input');
            if (input) input.value = '';
            if (method === 'action_send_quick_reply') this._playSound('sent', chatId);
            // Force scroll to bottom after sending
            this._userIsAtBottom = true;
            this._surgicalRefresh();
        } catch (e) {
            console.error('[WhatsApp] Send failed:', e);
        }
    }

    // ── Presence ───────────────────────────────────────────────────
    async _touchPresence() {
        const chatId = this._getActiveChatId();
        const isActive = !document.hidden && document.hasFocus();
        if (this.socket?.connected) {
            this.socket.emit('presence', { chat_id: chatId, active: isActive });
        }
        if (!chatId) return;
        try {
            await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: this._rpcHeaders(),
                body: JSON.stringify({
                    jsonrpc: '2.0', method: 'call', id: Date.now(),
                    params: {
                        model: 'whatsapp.chat',
                        method: 'action_touch_agent_presence',
                        args: [[chatId]],
                        kwargs: { is_active: isActive },
                    },
                }),
            });
        } catch (e) { /* non-fatal */ }
    }

    // ── Typing Indicator ───────────────────────────────────────────
    _showTypingIndicator(data = {}) {
        const activeChatId = this._getActiveChatId();
        if (data.chat_id && activeChatId && Number(data.chat_id) !== Number(activeChatId)) return;
        let indicator = document.getElementById('wa_typing_indicator');
        const historyDiv = document.querySelector('.wa-chat-history-content-container');
        if (!historyDiv) return;
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'wa_typing_indicator';
            indicator.className = 'wa-typing-indicator text-muted small px-3 py-2';
            indicator.textContent = 'Customer is typing...';
            historyDiv.parentElement?.appendChild(indicator);
        }
        clearTimeout(this._typingTimer);
        this._typingTimer = setTimeout(() => indicator.remove(), 3500);
    }

    // ── Media Lightbox ─────────────────────────────────────────────
    _openLightbox(src) {
        if (!src) return;
        const existing = document.getElementById('wa_media_lightbox');
        if (existing) existing.remove();
        const overlay = document.createElement('div');
        overlay.id = 'wa_media_lightbox';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.86);display:flex;align-items:center;justify-content:center;padding:24px;';
        overlay.innerHTML = `
            <button type="button" aria-label="Close" style="position:absolute;top:16px;right:20px;background:transparent;border:0;color:white;font-size:32px;line-height:1;">&times;</button>
            <img src="${src}" alt="" style="max-width:96vw;max-height:92vh;object-fit:contain;border-radius:6px;box-shadow:0 12px 40px rgba(0,0,0,.35);"/>
        `;
        overlay.addEventListener('click', (ev) => {
            if (ev.target === overlay || ev.target.tagName === 'BUTTON') overlay.remove();
        });
        document.body.appendChild(overlay);
    }

    // ── Emoji Picker ───────────────────────────────────────────────
    _toggleEmojiPicker(btn) {
        const existing = document.getElementById('wa_emoji_picker');
        if (existing) { existing.remove(); return; }
        const p = document.createElement('div');
        p.id = 'wa_emoji_picker';
        p.style.cssText = 'position:absolute;bottom:80px;left:20px;z-index:999;background:white;border-radius:12px;padding:10px;box-shadow:0 8px 30px rgba(0,0,0,0.2);width:280px;border:1px solid #ddd;';
        const search = document.createElement('input');
        search.type = 'search';
        search.placeholder = 'Search emoji';
        search.style.cssText = 'width:100%;border:1px solid #ddd;border-radius:8px;padding:6px 8px;margin-bottom:8px;';
        const grid = document.createElement('div');
        grid.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;max-height:220px;overflow:auto;';
        const emojis = [
            ['\u{1F600}','smile happy'], ['\u{1F602}','laugh'], ['\u{1F970}','love'], ['\u{1F60E}','cool'], ['\u{1F64F}','thanks please'],
            ['\u{1F44D}','yes like'], ['\u{1F525}','hot'], ['\u{1F4AF}','perfect'], ['\u2705','done check'], ['\u2764\uFE0F','heart'],
            ['\u2728','sparkle'], ['\u{1F64C}','celebrate'], ['\u{1F44B}','hello'], ['\u{1F4DE}','call'], ['\u{1F4E6}','order package'],
            ['\u{1F69A}','delivery'], ['\u{1F4B3}','payment'], ['\u{1F4C5}','date calendar'], ['\u2B50','star rating'], ['\u{1F389}','party'],
        ];
        const render = (term = '') => {
            const needle = term.toLowerCase();
            grid.innerHTML = '';
            emojis
                .filter(([emoji, keywords]) => !needle || keywords.includes(needle) || emoji.includes(term))
                .forEach(([e]) => {
                    const b = document.createElement('button');
                    b.textContent = e; b.type = 'button';
                    b.style.cssText = 'background:none;border:none;font-size:1.6rem;cursor:pointer;padding:5px;transition:transform 0.1s;';
                    b.onmouseover = () => b.style.transform = 'scale(1.2)';
                    b.onmouseout = () => b.style.transform = 'scale(1)';
                    b.onclick = () => {
                        const t = document.querySelector('.wa-premium-input textarea') || document.querySelector('.wa-premium-input');
                        if (t) { t.value += e; t.focus(); }
                        p.remove();
                    };
                    grid.appendChild(b);
                });
        };
        search.addEventListener('input', () => render(search.value.trim()));
        p.appendChild(search); p.appendChild(grid);
        render();
        document.body.appendChild(p);
        search.focus();
        const closer = (ev) => {
            if (!p.contains(ev.target) && ev.target !== btn) {
                p.remove();
                document.removeEventListener('mousedown', closer);
            }
        };
        document.addEventListener('mousedown', closer);
    }

    // ── Helpers ────────────────────────────────────────────────────
    _getActiveChatId() {
        const sidebarActive = document.querySelector('.o_whatsapp_sidebar_item.active');
        if (sidebarActive) return parseInt(sidebarActive.getAttribute('data-chat-id'));
        const hash = window.location.hash.slice(1);
        const params = new URLSearchParams(hash);
        const id = params.get('id') || params.get('res_id');
        if (id) return parseInt(id);
        const pathMatch = window.location.pathname.match(/\/odoo\/[^/]+\/(\d+)/);
        if (pathMatch) return parseInt(pathMatch[1]);
        return null;
    }

    _rpcHeaders() {
        const h = { 'Content-Type': 'application/json' };
        const csrf = window.odoo?.csrf_token || document.cookie.match(/csrf_token=([^;]+)/)?.[1];
        if (csrf) h['X-CSRFToken'] = csrf;
        return h;
    }

    async _rpc(model, method, args = [], kwargs = {}) {
        const response = await fetch('/web/dataset/call_kw', {
            method: 'POST',
            headers: this._rpcHeaders(),
            body: JSON.stringify({
                jsonrpc: '2.0', method: 'call', id: Date.now(),
                params: { model, method, args, kwargs },
            }),
        });
        const data = await response.json();
        return data.result;
    }
}

registry.category("services").add("whatsapp_realtime", {
    dependencies: ["bus_service", "action"],
    start(env, services) {
        try {
            return new WhatsAppChatHandler(env, services);
        } catch (e) {
            console.error('[WhatsApp] Fatal service start error:', e);
            return {};
        }
    },
});
