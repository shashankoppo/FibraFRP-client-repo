/** @odoo-module **/

import { registry } from "@web/core/registry";
import { playTone } from "@elsx_whatsapp_marketing/js/notification_tones";
import { animateInboxRefresh } from "@elsx_whatsapp_marketing/js/elsx_ui_motion";

// ============================================================
// WhatsApp Real-time Handler — Odoo 19 Compatible (v7.5)
// ============================================================

const WA_NOTIFICATION_TYPES = [
    'elsx_whatsapp_channel',
    'whatsapp.chat',
    'whatsapp_status_update',
];

const SCROLL_THRESHOLD = 150;
const RIGHT_PANE_STORAGE_KEY = 'elsx_whatsapp_crm_pane_open';
const PROCESSED_MESSAGE_LIMIT = 250;

export class WhatsAppChatHandler {
    constructor(env, { bus_service, action, orm }) {
        this.bus = bus_service;
        this.actionService = action;
        this.orm = orm;
        this.env = env;
        this._lastHtml = null;
        this._selectedChatId = null;
        this._lastChatId = null;
        this._refreshInterval = null;
        this._presenceInterval = null;
        this._slaInterval = null;
        this._componentInitInterval = null;
        this._historyLimit = 50;
        this._pollIntervalMs = 8000;
        this._maxPollIntervalMs = 30000;
        this._isPaging = false;
        this._userIsAtBottom = true;
        this._notificationPreferencesByAccount = {};
        this._accountByChat = {};
        this._boundHashChange = null;
        this._lastPlayedMessageId = new Set();
        this._processedMessageIds = new Set();
        this._lastBusActivity = 0; // BUG 3+8 FIX: timestamp of last Bus/Socket notification
        this._quickReplyItems = [];
        this._quickReplyActiveIndex = 0;
        this._quickReplyQueryKey = null;
        this._quickReplyFetchTimer = null;
        this._activeChatSwitchToken = 0;
        this._aiGuidanceLoadedForChatId = null;
        this._mobilePanel = null;
        this._lastViewportIsMobile = window.matchMedia('(max-width: 991px)').matches;
        this._mobileResizeTimer = null;
        try {
            sessionStorage.removeItem('wa_mobile_panel');
        } catch (e) { /* sessionStorage may be blocked */ }
        
        // --- Sidebar State ---
        this._sidebarFilter = sessionStorage.getItem('wa_sidebar_filter') || 'all';
        this._sidebarQuery = '';
        this._selectedAccountId = sessionStorage.getItem('wa_selected_account_id') ? parseInt(sessionStorage.getItem('wa_selected_account_id')) : null;
        // Per-pane fetch guards and pagination (map keyed by paneKey)
        this._isFetchingSidebar = { active: false, request: false, intervened: false };
        this._hasMoreSidebar = { active: true, request: true, intervened: true };
        this._sidebarOffsets = { active: 0, request: 0, intervened: 0 };
        
        this._initGlobalComponents();
        
        this._boundHashChange = () => {
            setTimeout(() => this._surgicalRefresh(), 250);
        };
        window.addEventListener('hashchange', this._boundHashChange);
        window.addEventListener('popstate', this._boundHashChange);
        this._boundResize = () => this._handleViewportResize();
        window.addEventListener('resize', this._boundResize);
        this._boundMobileKeydown = (ev) => this._handleMobileKeydown(ev);
        window.addEventListener('keydown', this._boundMobileKeydown);

        this._componentInitInterval = setInterval(() => this._initGlobalComponents(), 5000);

        try { this.init(); } catch (e) { console.warn('[WhatsApp] Service init error:', e); }
    }

    _normalizeActionViews(action, fallbackViews = [[false, 'form']]) {
        if (!action || typeof action !== 'object') {
            return action;
        }
        const normalized = { ...action };
        if (!Array.isArray(normalized.views) || !normalized.views.length) {
            const modes = String(normalized.view_mode || '')
                .split(',')
                .map((mode) => mode.trim())
                .filter(Boolean);
            normalized.views = modes.length
                ? modes.map((mode) => [false, mode === 'tree' ? 'list' : mode])
                : fallbackViews;
        }
        if (!normalized.view_mode && normalized.views.length) {
            normalized.view_mode = normalized.views.map((view) => view[1]).join(',');
        }
        return normalized;
    }

    _initGlobalComponents() {
        // Disabled by user request: no longer hiding the module from the menu or showing the floating chat button.
    }

    async _openTeamInbox() {
        const existingDialog = document.querySelector('.wa-floating-dialog-active');
        if (existingDialog) {
            existingDialog.style.display = existingDialog.style.display === 'none' ? 'flex' : 'none';
            return;
        }

        // Fetch the action to manipulate it natively
        let actionObj;
        try {
            const res = await this.orm.call('ir.model.data', 'check_object_reference', ['elsx_whatsapp_marketing', 'action_whatsapp_chat']);
            const actionId = res ? res[1] : false;
            if (actionId) {
                const actions = await this.orm.call('ir.actions.act_window', 'read', [[actionId]]);
                if (actions && actions.length > 0) {
                    actionObj = actions[0];
                }
            }
        } catch (e) {
            console.error('Could not fetch action details', e);
        }

        if (!actionObj) {
            actionObj = {
                type: 'ir.actions.act_window',
                res_model: 'whatsapp.chat',
                views: [[false, 'kanban'], [false, 'list'], [false, 'form']],
                name: 'WhatsApp Team Inbox'
            };
        }

        // Determine if we should open a specific chat or the general inbox
        const chatId = this._getActiveChatId();
        if (chatId) {
            actionObj.res_id = chatId;
            actionObj.views = [[false, 'form']];
        }

        // Force native Odoo Modal
        actionObj.target = 'new';
        actionObj.context = { ...(actionObj.context || {}), wa_floating_mode: true };

        await this.actionService.doAction(this._normalizeActionViews(actionObj, [[false, 'kanban'], [false, 'list'], [false, 'form']]));

        // Inject CSS to convert the centered modal into a floating bottom-right chatbox
        let retries = 0;
        const styleInterval = setInterval(() => {
            const dialogs = document.querySelectorAll('.o_dialog_container .o_dialog');
            if (dialogs.length > 0) {
                clearInterval(styleInterval);
                const lastDialog = dialogs[dialogs.length - 1];
                
                // Mark it to prevent duplicates
                lastDialog.classList.add('wa-floating-dialog-active');
                
                // Hide the backdrop for this dialog to keep the background interactive
                const backdrop = lastDialog.querySelector('.modal-backdrop') || document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.style.opacity = '0';
                    backdrop.style.pointerEvents = 'none';
                }
                
                // Convert Modal to Floating Chatbox
                lastDialog.style.cssText = `
                    position: fixed !important;
                    bottom: 100px !important;
                    right: 24px !important;
                    width: 900px !important;
                    max-width: calc(100vw - 48px) !important;
                    height: 75vh !important;
                    min-height: 580px !important;
                    max-height: calc(100vh - 160px) !important;
                    margin: 0 !important;
                    display: flex !important;
                    flex-direction: column !important;
                    box-shadow: 0 12px 60px rgba(0,0,0,0.18) !important;
                    border-radius: 16px !important;
                    overflow: hidden !important;
                    z-index: 2050 !important;
                    top: auto !important;
                    left: auto !important;
                    transform: translateY(20px) !important;
                    opacity: 0 !important;
                    animation: wa-modal-slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
                    background: #fff !important;
                    pointer-events: auto !important;
                    border: 1px solid rgba(0,0,0,0.05) !important;
                `;

                // --- Mobile Initial State Setup ---
                if (window.innerWidth <= 991) {
                    setTimeout(() => {
                        const sidebar = lastDialog.querySelector('.wa-left-sidebar');
                        const main = lastDialog.querySelector('.o_whatsapp_chat_main');
                        const chatId = this._getActiveChatId();
                        
                        if (!chatId) {
                            if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
                            if (main) { main.classList.add('d-none'); main.classList.remove('d-flex'); }
                        } else {
                            if (sidebar) { sidebar.classList.add('d-none'); sidebar.classList.remove('d-flex'); }
                            if (main) { main.classList.remove('d-none'); main.classList.add('d-flex'); }
                        }
                    }, 100);
                }
                
                // Add slide-up animation
                if (!document.getElementById('wa-modal-anim-style')) {
                    const s = document.createElement('style');
                    s.id = 'wa-modal-anim-style';
                    s.innerHTML = `@keyframes wa-modal-slide-up { to { transform: translateY(0); } }`;
                    document.head.appendChild(s);
                }

                const modalDialog = lastDialog.querySelector('.modal-dialog');
                if (modalDialog) {
                    modalDialog.style.cssText = `
                        margin: 0 !important;
                        height: 100% !important;
                        max-width: 100% !important;
                        padding: 0 !important;
                    `;
                }

                const content = lastDialog.querySelector('.modal-content');
                if (content) {
                    content.style.cssText = `
                        height: 100% !important;
                        border: none !important;
                        border-radius: 16px !important;
                        overflow: hidden !important;
                        background: #fff !important;
                    `;
                }

                const body = lastDialog.querySelector('.modal-body');
                if (body) {
                    body.style.cssText = `
                        padding: 0 !important;
                        height: 100% !important;
                        display: flex !important;
                        flex-direction: column !important;
                    `;
                }

                // Hide native control panel in floating mode to save space
                const cp = lastDialog.querySelector('.o_control_panel');
                if (cp) cp.style.setProperty('display', 'none', 'important');

                // Style the Modal Header like a Chat Header
                const modalHeader = lastDialog.querySelector('.modal-header');
                if (modalHeader) {
                    modalHeader.style.cssText = `
                        background: #00A884 !important;
                        color: white !important;
                        padding: 14px 20px !important;
                        border-bottom: none !important;
                        display: flex !important;
                        align-items: center !important;
                        justify-content: space-between !important;
                        border-top-left-radius: 16px !important;
                        border-top-right-radius: 16px !important;
                    `;
                    
                    const title = modalHeader.querySelector('.modal-title');
                    if (title) {
                        title.innerHTML = `
                            <div class="d-flex align-items-center gap-3">
                                <div class="rounded-circle bg-white d-flex align-items-center justify-content-center shadow-sm" style="width:36px;height:36px;color:#00A884;">
                                    <i class="fa fa-whatsapp"></i>
                                </div>
                                <div class="d-flex flex-column">
                                    <span style="font-size: 1.05rem; font-weight: 700; line-height: 1.2;">Team Inbox</span>
                                    <span style="font-size: 0.75rem; opacity: 0.85; font-weight: 400;"><i class="fa fa-circle text-white me-1" style="font-size:6px; vertical-align:middle;"></i> Active Session</span>
                                </div>
                            </div>
                        `;
                    }
                    
                    const closeBtn = modalHeader.querySelector('.btn-close');
                    if (closeBtn) {
                        closeBtn.style.cssText = `
                            filter: invert(1) brightness(200%);
                            opacity: 0.8;
                            margin: 0 !important;
                            padding: 10px !important;
                            transition: opacity 0.2s;
                        `;
                        closeBtn.onmouseover = () => closeBtn.style.opacity = '1';
                        closeBtn.onmouseout = () => closeBtn.style.opacity = '0.8';
                    }
                }
                
                const footer = lastDialog.querySelector('.modal-footer');
                if (footer) footer.style.setProperty('display', 'none', 'important');
            } else if (retries++ > 20) {
                clearInterval(styleInterval);
            }
        }, 50);
    }

    async _rpc(model, method, args = [], kwargs = {}) {
        return await this.orm.call(model, method, args, kwargs);
    }

    async _getNotificationPreferences(chatId = null) {
        chatId = chatId || this._getActiveChatId();
        if (!chatId) return null;
        let accountId = this._accountByChat[chatId];
        if (!accountId) {
            try {
                const chatData = await this._rpc('whatsapp.chat', 'read', [[chatId], ['account_id']]);
                const accountField = chatData?.[0]?.account_id;
                accountId = Array.isArray(accountField) ? accountField[0] : accountField;
                if (!accountId) return null;
                this._accountByChat[chatId] = accountId;
            } catch (e) { return null; }
        }
        if (!this._notificationPreferencesByAccount[accountId]) {
            try {
                const accountData = await this._rpc('whatsapp.account', 'read', [
                    [accountId], ['notification_enabled', 'notification_sound_receive', 'notification_sound_send'],
                ]);
                this._notificationPreferencesByAccount[accountId] = accountData?.[0] || null;
            } catch (e) { return null; }
        }
        return this._notificationPreferencesByAccount[accountId];
    }

    async _playSound(type, chatId = null, messageId = null) {
        if (messageId) {
            if (this._lastPlayedMessageId.has(messageId)) return;
            this._lastPlayedMessageId.add(messageId);
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
        } catch (e) { /* silent fail */ }
    }

    _messageEventKey(payload = {}) {
        const messageId = payload.message_id || payload.message?.id || payload.id;
        if (!messageId) return null;
        return `${payload.chat_id || payload.message?.chat_id || 'chat'}:${messageId}`;
    }

    _isDuplicateNewMessage(payload = {}) {
        if (payload?.type !== 'new_message') return false;
        const key = this._messageEventKey(payload);
        if (!key) return false;
        if (this._processedMessageIds.has(key)) {
            return true;
        }
        this._processedMessageIds.add(key);
        if (this._processedMessageIds.size > PROCESSED_MESSAGE_LIMIT) {
            const first = this._processedMessageIds.values().next().value;
            this._processedMessageIds.delete(first);
        }
        return false;
    }

    // ── Socket.IO ──────────────────────────────────────────────────
    async initSocket() {
        if (typeof io === 'undefined') return;
        if (this.socket) this.socket.disconnect();

        let socketUrl = '';
        try {
            const sysParam = await this._rpc('whatsapp.chat', 'get_sidecar_url', []);
            if (sysParam) {
                socketUrl = sysParam;
                if (socketUrl.includes('sidecar')) {
                    socketUrl = socketUrl.replace('sidecar', window.location.hostname);
                }
            }
        } catch (e) {
            console.warn('[WhatsApp] Could not fetch sidecar url:', e);
        }
        if (!socketUrl) return;

        this.socket = io(socketUrl, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 10,
            reconnectionDelay: 2000,
            timeout: 10000,
        });

        this.socket.on('connect', () => {
            this._updateConnectionStatus('connected');
            this._touchPresence();
            this._surgicalRefresh();
        });
        this.socket.on('whatsapp_event', (data) => {
            // BUG 3 FIX: Record socket activity to suppress redundant polling
            this._lastBusActivity = Date.now();
            if (data?.type === 'status_update' && (data.message_id || data.message?.id) && (data.status || data.message?.status)) {
                const messageId = data.message_id || data.message?.id;
                const status = data.status || data.message?.status;
                this._patchMessageStatus(data.chat_id, messageId, status);
                if (data.chat_id) {
                    this._patchSidebarStatus(data.chat_id, status);
                    this._updateSidebarForChat(data.chat_id);
                }
                return;
            }
            if (this._isDuplicateNewMessage(data || {})) {
                return;
            }

            // Reset cache so incoming message ALWAYS re-renders
            this._lastHtml = null;

            const activeChatId = this._getActiveChatId();
            
            // 1. Refresh UI if it's for the current chat (or we are in list view)
            if (!activeChatId || activeChatId == data.chat_id) {
                this._surgicalRefresh();
            }

            // 2. Update sidebar preview + counts
            if (data.chat_id) {
                this._updateSidebarForChat(data.chat_id);
            } else {
                this._updateSidebarCounts();
            }

            // 3. Play sound for ALL inbound messages regardless of active chat
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
        if (dot) {
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

        // We silently fall back to 8-second polling if the socket disconnects.
        // Displaying a persistent "Computer not connected" banner causes user confusion
        // because the application still functions correctly via Odoo RPC polling.
        const banner = document.getElementById('wa-connection-banner');
        if (banner) banner.remove();
    }

    // ── Initialization ─────────────────────────────────────────────
    init() {
        try {
            // Subscribe to channels using modern Odoo 19 Bus API
            this.bus.addChannel('elsx_whatsapp_channel');
            
            // Subscribe directly to modern Odoo 19 Bus notification types
            this._busSubscriptions = [];

            WA_NOTIFICATION_TYPES.forEach(type => {
                const callback = (payload) => {
                    this._onNotification(type, payload);
                };
                this.bus.subscribe(type, callback);
                this._busSubscriptions.push({ type, callback });
            });

            const typingCallback = (payload) => {
                this._showTypingIndicator(payload || {});
            };
            this.bus.subscribe('whatsapp_typing', typingCallback);
            this._busSubscriptions.push({ type: 'whatsapp_typing', callback: typingCallback });

        } catch (e) {
            console.error('[WhatsApp] Bus subscription error:', e);
        }

        // Initial load of history — wait for Odoo form DOM to settle then fetch
        setTimeout(() => {
            this._attachScrollListener();
            this._injectScrollFAB();
            this._injectMobileBackButton();
            this._applyRightPanePreference();
            this._syncMobileLayout();
            this._tickSlaTimers();
            this._initSidebarEngine();
            this._enhanceComposer();

            // KEY FIX: Actively fetch & render history on first paint
            const chatId = this._getActiveChatId();
            if (chatId) {
                this._lastChatId = chatId;
                this._surgicalRefresh(chatId);
            }
        }, 600);

        // FALLBACK: MutationObserver — if Odoo's form renders the mount div AFTER our timeout,
        // we catch it here and trigger the first load. Prevents blank chat on slow machines.
        this._historyMountObserver = new MutationObserver(() => {
            const mount = document.getElementById('wa-custom-history-mount');
            if (mount && !mount.dataset.waBound) {
                mount.dataset.waBound = 'true';
                const chatId = this._getActiveChatId();
                if (chatId && !mount.querySelector('[data-wa-message-id]')) {
                    this._lastChatId = chatId;
                    this._surgicalRefresh(chatId);
                }
                this._attachScrollListener();
                this._injectScrollFAB();
                this._applyRightPanePreference();
                this._syncMobileLayout();
                this._tickSlaTimers();
                this._initSidebarEngine();
                this._enhanceComposer();
            }
        });
        this._historyMountObserver.observe(document.body, { childList: true, subtree: true });

        // Fallback polling — fires every 8 seconds as safety net when bus/socket is absent.
        // BUG 3+8 FIX: Skip polling when Bus was active recently (<12s) or not on WA view.
        this._startFallbackPolling();

        // Presence heartbeat every 45 seconds
        this._presenceInterval = setInterval(() => this._touchPresence(), 45000);
        this._slaInterval = setInterval(() => this._tickSlaTimers(), 60000);
        if (!this._boundVisibilityChange) {
            this._boundVisibilityChange = () => this._touchPresence();
        }
        document.addEventListener('visibilitychange', this._boundVisibilityChange);

        // Global click handler
        if (!this._boundGlobalClick) {
            this._boundGlobalClick = this._handleGlobalClicks.bind(this);
        }
        document.addEventListener('click', this._boundGlobalClick, true);

        if (!this._boundComposerInput) {
            this._boundComposerInput = (e) => {
                const textarea = e.target.closest('.wa-premium-input textarea') || e.target.closest('.wa-premium-input');
                if (!textarea) return;
                this._resizeComposer(textarea);
                this._updateComposerCounter(textarea);
                this._queueQuickReplySuggestions(textarea);
            };
        }
        document.addEventListener('input', this._boundComposerInput);

        // Enter to Send & Slash command for Quick Replies
        if (!this._boundKeydown) {
            this._boundKeydown = (e) => {
                const textarea = e.target.closest('.wa-premium-input textarea') || e.target.closest('.wa-premium-input');
                if (!textarea) return;

                if (e.key === 'Escape' && this._isQuickReplyOpen()) {
                    e.preventDefault();
                    this._hideQuickReplyPopover();
                    return;
                }

                if (this._isQuickReplyOpen() && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
                    e.preventDefault();
                    this._moveQuickReplySelection(e.key === 'ArrowDown' ? 1 : -1);
                    return;
                }

                if (this._isQuickReplyOpen() && e.key === 'Tab') {
                    e.preventDefault();
                    this._insertQuickReply(this._quickReplyItems[this._quickReplyActiveIndex], textarea);
                    return;
                }

                // Enter to Send
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (this._isQuickReplyOpen() && this._quickReplyItems[this._quickReplyActiveIndex]) {
                        this._insertQuickReply(this._quickReplyItems[this._quickReplyActiveIndex], textarea);
                        return;
                    }
                    const sendBtn = textarea.closest('.o_form_view')?.querySelector('button[name="action_send_quick_reply"]')
                        || document.querySelector('button[name="action_send_quick_reply"]');
                    if (sendBtn) sendBtn.click();
                }
            };
        }
        document.addEventListener('keydown', this._boundKeydown);

        // Attempt socket connection after loadJS
        if (typeof io !== 'undefined') {
            this.initSocket();
        }
    }

    // ── Custom JS Sidebar Engine (SPA) ─────────────────────────────
    _hasWhatsAppView() {
        return !!(
            document.querySelector('.o_whatsapp_chat_form_view')
            || document.querySelector('.o_whatsapp_inbox_kanban')
        );
    }

    _startFallbackPolling() {
        if (this._refreshInterval) return;
        const tick = async () => {
            this._refreshInterval = null;
            let shouldBackoff = true;
            try {
                if (
                    document.visibilityState !== 'visible'
                    || Date.now() - this._lastBusActivity < 12000
                    || !this._hasWhatsAppView()
                ) {
                    shouldBackoff = false;
                } else {
                    const chatId = this._getActiveChatId();
                    if (chatId) {
                        await this._surgicalRefresh();
                        shouldBackoff = false;
                    }
                }
            } catch (error) {
                console.warn('[WhatsApp] fallback poll failed:', error);
                shouldBackoff = true;
            } finally {
                this._pollIntervalMs = shouldBackoff
                    ? Math.min(this._maxPollIntervalMs, this._pollIntervalMs + 4000)
                    : 8000;
                this._refreshInterval = setTimeout(tick, this._pollIntervalMs);
            }
        };
        this._refreshInterval = setTimeout(tick, this._pollIntervalMs);
    }

    _initSidebarEngine() {
        // Initialize three sidebar panes
        this._paneIds = {
            active: 'wa-active-sidebar-mount',
            request: 'wa-request-sidebar-mount',
            intervened: 'wa-intervened-sidebar-mount',
        };
        // Reset per-pane pagination on each sidebar engine init
        Object.keys(this._paneIds).forEach(k => {
            this._sidebarOffsets[k] = 0;
            this._hasMoreSidebar[k] = true;
            this._isFetchingSidebar[k] = false;
        });

        this._initAccountSelectorDropdown();

        // Initialize each pane: guard + infinite scroll
        Object.entries(this._paneIds).forEach(([paneKey, paneId]) => {
            const mount = document.getElementById(paneId);
            if (!mount || mount.dataset.sidebarInit) return;
            mount.dataset.sidebarInit = 'true';
            mount.addEventListener('scroll', () => {
                const distFromBottom = mount.scrollHeight - mount.scrollTop - mount.clientHeight;
                // Use per-pane map key — NOT the whole object — to check guard
                if (distFromBottom < 100 && !this._isFetchingSidebar[paneKey] && this._hasMoreSidebar[paneKey]) {
                    this._fetchAndRenderSidebar(paneKey, this._sidebarOffsets[paneKey], true);
                }
            });
        });

        // Search Input
        const searchInput = document.getElementById('wa-sidebar-search-input');
        if (searchInput && !searchInput._waSearchBound) {
            searchInput._waSearchBound = true;
            searchInput.value = this._sidebarQuery;
            let debounce;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(debounce);
                debounce = setTimeout(() => {
                    this._sidebarQuery = e.target.value.trim();
                    Object.keys(this._paneIds).forEach(k => {
                        this._sidebarOffsets[k] = 0;
                        this._hasMoreSidebar[k] = true;
                    });
                    this._refreshAllPanes();
                }, 300);
            });
        }

        // Pane Tabs
        const paneTabs = document.querySelectorAll('.wa-pane-tab');
        const savedPane = sessionStorage.getItem('wa_active_pane') || 'active';
        
        paneTabs.forEach(tab => {
            if (tab._waTabBound) return;
            tab._waTabBound = true;
            tab.addEventListener('click', () => {
                const targetPane = tab.dataset.pane;
                sessionStorage.setItem('wa_active_pane', targetPane);
                
                // Update tab styles
                paneTabs.forEach(t => {
                    t.classList.remove('text-dark', 'border-success');
                    t.classList.add('text-muted', 'border-transparent');
                });
                tab.classList.remove('text-muted', 'border-transparent');
                tab.classList.add('text-dark', 'border-success');
                
                // Toggle mount visibility
                document.querySelectorAll('.wa-pane-mount').forEach(mount => {
                    mount.classList.add('d-none');
                });
                const targetMount = document.getElementById(this._paneIds[targetPane]);
                if (targetMount) {
                    targetMount.classList.remove('d-none');
                }
            });
            
            // Apply saved state on init
            if (tab.dataset.pane === savedPane) {
                tab.click();
            }
        });

        // Filter Pills
        const filters = document.querySelectorAll('.wa-filter-btn');

        // BUG FIX: Deactivate ALL pills first to clear any inline XML styles,
        // so only the persisted/active filter gets the active highlight.
        filters.forEach(f => {
            f.style.background = '';
            f.style.color = '';
            f.classList.remove('bg-success', 'text-white');
            f.classList.add('bg-light', 'text-muted');
        });

        filters.forEach(btn => {
            if (btn._waFilterBound) return;
            btn._waFilterBound = true;
            btn.addEventListener('click', () => {
                filters.forEach(f => {
                    f.style.background = '';
                    f.style.color = '';
                    f.classList.remove('bg-success', 'text-white');
                    f.classList.add('bg-light', 'text-muted');
                });
                btn.classList.remove('bg-light', 'text-muted');
                btn.classList.add('bg-success', 'text-white');
                this._sidebarFilter = btn.dataset.filter;
                sessionStorage.setItem('wa_sidebar_filter', this._sidebarFilter);
                Object.keys(this._paneIds).forEach(k => {
                    this._sidebarOffsets[k] = 0;
                    this._hasMoreSidebar[k] = true;
                });
                this._refreshAllPanes();
            });
            // Restore active state for the persisted filter
            if (btn.dataset.filter === this._sidebarFilter) {
                btn.style.background = '';
                btn.style.color = '';
                btn.classList.remove('bg-light', 'text-muted');
                btn.classList.add('bg-success', 'text-white');
            }
        });

        // Initial Load: render all three panes
        this._refreshAllPanes();
    }

    // Helper: refresh all sidebar panes from offset 0
    _refreshAllPanes() {
        this._updateSidebarCounts();
        Object.keys(this._paneIds).forEach(paneKey => {
            this._fetchAndRenderSidebar(paneKey, 0, false);
        });
    }

    async _initAccountSelectorDropdown() {
        const mount = document.getElementById('wa-account-selector-mount');
        if (!mount || mount.dataset.dropdownInit) return;
        mount.dataset.dropdownInit = 'true';

        try {
            const accounts = await this._rpc('whatsapp.account', 'search_read', [[['active', '=', true]], ['id', 'name']]);
            if (!accounts || accounts.length === 0) {
                mount.innerHTML = '';
                return;
            }

            let optionsHtml = `<option value="">All Accounts</option>`;
            accounts.forEach(acc => {
                const selected = this._selectedAccountId === acc.id ? 'selected' : '';
                optionsHtml += `<option value="${acc.id}" ${selected}>${acc.name}</option>`;
            });

            mount.innerHTML = `
                <div class="position-relative">
                    <select id="wa-account-dropdown" class="form-select shadow-sm" style="background: #f0f2f5; border: 1px solid rgba(0,0,0,0.05); border-radius: 8px; padding: 8px 12px; font-size: 0.85rem; font-weight: 600; color: #111B21; cursor: pointer; transition: all 0.2s; -webkit-appearance: none; -moz-appearance: none; appearance: none; background-image: url('data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22292.4%22%20height%3D%22292.4%22%3E%3Cpath%20fill%3D%22%2523555%22%20d%3D%22M287%2069.4a17.6%2017.6%200%200%200-13-5.4H18.4c-5%200-9.3%201.8-12.9%205.4A17.6%2017.6%200%200%200%200%2082.2c0%205%201.8%209.3%205.4%2012.9l128%20127.9c3.6%203.6%207.8%205.4%2012.8%205.4s9.2-1.8%2012.8-5.4L287%2095c3.5-3.5%205.4-7.8%205.4-12.8%200-5-1.9-9.2-5.5-12.8z%22%2F%3E%3C%2Fsvg%3E'); background-repeat: no-repeat; background-position: right%2012px%20top%2050%25; background-size:%2010px%20auto;">
                        ${optionsHtml}
                    </select>
                </div>
            `;

            const selectEl = document.getElementById('wa-account-dropdown');
            if (selectEl) {
                selectEl.addEventListener('change', (e) => {
                    const val = e.target.value;
                    this._selectedAccountId = val ? parseInt(val) : null;
                    if (this._selectedAccountId) {
                        sessionStorage.setItem('wa_selected_account_id', this._selectedAccountId);
                    } else {
                        sessionStorage.removeItem('wa_selected_account_id');
                    }
                    this._refreshAllPanes();
                });
            }
        } catch (e) {
            console.error('[WhatsApp] Failed to init account selector dropdown:', e);
        }
    }

    _matchesFilterAndPane(chat, filterType, paneKey) {
        if (chat.is_archived) return false;

        // Account filter constraint
        if (this._selectedAccountId && chat.account_id !== this._selectedAccountId) {
            return false;
        }

        // 1. Check pane matching
        let paneMatch = false;
        // BUG 6 FIX: Reliable user ID resolution — Odoo 19 env.user may not have .id
        // Note: `odoo` is NOT a global in ES module scope, so we use try-catch
        let currentUserId = null;
        try {
            currentUserId = this.env?.user?.userId || this.env?.user?.id || this.env?.services?.user?.userId || null;
        } catch (e) { /* fallback to null */ }
        if (!currentUserId) {
            try { currentUserId = window.__session_info?.uid || null; } catch (e) {}
        }
        if (paneKey === 'active') { // Mine
            paneMatch = (chat.assigned_user_id === currentUserId);
        } else if (paneKey === 'request') { // Unassigned
            paneMatch = (!chat.assigned_user_id);
        } else if (paneKey === 'intervened') { // All
            paneMatch = true;
        }
        if (!paneMatch) return false;

        // 2. Check filter matching
        if (filterType === 'all') {
            return true;
        } else if (filterType === 'open') {
            return chat.state === 'open';
        } else if (filterType === 'mine') {
            return chat.assigned_user_id === currentUserId;
        } else if (filterType === 'unread') {
            return chat.unread_count > 0;
        } else if (filterType === 'snoozed') {
            return chat.state === 'snoozed';
        } else if (filterType === 'resolved') {
            return chat.state === 'resolved';
        }
        return true;
    }

    _renderChatCardHtml(chat) {
        const isActive = this._getActiveChatId() === chat.id ? 'active' : '';
        const unreadBadge = chat.unread_count > 0 ? `<div class="badge rounded-pill bg-success shadow-sm o_whatsapp_unread_count" style="padding: 4px 8px; font-size: 0.7rem;">${chat.unread_count}</div>` : '';
        const pinnedIcon = chat.is_pinned ? `<i class="fa fa-thumb-tack text-muted" title="Pinned" style="font-size: 0.7rem;"></i>` : '';
        const archivedIcon = chat.is_archived ? `<i class="fa fa-archive text-muted" title="Archived" style="font-size: 0.7rem;"></i>` : '';

        let slaBadge = '';
        if (chat.sla_status === 'breached') {
            slaBadge = `<span class="badge bg-danger mt-1 shadow-sm" style="font-size: 0.6rem; animation: pulse 2s infinite;">SLA Breach</span>`;
        } else if (chat.sla_status === 'active') {
            slaBadge = `<span class="badge bg-warning text-dark mt-1 shadow-sm wa-sla-timer" data-wa-sla-minutes="${chat.sla_timer_minutes || 0}" style="font-size: 0.6rem;"><span class="wa-sla-value">${chat.sla_timer_minutes || 0}</span>m wait</span>`;
        }

        let statusIcon = '';
        if (chat.last_message_direction === 'outbound') {
            if (chat.last_message_status === 'sent') statusIcon = `<i class="fa fa-check text-muted" title="Sent" style="font-size: 0.7rem;"></i>`;
            else if (chat.last_message_status === 'delivered') statusIcon = `<span class="d-flex align-items-center" style="margin-left: -2px;"><i class="fa fa-check text-muted" title="Delivered" style="font-size: 0.7rem;"></i><i class="fa fa-check text-muted" title="Delivered" style="font-size: 0.7rem; margin-left: -4px;"></i></span>`;
            else if (chat.last_message_status === 'read') statusIcon = `<span class="d-flex align-items-center" style="margin-left: -2px;"><i class="fa fa-check text-info" title="Read" style="font-size: 0.7rem;"></i><i class="fa fa-check text-info" title="Read" style="font-size: 0.7rem; margin-left: -4px;"></i></span>`;
        }

        const safeName = (chat.display_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const safeBody = (chat.last_message_body || 'No messages yet').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        const initial = chat.display_name_initial || '?';
        const colors = ['#1abc9c', '#2ecc71', '#3498db', '#9b59b6', '#34495e', '#16a085', '#27ae60', '#2980b9', '#8e44ad', '#2c3e50', '#f1c40f', '#e67e22', '#e74c3c', '#95a5a6', '#f39c12', '#d35400', '#c0392b', '#7f8c8d'];
        let hash = 0;
        for (let i = 0; i < safeName.length; i++) hash = safeName.charCodeAt(i) + ((hash << 5) - hash);
        const avatarColor = colors[Math.abs(hash) % colors.length];

        const accountBadge = chat.account_name ? `<span class="badge text-white" style="background: rgba(0, 168, 132, 0.7); font-size: 0.65rem; border-radius: 4px; padding: 2px 6px;">${chat.account_name}</span>` : '';
        const agentBadge = chat.assigned_user_name ? `<span class="badge text-dark" style="background: rgba(0, 0, 0, 0.05); font-size: 0.65rem; border-radius: 4px; padding: 2px 6px;"><i class="fa fa-user-o me-1"></i>${chat.assigned_user_name}</span>` : `<span class="badge text-muted" style="background: rgba(0, 0, 0, 0.03); font-size: 0.65rem; border-radius: 4px; padding: 2px 6px; border: 1px dashed rgba(0,0,0,0.1);"><i class="fa fa-user-times me-1"></i>Unassigned</span>`;

        return `
            <button type="button" class="o_whatsapp_sidebar_btn p-0 border-0 bg-transparent w-100 text-start">
                <div class="p-2 px-3 border-bottom cursor-pointer o_whatsapp_sidebar_item hover-bg-light position-relative ${isActive}"
                    data-chat-id="${chat.id}" style="transition: all 0.2s; border-left: 4px solid transparent;">
                    <div class="d-flex align-items-center">
                        <div class="o_whatsapp_avatar position-relative shadow-sm d-flex align-items-center justify-content-center text-white fw-bold" style="background: ${avatarColor} !important; border-radius: 50%; user-select: none;">${initial}</div>
                        <div class="ms-3 flex-grow-1 overflow-hidden">
                            <div class="d-flex justify-content-between align-items-start mb-1">
                                <div class="fw-bold text-truncate o_whatsapp_chat_item_name" style="max-width: 140px; font-size: 1.05rem;">${safeName}</div>
                                <div class="d-flex flex-column align-items-end">
                                    <div class="small text-muted text-nowrap" style="font-size: 0.75rem; min-width: 60px; text-align: right;">${chat.last_message_date_str || ''}</div>
                                    ${slaBadge}
                                </div>
                            </div>
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <div class="small text-muted text-truncate d-flex align-items-center gap-1" style="max-width: 140px; font-size: 0.85rem;">
                                    ${statusIcon}
                                    ${safeBody}
                                </div>
                                <div class="d-flex align-items-center gap-1">
                                    ${chat.needs_reply ? '<span class="badge bg-danger rounded-pill" style="font-size: 0.65rem;">Needs Reply</span>' : ''}
                                    ${pinnedIcon}
                                    ${archivedIcon}
                                    ${unreadBadge}
                                </div>
                            </div>
                            <div class="d-flex align-items-center gap-1 mt-1 flex-wrap">
                                ${accountBadge}
                                ${agentBadge}
                            </div>
                        </div>
                    </div>
                </div>
            </button>
        `;
    }

    async _updateSidebarCounts() {
        try {
            const counts = await this._rpc('whatsapp.chat', 'get_sidebar_counts', [], {
                filter_type: this._sidebarFilter,
                search_query: this._sidebarQuery,
                account_id: this._selectedAccountId,
            });
            if (counts) {
                Object.entries(counts).forEach(([paneKey, count]) => {
                    const badge = document.querySelector(`.wa-pane-count-${paneKey}`);
                    if (badge) {
                        badge.textContent = count;
                    }
                });
            }
        } catch (e) {
            console.warn('[WhatsApp] Failed to fetch sidebar counts:', e);
        }
    }

    // Fetch and render sidebar for a specific pane
    // paneKey: 'active' | 'request' | 'intervened'
    async _fetchAndRenderSidebar(paneKey, offset = 0, append = false) {
        // Guard is always a map — initialized in constructor
        if (this._isFetchingSidebar[paneKey]) return;
        this._isFetchingSidebar[paneKey] = true;
        const mountId = this._paneIds[paneKey];
        const mount = document.getElementById(mountId);
        if (!mount) { this._isFetchingSidebar[paneKey] = false; return; }

        if (!append) {
            mount.innerHTML = '<div class="text-center p-4 mt-5"><i class="fa fa-circle-o-notch fa-spin fa-2x text-success mb-2"></i><div class="small text-muted">Loading chats...</div></div>';
            this._sidebarOffsets[paneKey] = 0;
            this._hasMoreSidebar[paneKey] = true;
        } else {
            mount.insertAdjacentHTML('beforeend', '<div id="wa-sidebar-loader" class="text-center p-2"><i class="fa fa-circle-o-notch fa-spin text-muted"></i></div>');
        }

        try {
            const limit = 20;
            const chats = await this._rpc('whatsapp.chat', 'get_sidebar_chats', [], {
                filter_type: this._sidebarFilter,
                search_query: this._sidebarQuery,
                offset: offset,
                limit: limit,
                pane: paneKey,
                account_id: this._selectedAccountId,
            });

            const loader = document.getElementById('wa-sidebar-loader');
            if (loader) loader.remove();
            if (!append) mount.innerHTML = '';

            if (!chats || chats.length === 0) {
                if (!append) mount.innerHTML = '<div class="text-center p-5 text-muted"><i class="fa fa-inbox fa-3x mb-3 opacity-25"></i><div>No conversations found</div></div>';
                this._hasMoreSidebar[paneKey] = false;
                this._isFetchingSidebar[paneKey] = false;
                return;
            }

            this._hasMoreSidebar[paneKey] = chats.length === limit;
            this._sidebarOffsets[paneKey] += chats.length;

            let html = '';
            const existingChatIds = new Set(
                Array.from(mount.querySelectorAll('.o_whatsapp_sidebar_item[data-chat-id]'))
                    .map((el) => el.getAttribute('data-chat-id'))
            );
            chats.forEach(chat => {
                try {
                    const chatId = String(chat.id);
                    if (append && existingChatIds.has(chatId)) return;
                    existingChatIds.add(chatId);
                    html += this._renderChatCardHtml(chat);
                } catch (renderErr) {
                    console.error('[WhatsApp] Failed to render chat card:', chat.id, renderErr);
                    // Skip broken cards instead of killing entire sidebar
                }
            });
            mount.insertAdjacentHTML('beforeend', html);
            animateInboxRefresh(mount, { level: "subtle" });
        } catch (e) {
            console.error('[WhatsApp] Sidebar fetch error for pane:', paneKey, e);
            if (!append && mount) mount.innerHTML = '<div class="text-center p-3 text-danger"><i class="fa fa-warning"></i> Error loading: ' + (e.message || String(e)).replace(/</g, '&lt;') + '</div>';
        }
        this._isFetchingSidebar[paneKey] = false;
        // BUG 5 FIX: Removed redundant _bindSidebarClickHandlers() — global click handler covers sidebar clicks
    }

    _bindSidebarClickHandlers() {
        const sidebars = document.querySelectorAll('.wa-left-sidebar');
        sidebars.forEach(sidebar => {
            if (sidebar._waClickBound) return;
            sidebar._waClickBound = true;
            sidebar.addEventListener('click', (ev) => {
                const item = ev.target.closest('.o_whatsapp_sidebar_item');
                if (!item) return;
                const chatId = parseInt(item.getAttribute('data-chat-id'));
                if (chatId) {
                    this._selectedChatId = chatId;
                    this._lastChatId = chatId;
                    sessionStorage.setItem('wa_selected_chat_id', chatId);
                }
            });
        });
    }


    // ── Scroll Intelligence & Infinite Pagination ────────────────────
    _attachScrollListener() {
        const historyWrappers = document.querySelectorAll('.o_whatsapp_chat_history');
        let activeWrapper = null;
        for (let i = 0; i < historyWrappers.length; i++) {
            if (historyWrappers[i].offsetParent !== null) {
                activeWrapper = historyWrappers[i];
                break;
            }
        }
        if (!activeWrapper) return;

        const historyDiv = activeWrapper.querySelector('.wa-chat-history-content-container') || activeWrapper;
        const oContent = activeWrapper.closest('.o_content');

        const bindScroll = (el) => {
            if (!el || el._waScrollBound) return;
            el._waScrollBound = true;
            el.addEventListener('scroll', () => {
                const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
                this._userIsAtBottom = distFromBottom < SCROLL_THRESHOLD;
                this._toggleScrollFAB(!this._userIsAtBottom);
            });
        };

        bindScroll(historyDiv);
        if (oContent) bindScroll(oContent);

        // Infinite Scroll using Intersection Observer
        if (window.IntersectionObserver) {
            // Re-bind top observer when DOM changes
            if (!this._bindTopObserver) {
                this._bindTopObserver = () => {
                    if (this._topObserver) this._topObserver.disconnect();
                    const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
                    const firstMsg = mount.querySelector('.wa-message-row');
                    if (firstMsg) {
                        this._topObserver = new IntersectionObserver((entries) => {
                            if (this._isInitialScroll) return; // Prevent loop during programmatic scroll
                            if (entries[0].isIntersecting && historyDiv.scrollTop < 100) {
                                // Only trigger pagination if there is actually a scrollbar
                                if (historyDiv.scrollHeight > historyDiv.clientHeight + 50) {
                                    this._topObserver.disconnect();
                                    this._historyLimit += 100;
                                    this._isPaging = true;
                                    this._surgicalRefresh();
                                }
                            }
                        }, { root: historyDiv, threshold: 0.1 });
                        this._topObserver.observe(firstMsg);
                    }
                };
            }
            this._bindTopObserver();
        }

        // Use ResizeObserver to catch delayed image loads
        if (window.ResizeObserver) {
            const ro = new ResizeObserver(() => {
                if (this._userIsAtBottom) {
                    historyDiv.scrollTop = historyDiv.scrollHeight;
                }
            });
            const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
            if (mount) ro.observe(mount);
        }
    }

    _scrollToBottom(force = false, options = {}) {
        // Find the visible scroll container (Odoo might keep old form views hidden in DOM)
        const historyWrappers = document.querySelectorAll('.o_whatsapp_chat_history');
        let activeWrapper = null;
        for (let i = 0; i < historyWrappers.length; i++) {
            if (historyWrappers[i].offsetParent !== null) {
                activeWrapper = historyWrappers[i];
                break;
            }
        }
        if (!activeWrapper) return;

        // The actual scrollable element based on whatsapp.css
        const historyDiv = activeWrapper.querySelector('.wa-chat-history-content-container') || activeWrapper;
        
        // Odoo native scroll wrapper
        const oContent = activeWrapper.closest('.o_content');
        const scrollTargets = [historyDiv];
        if (oContent) {
            scrollTargets.push(oContent);
        }
        const previousScrollBehavior = new Map();
        const useInstantScroll = !!options.instant;
        const setInstantScroll = () => {
            if (!useInstantScroll) return;
            scrollTargets.forEach((target) => {
                previousScrollBehavior.set(target, target.style.scrollBehavior);
                target.style.scrollBehavior = 'auto';
            });
        };
        const restoreScrollBehavior = () => {
            if (!useInstantScroll) return;
            scrollTargets.forEach((target) => {
                const previous = previousScrollBehavior.get(target);
                if (previous) {
                    target.style.scrollBehavior = previous;
                } else {
                    target.style.removeProperty('scroll-behavior');
                }
            });
        };

        if (force || this._userIsAtBottom) {
            this._isInitialScroll = true;
            setInstantScroll();
            
            const doScroll = () => {
                scrollTargets.forEach((target) => {
                    target.scrollTop = target.scrollHeight + 1000;
                });
            };
            
            // Immediate synchronous scroll
            doScroll();
            
            // Wait for images to render and ensure we are pinned
            setTimeout(() => {
                doScroll();
                this._userIsAtBottom = true;
                this._toggleScrollFAB(false);
                this._isInitialScroll = false;
            }, 200);
            
            // Extra safety pass for slow-loading media
            setTimeout(doScroll, 600);
            setTimeout(() => {
                doScroll();
                restoreScrollBehavior();
            }, 1200);
        } else {
            this._isInitialScroll = false;
        }
    }

    // ── Scroll-to-Bottom FAB ───────────────────────────────────────
    _prepareHistorySoftReveal(mount) {
        if (!mount || window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) {
            return;
        }
        mount.classList.remove('wa-history-soft-ready');
        mount.classList.add('wa-history-soft-loading');
    }

    _finishHistorySoftReveal(mount) {
        if (!mount) return;
        mount.querySelectorAll('.wa-message-row:not([data-wa-motion-seen])').forEach((row) => {
            row.dataset.waMotionSeen = '1';
        });
        if (window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) {
            mount.classList.remove('wa-history-soft-loading', 'wa-history-soft-ready');
            return;
        }
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                mount.classList.remove('wa-history-soft-loading');
                mount.classList.add('wa-history-soft-ready');
                setTimeout(() => {
                    mount.classList.remove('wa-history-soft-ready');
                }, 220);
            });
        });
    }

    _injectScrollFAB() {
        if (document.getElementById('wa_scroll_fab')) return;
        const chatMain = document.querySelector('.o_whatsapp_chat_main');
        if (!chatMain) return;

        const fab = document.createElement('button');
        fab.id = 'wa_scroll_fab';
        fab.type = 'button';
        fab.className = 'wa-scroll-fab';
        fab.title = 'Jump to latest';
        fab.setAttribute('aria-label', 'Scroll to bottom');
        fab.innerHTML = '<i class="fa fa-chevron-down"></i>';
        fab.addEventListener('click', () => this._scrollToBottom(true));
        chatMain.style.position = 'relative';
        chatMain.appendChild(fab);
    }

    _toggleScrollFAB(show) {
        const fab = document.getElementById('wa_scroll_fab');
        if (!fab) return;
        if (show) {
            fab.style.display = 'flex';
            requestAnimationFrame(() => {
                fab.classList.add('visible');
            });
        } else {
            fab.classList.remove('visible');
            setTimeout(() => {
                if (!fab.classList.contains('visible')) {
                    fab.style.display = 'none';
                }
            }, 200);
        }
    }

    // ── Mobile Back Button ─────────────────────────────────────────
    _getMobileHeaderRow(container = null) {
        const root = container || document.querySelector('.o_whatsapp_chat_container');
        return root?.querySelector('.o_whatsapp_chat_main > .border-bottom .d-flex.align-items-center') ||
            root?.querySelector('.o_whatsapp_chat_main > .border-bottom') ||
            document.querySelector('.o_whatsapp_chat_main > .border-bottom .d-flex.align-items-center') ||
            document.querySelector('.o_whatsapp_chat_main > .border-bottom') ||
            document.querySelector('.o_whatsapp_panel_header_premium .d-flex');
    }

    _normalizeMobileChatsButton(button) {
        if (!button) return;
        button.id = button.id || 'wa_mobile_back_btn';
        button.type = 'button';
        button.classList.add('btn', 'btn-light', 'wa-mobile-back-btn', 'wa-mobile-chats-btn');
        button.classList.remove('btn-link', 'p-0');
        button.title = 'Chats';
        button.setAttribute('aria-label', 'Open chats');
        button.setAttribute('aria-controls', 'wa-active-sidebar-mount');
        button.innerHTML = '<i class="fa fa-comments-o me-1"></i><span class="wa-mobile-chats-label">Chats</span>';
    }

    _injectMobileBackButton() {
        if (window.innerWidth > 991) return;
        const { container } = this._getMobileLayoutParts();
        const existingBtn = container?.querySelector('.wa-mobile-back-btn') || document.querySelector('.wa-mobile-back-btn');
        if (existingBtn) {
            this._normalizeMobileChatsButton(existingBtn);
            return;
        }
        if (document.getElementById('wa_mobile_back_btn')) return;
        const headerRow = this._getMobileHeaderRow(container);
        if (!headerRow) return;

        const btn = document.createElement('button');
        btn.className = 'me-2 d-lg-none';
        this._normalizeMobileChatsButton(btn);
        btn.addEventListener('click', () => {
            this._openMobileChatList();
        });
        headerRow.prepend(btn);
    }

    _isMobileViewport() {
        return window.matchMedia('(max-width: 991px)').matches;
    }

    _handleViewportResize() {
        if (this._mobileResizeTimer) {
            clearTimeout(this._mobileResizeTimer);
        }
        this._mobileResizeTimer = setTimeout(() => {
            this._mobileResizeTimer = null;
            const isMobile = this._isMobileViewport();
            const enteredMobile = isMobile && !this._lastViewportIsMobile;
            const leftMobile = !isMobile && this._lastViewportIsMobile;
            this._lastViewportIsMobile = isMobile;

            if (enteredMobile) {
                this._refreshForMobileEntry();
                return;
            }

            this._syncMobileLayout();
            if (leftMobile) {
                this._applyRightPanePreference();
            }
        }, 120);
    }

    _getMobileLayoutParts() {
        const container = document.querySelector('.o_whatsapp_chat_container');
        return {
            container,
            sidebar: container?.querySelector('.wa-left-sidebar') || document.querySelector('.wa-left-sidebar'),
            main: container?.querySelector('.o_whatsapp_chat_main') || document.querySelector('.o_whatsapp_chat_main'),
            rightPane: container?.querySelector('.wa-right-sidebar') || document.querySelector('.wa-right-sidebar'),
            backdrop: container?.querySelector('.wa-mobile-drawer-backdrop') || document.querySelector('.wa-mobile-drawer-backdrop'),
        };
    }

    _refreshForMobileEntry() {
        const { container, sidebar } = this._getMobileLayoutParts();
        if (!container) return;

        container.removeAttribute('data-wa-mobile-panel');
        this._mobilePanel = null;
        try {
            sessionStorage.removeItem('wa_mobile_panel');
        } catch (e) { /* sessionStorage may be blocked */ }

        this._injectMobileBackButton();
        this._ensureMobileChatListControls(container, sidebar);
        this._syncMobileLayout();
        this._attachScrollListener();
        this._initSidebarEngine();
        this._enhanceComposer();

        const activeChatId = this._selectedChatId || this._getActiveChatId();
        if (activeChatId) {
            this._lastHtml = null;
            this._surgicalRefresh(activeChatId);
        }
    }

    _openMobileChatList() {
        if (!this._isMobileViewport()) return;
        const activeChatId = this._selectedChatId || this._getActiveChatId();
        this._setMobilePanel(activeChatId ? 'chat_list_drawer' : 'list');
    }

    _handleMobileKeydown(ev) {
        if (!this._isMobileViewport() || ev.key !== 'Escape') return;
        const { container } = this._getMobileLayoutParts();
        const panel = container?.getAttribute('data-wa-mobile-panel');
        if (panel === 'chat_list_drawer' || panel === 'details') {
            ev.preventDefault();
            this._setMobilePanel('chat');
        }
    }

    _ensureMobileChatListControls(container, sidebar) {
        const headerButton = container?.querySelector('.wa-mobile-back-btn') || document.querySelector('.wa-mobile-back-btn');
        if (headerButton) {
            this._normalizeMobileChatsButton(headerButton);
        }

        if (container && !container.querySelector('.wa-mobile-drawer-backdrop')) {
            const backdrop = document.createElement('button');
            backdrop.type = 'button';
            backdrop.className = 'wa-mobile-drawer-backdrop';
            backdrop.setAttribute('aria-label', 'Close chats drawer');
            backdrop.addEventListener('click', (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                this._setMobilePanel('chat');
            });
            container.insertBefore(backdrop, container.firstChild);
        }

        if (sidebar && !sidebar.querySelector('.wa-mobile-sidebar-close')) {
            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'wa-mobile-sidebar-close btn btn-light border rounded-circle';
            closeBtn.setAttribute('aria-label', 'Close chats drawer');
            closeBtn.title = 'Close chats';
            closeBtn.innerHTML = '<i class="fa fa-times"></i>';
            closeBtn.addEventListener('click', (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                this._setMobilePanel('chat');
            });
            const headerRow = sidebar.querySelector('.o_whatsapp_panel_header .d-flex.justify-content-between') ||
                sidebar.querySelector('.o_whatsapp_panel_header') ||
                sidebar;
            headerRow.append(closeBtn);
        }
    }

    _ensureMobileDetailsCloseButton(rightPane) {
        if (!rightPane || rightPane.querySelector('.wa-mobile-details-close')) return;
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'wa-mobile-details-close btn btn-light border rounded-circle';
        closeBtn.setAttribute('aria-label', 'Close contact details');
        closeBtn.title = 'Close';
        closeBtn.innerHTML = '<i class="fa fa-times"></i>';
        closeBtn.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            this._setMobilePanel('chat');
        });
        rightPane.prepend(closeBtn);
    }

    _setMobilePanel(panel = 'chat', { persist = true } = {}) {
        if (!this._isMobileViewport()) return;
        const { container, sidebar, main, rightPane, backdrop } = this._getMobileLayoutParts();
        if (!container) return;

        const allowedPanels = ['list', 'chat', 'chat_list_drawer', 'details'];
        let nextPanel = allowedPanels.includes(panel) ? panel : 'chat';
        const activeChatId = this._selectedChatId || this._getActiveChatId();
        if (!activeChatId && nextPanel !== 'list') {
            nextPanel = 'list';
        }

        this._ensureMobileChatListControls(container, sidebar);
        container.setAttribute('data-wa-mobile-panel', nextPanel);
        this._mobilePanel = nextPanel;
        if (persist) {
            try {
                sessionStorage.removeItem('wa_mobile_panel');
            } catch (e) { /* sessionStorage may be blocked */ }
        }

        if (sidebar) {
            const sidebarOpen = nextPanel === 'list' || nextPanel === 'chat_list_drawer';
            sidebar.classList.toggle('d-none', !sidebarOpen);
            sidebar.classList.toggle('d-flex', sidebarOpen);
            sidebar.classList.toggle('wa-mobile-chat-list-drawer', nextPanel === 'chat_list_drawer');
            sidebar.classList.toggle('wa-mobile-chat-list-fullscreen', nextPanel === 'list');
        }
        if (main) {
            main.classList.toggle('d-none', nextPanel === 'list');
            main.classList.toggle('d-flex', nextPanel !== 'list');
        }
        if (rightPane) {
            const detailsOpen = nextPanel === 'details';
            rightPane.classList.toggle('d-none', !detailsOpen);
            rightPane.classList.toggle('wa-mobile-details-open', detailsOpen);
            if (detailsOpen) {
                this._ensureMobileDetailsCloseButton(rightPane);
            }
        }
        if (backdrop) {
            backdrop.classList.toggle('wa-mobile-drawer-backdrop-open', nextPanel === 'chat_list_drawer');
        }
        const chatButton = container.querySelector('.wa-mobile-chats-btn');
        if (chatButton) {
            chatButton.classList.toggle('active', nextPanel === 'chat_list_drawer' || nextPanel === 'list');
            chatButton.setAttribute('aria-expanded', nextPanel === 'chat_list_drawer' ? 'true' : 'false');
        }
    }

    _syncMobileLayout() {
        const { container, sidebar, main, rightPane } = this._getMobileLayoutParts();
        if (!container) return;

        if (!this._isMobileViewport()) {
            container.removeAttribute('data-wa-mobile-panel');
            if (sidebar) {
                sidebar.classList.remove('wa-mobile-chat-list-drawer', 'wa-mobile-chat-list-fullscreen');
            }
            if (main) {
                main.classList.remove('d-none');
                main.classList.add('d-flex');
            }
            if (rightPane) {
                rightPane.classList.remove('wa-mobile-details-open');
            }
            const backdrop = container.querySelector('.wa-mobile-drawer-backdrop');
            if (backdrop) {
                backdrop.classList.remove('wa-mobile-drawer-backdrop-open');
            }
            return;
        }

        const activeChatId = this._selectedChatId || this._getActiveChatId();
        const currentPanel = container.getAttribute('data-wa-mobile-panel');
        const allowedPanels = ['list', 'chat', 'chat_list_drawer', 'details'];
        let nextPanel = allowedPanels.includes(currentPanel) ? currentPanel : 'list';
        if (!activeChatId) {
            nextPanel = 'list';
        }
        this._setMobilePanel(nextPanel, { persist: false });
        if (sidebar && nextPanel === 'list') {
            sidebar.classList.remove('d-none');
            sidebar.classList.add('d-flex');
        }
    }

    _setRightPaneOpen(isOpen) {
        if (this._isMobileViewport()) {
            const rightPane = document.querySelector('.wa-right-sidebar');
            const isDetailsOpen = rightPane?.classList.contains('wa-mobile-details-open');
            const targetPanel = typeof isOpen === 'boolean'
                ? (isOpen ? 'details' : 'chat')
                : (isDetailsOpen ? 'chat' : 'details');
            this._setMobilePanel(targetPanel);
            return;
        }
        const rightPane = document.querySelector('.wa-right-sidebar');
        if (!rightPane) return;
        if (isOpen) {
            // Show: remove all hiding classes, add visible class
            rightPane.classList.remove('d-none', 'd-lg-none');
            rightPane.classList.add('d-lg-block');
        } else {
            // Hide: remove visible class, add hide classes
            rightPane.classList.remove('d-lg-block');
            rightPane.classList.add('d-none', 'd-lg-none');
        }
        try {
            localStorage.setItem(RIGHT_PANE_STORAGE_KEY, isOpen ? '1' : '0');
        } catch (e) { /* localStorage may be blocked */ }
    }

    _applyRightPanePreference() {
        if (this._isMobileViewport()) {
            this._syncMobileLayout();
            return;
        }
        let stored = null;
        try {
            stored = localStorage.getItem(RIGHT_PANE_STORAGE_KEY);
        } catch (e) { /* localStorage may be blocked */ }
        if (stored === '0') {
            this._setRightPaneOpen(false);
        } else if (stored === '1') {
            this._setRightPaneOpen(true);
        }
    }

    _tickSlaTimers() {
        const timers = document.querySelectorAll('.wa-sla-timer');
        const now = Date.now();
        timers.forEach((timer) => {
            if (!timer.dataset.waSlaStartedAt) {
                const datasetMinutes = parseInt(timer.dataset.waSlaMinutes || '', 10);
                const match = (timer.textContent || '').match(/(\d+)\s*m\s*wait/i);
                const parsedMinutes = parseInt(match?.[1] || '', 10);
                const baseMinutes = Number.isFinite(datasetMinutes)
                    ? datasetMinutes
                    : (Number.isFinite(parsedMinutes) ? parsedMinutes : 0);
                timer.dataset.waSlaBaseMinutes = String(baseMinutes);
                timer.dataset.waSlaStartedAt = String(now);
            }
            const base = parseInt(timer.dataset.waSlaBaseMinutes || '0', 10);
            const startedAt = parseInt(timer.dataset.waSlaStartedAt || String(now), 10);
            const liveMinutes = base + Math.max(0, Math.floor((now - startedAt) / 60000));
            const valueEl = timer.querySelector('.wa-sla-value');
            if (valueEl) {
                valueEl.textContent = String(liveMinutes);
            } else {
                timer.textContent = `${liveMinutes}m wait`;
            }
        });
    }

    // ── Notification Handler ───────────────────────────────────────
    // BUG 1+4 FIX: Type-aware routing — status updates get efficient DOM patching,
    // new messages get full refresh. _lastBusActivity gates polling (BUG 3+8).
    _onNotification(type, payload) {
        // Record Bus activity timestamp (gates 8s polling fallback)
        this._lastBusActivity = Date.now();

        if (type === 'whatsapp_typing') {
            this._showTypingIndicator(payload || {});
            return;
        }

        // ── STATUS UPDATE path (efficient tick patching) ──
        if (type === 'whatsapp_status_update' && payload?.message_id && payload?.status) {
            this._patchMessageStatus(payload.chat_id, payload.message_id, payload.status);
            // Also update sidebar last-message status badge
            if (payload.chat_id) {
                this._patchSidebarStatus(payload.chat_id, payload.status);
                this._updateSidebarForChat(payload.chat_id);
            }
            return;
        }

        // ── NEW MESSAGE path ──
        if (this._isDuplicateNewMessage(payload || {})) {
            return;
        }
        
        // Play sound for inbound messages from Bus notifications (backup to Socket.IO)
        if (payload?.type === 'new_message' && payload?.chat_id) {
            this._playSound('received', payload.chat_id, payload.message_id);
        }

        // Reset cache so incoming message ALWAYS re-renders the history
        this._lastHtml = null;
        
        // If it's for the active chat, refresh it.
        const activeChatId = this._getActiveChatId();
        if (!activeChatId || activeChatId == payload?.chat_id) {
            this._surgicalRefresh();
        }

        // BUG 7 FIX: Always update the sidebar for the chat receiving the message
        // across ALL panes, and refresh counts for badge accuracy.
        if (payload?.chat_id) {
            this._updateSidebarForChat(payload.chat_id);
        } else {
            // No specific chat in payload — refresh all to be safe
            this._updateSidebarCounts();
        }
        // Always refresh pane tab badge counts so cross-pane visibility is correct
        this._updateSidebarCounts();
    }

    // BUG 4 FIX: Direct DOM tick patching for status updates (sent→delivered→read)
    // Avoids full RPC re-fetch for simple tick changes.
    _patchMessageStatus(chatId, messageId, newStatus) {
        const activeChatId = this._getActiveChatId();
        if (!chatId || Number(chatId) !== Number(activeChatId)) return;

        const row = document.querySelector(`[data-wa-message-id="${messageId}"]`);
        if (!row) {
            // Message not in DOM — fall back to full refresh
            this._lastHtml = null;
            this._surgicalRefresh();
            return;
        }

        const tickEl = row.querySelector('.wa-msg-tick');
        if (!tickEl) return;

        // Build new tick HTML based on status
        let tickHtml = '';
        if (newStatus === 'sent') {
            tickHtml = '<i class="fa fa-check text-muted wa-msg-tick" title="Sent" style="font-size: 0.7rem;"></i>';
        } else if (newStatus === 'delivered') {
            tickHtml = '<span class="wa-msg-tick d-inline-flex align-items-center" title="Delivered"><i class="fa fa-check text-muted" style="font-size: 0.7rem;"></i><i class="fa fa-check text-muted" style="font-size: 0.7rem; margin-left: -4px;"></i></span>';
        } else if (newStatus === 'read') {
            tickHtml = '<span class="wa-msg-tick d-inline-flex align-items-center" title="Read"><i class="fa fa-check text-info" style="font-size: 0.7rem;"></i><i class="fa fa-check text-info" style="font-size: 0.7rem; margin-left: -4px;"></i></span>';
        } else if (newStatus === 'failed') {
            tickHtml = '<i class="fa fa-exclamation-circle text-danger wa-msg-tick" title="Failed" style="font-size: 0.7rem;"></i>';
        }

        if (tickHtml) {
            tickEl.outerHTML = tickHtml;
        }
    }

    // BUG 4 FIX: Patch sidebar last-message status icon without full re-fetch
    _patchSidebarStatus(chatId, newStatus) {
        const sidebarItem = document.querySelector(`.o_whatsapp_sidebar_item[data-chat-id="${chatId}"]`);
        if (!sidebarItem) return;

        const bodyEl = sidebarItem.querySelector('.small.text-muted.text-truncate.d-flex');
        if (!bodyEl) return;

        // Find existing status icons and update them
        const existingIcons = bodyEl.querySelectorAll('.fa-check, .fa-exclamation-circle');
        if (existingIcons.length === 0) return; // No outbound status to update

        let statusIcon = '';
        if (newStatus === 'sent') {
            statusIcon = '<i class="fa fa-check text-muted" title="Sent" style="font-size: 0.7rem;"></i>';
        } else if (newStatus === 'delivered') {
            statusIcon = '<span class="d-flex align-items-center" style="margin-left: -2px;"><i class="fa fa-check text-muted" title="Delivered" style="font-size: 0.7rem;"></i><i class="fa fa-check text-muted" title="Delivered" style="font-size: 0.7rem; margin-left: -4px;"></i></span>';
        } else if (newStatus === 'read') {
            statusIcon = '<span class="d-flex align-items-center" style="margin-left: -2px;"><i class="fa fa-check text-info" title="Read" style="font-size: 0.7rem;"></i><i class="fa fa-check text-info" title="Read" style="font-size: 0.7rem; margin-left: -4px;"></i></span>';
        }

        // Replace the first icon group (status indicators come before the text)
        const textContent = bodyEl.textContent?.trim() || '';
        // Remove all existing check icons, keep the text
        existingIcons.forEach(icon => {
            const parent = icon.closest('span.d-flex');
            if (parent) parent.remove();
            else icon.remove();
        });
        // Re-insert the new status icon at the beginning
        if (statusIcon) {
            bodyEl.insertAdjacentHTML('afterbegin', statusIcon);
        }
    }

    async _updateSidebarForChat(chatId) {
        if (!chatId) return;
        try {
            const fieldsToRead = [
                'display_name', 'phone_number', 'display_name_initial',
                'account_id', 'assigned_user_id',
                'last_message_body', 'last_message_date_str', 'last_message_status',
                'last_message_direction', 'unread_count', 'is_pinned',
                'is_archived', 'sla_status', 'sla_timer_minutes',
                'state', 'needs_reply'
            ];
            const res = await this._rpc('whatsapp.chat', 'read', [[parseInt(chatId)], fieldsToRead]);
            if (!res || !res[0]) return;

            const rawChat = res[0];
            const chat = {
                id: rawChat.id,
                display_name: rawChat.display_name || rawChat.phone_number,
                phone_number: rawChat.phone_number,
                display_name_initial: rawChat.display_name_initial,
                account_id: rawChat.account_id ? rawChat.account_id[0] : false,
                account_name: rawChat.account_id ? rawChat.account_id[1] : '',
                assigned_user_id: rawChat.assigned_user_id ? rawChat.assigned_user_id[0] : false,
                assigned_user_name: rawChat.assigned_user_id ? rawChat.assigned_user_id[1] : '',
                last_message_body: rawChat.last_message_body || 'No messages yet',
                last_message_date_str: rawChat.last_message_date_str || '',
                last_message_status: rawChat.last_message_status,
                last_message_direction: rawChat.last_message_direction,
                unread_count: rawChat.unread_count,
                is_pinned: rawChat.is_pinned,
                is_archived: rawChat.is_archived,
                sla_status: rawChat.sla_status,
                sla_timer_minutes: rawChat.sla_timer_minutes,
                state: rawChat.state,
                needs_reply: rawChat.needs_reply,
            };

            Object.entries(this._paneIds).forEach(([paneKey, mountId]) => {
                const mount = document.getElementById(mountId);
                if (!mount) return;

                const shouldBeInPane = this._matchesFilterAndPane(chat, this._sidebarFilter, paneKey);
                const sidebarItem = mount.querySelector(`.o_whatsapp_sidebar_item[data-chat-id="${chat.id}"]`);

                if (shouldBeInPane) {
                    if (sidebarItem) {
                        // Surgical update to avoid layout flicker
                        const bodyEl = sidebarItem.querySelector('.small.text-muted.text-truncate.d-flex');
                        if (bodyEl) {
                            let statusIcon = '';
                            if (chat.last_message_direction === 'outbound') {
                                if (chat.last_message_status === 'sent') statusIcon = `<i class="fa fa-check text-muted" title="Sent" style="font-size: 0.7rem;"></i>`;
                                else if (chat.last_message_status === 'delivered') statusIcon = `<span class="d-flex align-items-center" style="margin-left: -2px;"><i class="fa fa-check text-muted" title="Delivered" style="font-size: 0.7rem;"></i><i class="fa fa-check text-muted" title="Delivered" style="font-size: 0.7rem; margin-left: -4px;"></i></span>`;
                                else if (chat.last_message_status === 'read') statusIcon = `<span class="d-flex align-items-center" style="margin-left: -2px;"><i class="fa fa-check text-info" title="Read" style="font-size: 0.7rem;"></i><i class="fa fa-check text-info" title="Read" style="font-size: 0.7rem; margin-left: -4px;"></i></span>`;
                            }
                            const safeBody = (chat.last_message_body || 'No messages yet').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            bodyEl.innerHTML = `${statusIcon}${safeBody}`;
                        }

                        const dateEl = sidebarItem.querySelector('.d-flex.flex-column.align-items-end .small.text-muted');
                        if (dateEl) dateEl.innerText = chat.last_message_date_str || '';

                        // Update unread count
                        let badge = sidebarItem.querySelector('.o_whatsapp_unread_count');
                        if (chat.unread_count > 0 && this._getActiveChatId() !== chat.id) {
                            if (!badge) {
                                badge = document.createElement('div');
                                badge.className = 'badge rounded-pill bg-success shadow-sm o_whatsapp_unread_count';
                                badge.style.cssText = 'padding: 4px 8px; font-size: 0.7rem;';
                                const badgeContainer = sidebarItem.querySelector('.d-flex.align-items-center.gap-1');
                                if (badgeContainer) badgeContainer.appendChild(badge);
                            }
                            badge.innerText = chat.unread_count;
                        } else if (badge) {
                            badge.remove();
                        }

                        // Update badges container
                        const badgesContainer = sidebarItem.querySelector('.mt-1.flex-wrap');
                        if (badgesContainer) {
                            const accountBadge = chat.account_name ? `<span class="badge text-white" style="background: rgba(0, 168, 132, 0.7); font-size: 0.65rem; border-radius: 4px; padding: 2px 6px;">${chat.account_name}</span>` : '';
                            const agentBadge = chat.assigned_user_name ? `<span class="badge text-dark" style="background: rgba(0, 0, 0, 0.05); font-size: 0.65rem; border-radius: 4px; padding: 2px 6px;"><i class="fa fa-user-o me-1"></i>${chat.assigned_user_name}</span>` : `<span class="badge text-muted" style="background: rgba(0, 0, 0, 0.03); font-size: 0.65rem; border-radius: 4px; padding: 2px 6px; border: 1px dashed rgba(0,0,0,0.1);"><i class="fa fa-user-times me-1"></i>Unassigned</span>`;
                            badgesContainer.innerHTML = `${accountBadge}${agentBadge}`;
                        }

                        // Promote to top
                        const btnContainer = sidebarItem.closest('button.o_whatsapp_sidebar_btn');
                        if (btnContainer && mount.firstChild !== btnContainer) {
                            mount.prepend(btnContainer);
                        }
                    } else {
                        // Create and prepend new card
                        const cardHtml = this._renderChatCardHtml(chat);
                        mount.insertAdjacentHTML('afterbegin', cardHtml);
                    }
                } else {
                    // Remove from pane if it no longer belongs
                    if (sidebarItem) {
                        const btnContainer = sidebarItem.closest('button.o_whatsapp_sidebar_btn');
                        if (btnContainer) btnContainer.remove();
                    }
                }
            });

            this._updateSidebarCounts();
        } catch (e) {
            console.warn('[WhatsApp] Sidebar update failed:', e);
        }
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
        // Manual media retry for inbound Meta media that has not been stored yet.
        const retryMediaBtn = e.target.closest('[data-wa-retry-media-id]');
        if (retryMediaBtn) {
            e.preventDefault();
            e.stopPropagation();
            const messageId = parseInt(retryMediaBtn.getAttribute('data-wa-retry-media-id'), 10);
            if (messageId) {
                this._setButtonBusy(retryMediaBtn, true, 'Downloading...');
                this._rpc('whatsapp.message', 'action_retry_media_download', [[messageId]])
                    .then((action) => {
                        if (action) {
                            this.actionService.doAction(action);
                        }
                        this._lastHtml = null;
                        this._surgicalRefresh();
                    })
                    .catch((error) => {
                        console.warn('[WhatsApp] Media retry failed:', error);
                    })
                    .finally(() => this._setButtonBusy(retryMediaBtn, false));
            }
            return;
        }
        // Media Lightbox
        const lightbox = e.target.closest('.wa-lightbox-trigger');
        if (lightbox) {
            e.preventDefault(); e.stopPropagation();
            this._openLightbox(lightbox.getAttribute('href') || lightbox.getAttribute('src'));
            return;
        }
        // Right Pane Toggle
        const rightPaneToggleBtn = e.target.closest('.wa-toggle-right-pane-btn');
        if (rightPaneToggleBtn) {
            e.preventDefault(); e.stopPropagation();
            if (this._isMobileViewport()) {
                const rightPane = document.querySelector('.wa-right-sidebar');
                const isDetailsOpen = rightPane?.classList.contains('wa-mobile-details-open');
                this._setMobilePanel(isDetailsOpen ? 'chat' : 'details');
                return;
            }
            const rightPane = document.querySelector('.wa-right-sidebar');
            if (rightPane) {
                this._setRightPaneOpen(!rightPane.classList.contains('d-lg-block'));
            }
            return;
        }
        // Sidebar chat switch — also handle mobile view toggle
        const sidebarItem = e.target.closest('.o_whatsapp_sidebar_item');
        if (sidebarItem) {
            const chatId = parseInt(sidebarItem.getAttribute('data-chat-id'));
            if (chatId) {
                e.preventDefault(); e.stopPropagation();
                this._switchChatContext(chatId, sidebarItem);
                // Mobile: hide sidebar, show chat
                if (window.innerWidth <= 991) {
                    this._setMobilePanel('chat');
                }
            }
            return;
        }
        // Mobile Back Button
        const mobileBackBtn = e.target.closest('.wa-mobile-back-btn');
        if (mobileBackBtn) {
            e.preventDefault(); e.stopPropagation();
            this._openMobileChatList();
            return;
        }
        
        // Send Template Wizard Intercept
        const templateBtn = e.target.closest('button[name="action_open_send_wizard"]');
        if (templateBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getChatIdForUserAction(templateBtn);
            if (chatId) {
                this._selectedChatId = chatId;
                this._lastChatId = chatId;
                sessionStorage.setItem('wa_selected_chat_id', chatId);
                this._rpc('whatsapp.chat', 'action_open_send_wizard', [[chatId]]).then((action) => {
                    this.actionService.doAction(this._normalizeActionViews(action, [[false, 'form']]), {
                        onClose: () => {
                            // BUG FIX: Template replies not showing after wizard closes.
                            // Always bust the HTML cache and force a full re-fetch.
                            // Then retry after 2s in case server-side template processing
                            // (media upload, Meta API call) hasn't committed yet.
                            this._lastHtml = null;
                            this._surgicalRefresh(chatId);
                            this._refreshAllPanes();
                            setTimeout(() => {
                                this._lastHtml = null;
                                this._surgicalRefresh(chatId);
                                this._refreshAllPanes();
                            }, 2000);
                        }
                    });
                }).catch((err) => {
                    console.error('[WhatsApp] Failed to open send wizard:', err);
                });
            }
            return;
        }

        // View Partner Intercept
        const partnerBtn = e.target.closest('button[name="action_view_partner"]');
        if (partnerBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getChatIdForUserAction(partnerBtn);
            if (chatId) {
                this._rpc('whatsapp.chat', 'read', [[chatId], ['partner_id']]).then((res) => {
                    if (res && res[0] && res[0].partner_id) {
                        const pid = Array.isArray(res[0].partner_id) ? res[0].partner_id[0] : res[0].partner_id;
                        this.actionService.doAction(this._normalizeActionViews({
                            type: 'ir.actions.act_window',
                            res_model: 'res.partner',
                            res_id: pid,
                            view_mode: 'form',
                            views: [[false, 'form']],
                            target: 'current'
                        }));
                    }
                });
            }
            return;
        }

        // Resolve Intercept
        const resolveBtn = e.target.closest('button[name="action_resolve"]');
        if (resolveBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getChatIdForUserAction(resolveBtn);
            if (chatId) {
                this._rpc('whatsapp.chat', 'action_resolve', [[chatId]]).then(() => {
                    // BUG FIX: Clear state FIRST, then refresh sidebar, then navigate away.
                    // The old order caused the resolved chat to briefly flash as active.
                    this._lastChatId = null;
                    this._selectedChatId = null;
                    this._lastHtml = null;
                    sessionStorage.removeItem('wa_selected_chat_id');

                    // On mobile: show sidebar, hide chat area
                    if (window.innerWidth <= 991) {
                        const sidebar = document.querySelector('.wa-left-sidebar');
                        const main = document.querySelector('.o_whatsapp_chat_main');
                        if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
                        if (main) main.classList.add('d-none');
                    }

                    // Navigate away first, then refresh panes after navigation settles
                    this._hardRefresh();
                    setTimeout(() => this._refreshAllPanes(), 500);
                });
            }
            return;
        }

        // Snooze Intercept
        const snoozeBtn = e.target.closest('button[name="action_snooze"]');
        if (snoozeBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getChatIdForUserAction(snoozeBtn);
            if (chatId) {
                this._rpc('whatsapp.chat', 'action_snooze', [[chatId]]).then(() => {
                    // BUG FIX: Same fix as resolve — clear state cleanly
                    this._lastChatId = null;
                    this._selectedChatId = null;
                    this._lastHtml = null;
                    sessionStorage.removeItem('wa_selected_chat_id');

                    if (window.innerWidth <= 991) {
                        const sidebar = document.querySelector('.wa-left-sidebar');
                        const main = document.querySelector('.o_whatsapp_chat_main');
                        if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
                        if (main) main.classList.add('d-none');
                    }

                    this._hardRefresh();
                    setTimeout(() => this._refreshAllPanes(), 500);
                });
            }
            return;
        }

        // Reopen Intercept
        const reopenBtn = e.target.closest('button[name="action_reopen"]');
        if (reopenBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getChatIdForUserAction(reopenBtn);
            if (chatId) {
                this._rpc('whatsapp.chat', 'action_reopen', [[chatId]]).then(() => {
                    // BUG FIX: Clear cached HTML so the header badges (state) refresh
                    this._lastHtml = null;
                    this._refreshAllPanes();
                    this._surgicalRefresh(chatId);
                });
            }
            return;
        }


        // AI draft generation: keep this in-place. Letting the native Odoo object
        // button reload the form can wipe the custom chat-history mount.
        const generateAiBtn = e.target.closest('button[name="action_generate_ai_reply"]');
        if (generateAiBtn) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
            const chatId = this._getChatIdForUserAction(generateAiBtn);
            if (chatId) {
                this._generateAiReplyInPlace(chatId, generateAiBtn);
            }
            return;
        }

        const clearAiBtn = e.target.closest('button[name="action_clear_ai_guidance"]');
        if (clearAiBtn) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
            const chatId = this._getChatIdForUserAction(clearAiBtn);
            if (chatId) {
                this._clearAiGuidanceInPlace(chatId, clearAiBtn);
            }
            return;
        }

        // AI draft: place text in composer without reloading/replacing the chat form.
        const useAiDraftBtn = e.target.closest('button[name="action_use_ai_suggested_reply"]');
        if (useAiDraftBtn) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
            const chatId = this._getChatIdForUserAction(useAiDraftBtn);
            const formRoot = useAiDraftBtn.closest('.o_form_view') || document;
            const input = this._getComposerTextarea(formRoot);
            if (chatId && input) {
                this._setButtonBusy(useAiDraftBtn, true, 'Placing...');
                this._rpc('whatsapp.chat', 'action_use_ai_suggested_reply', [[chatId]])
                    .then(() => this._rpc('whatsapp.chat', 'read', [[chatId], ['quick_reply_text']]))
                    .then((res) => {
                        const draft = res?.[0]?.quick_reply_text || '';
                        this._applyTextToComposer(input, draft);
                    })
                    .catch((error) => {
                        console.warn('[WhatsApp] AI draft placement failed:', error);
                        this._showTransientComposerWarning(formRoot, this._friendlyError(error, 'AI draft could not be placed in the composer.'), useAiDraftBtn);
                    })
                    .finally(() => this._setButtonBusy(useAiDraftBtn, false));
            }
            return;
        }

        // AI suggested flow: run it in-place and refresh the message history only.
        const startAiFlowBtn = e.target.closest('button[name="action_start_ai_suggested_flow"]');
        if (startAiFlowBtn) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
            const chatId = this._getChatIdForUserAction(startAiFlowBtn);
            if (chatId) {
                this._rpc('whatsapp.chat', 'action_start_ai_suggested_flow', [[chatId]])
                    .then((action) => {
                        if (action?.type) {
                            this.actionService.doAction(action);
                        }
                        this._lastHtml = null;
                        this._surgicalRefresh(chatId);
                        this._refreshAllPanes();
                    })
                    .catch((error) => console.warn('[WhatsApp] Starting AI suggested flow failed:', error));
            }
            return;
        }

        const manageAiFlowsBtn = e.target.closest('button[name="action_open_ai_flow_manager"]');
        if (manageAiFlowsBtn) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
            const chatId = this._getChatIdForUserAction(manageAiFlowsBtn);
            if (chatId) {
                this._setButtonBusy(manageAiFlowsBtn, true, 'Opening...');
                this._rpc('whatsapp.chat', 'action_open_ai_flow_manager', [[chatId]])
                    .then((action) => {
                        if (action?.type) {
                            this.actionService.doAction(action);
                        }
                    })
                    .catch((error) => {
                        console.warn('[WhatsApp] Opening AI flow manager failed:', error);
                        this._showTransientComposerWarning(
                            manageAiFlowsBtn.closest('.o_form_view') || document,
                            this._friendlyError(error, 'Flow manager could not be opened.'),
                            manageAiFlowsBtn
                        );
                    })
                    .finally(() => this._setButtonBusy(manageAiFlowsBtn, false));
            }
            return;
        }

        // Send message
        const sendBtn = e.target.closest('button[name="action_send_quick_reply"]');
        if (sendBtn) {
            const formRoot = sendBtn.closest('.o_form_view') || document;
            const mediaPreview = formRoot.querySelector('.wa-floating-attachment-preview');
            if (mediaPreview && !mediaPreview.parentElement.hasAttribute('invisible') && mediaPreview.offsetParent !== null) {
                return; // Let Odoo native form handle file upload
            }
            
            const input = this._getComposerTextarea(formRoot);
            if (input && input.value.trim()) {
                e.preventDefault(); e.stopPropagation();
                const chatId = this._getChatIdForUserAction(sendBtn);
                if (chatId) {
                    this._sendRPC('action_send_quick_reply', input.value.trim(), chatId, input).then(() => {
                        input.value = '';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        // Immediate optimistic rendering is handled by _sendRPC cache clear
                        setTimeout(() => this._refreshAllPanes(), 1000);
                    });
                }
            }
            return;
        }
        // Internal note
        const noteBtn = e.target.closest('button[name="action_send_internal_note"]');
        if (noteBtn) {
            const input = this._getComposerTextarea(noteBtn.closest('.o_form_view') || document);
            if (input && input.value.trim()) {
                e.preventDefault(); e.stopPropagation();
                const chatId = this._getChatIdForUserAction(noteBtn);
                this._sendRPC('action_send_internal_note', input.value, chatId, input);
            }
            return;
        }
        // Emoji picker toggle
        const emojiBtn = e.target.closest('#wa_emoji_trigger');
        if (emojiBtn) {
            e.preventDefault(); e.stopPropagation();
            this._toggleEmojiPicker(emojiBtn);
            this._hideQuickReplyPopover();
            return;
        }

        const quickReplyItem = e.target.closest('.wa-quick-reply-item');
        if (quickReplyItem) {
            e.preventDefault(); e.stopPropagation();
            const textarea = this._getComposerTextarea(quickReplyItem.closest('.o_form_view') || document);
            const idx = parseInt(quickReplyItem.dataset.index || '0', 10);
            this._insertQuickReply(this._quickReplyItems[idx], textarea);
            return;
        }

        const quickReplyBtn = e.target.closest('#wa_quick_reply_trigger');
        if (quickReplyBtn) {
            e.preventDefault(); e.stopPropagation();
            const textarea = this._getComposerTextarea(quickReplyBtn.closest('.o_form_view') || document);
            if (this._isQuickReplyOpen()) {
                this._hideQuickReplyPopover();
            } else {
                this._fetchQuickReplySuggestions('', textarea);
            }
            return;
        }

        if (
            this._isQuickReplyOpen()
            && !e.target.closest('.wa-quick-reply-popover')
            && !e.target.closest('#wa_quick_reply_trigger')
            && !e.target.closest('.wa-premium-input')
        ) {
            this._hideQuickReplyPopover();
        }
    }

    // ── Twilio-Style Atomic Chat Context Switch ──────────────────────
    _setButtonBusy(button, busy, label = null) {
        if (!button) return;
        if (busy) {
            button.dataset.waOriginalHtml = button.innerHTML;
            button.disabled = true;
            button.classList.add('disabled');
            button.innerHTML = `<i class="fa fa-spinner fa-spin me-1"></i>${label || 'Working...'}`;
        } else {
            button.disabled = false;
            button.classList.remove('disabled');
            if (button.dataset.waOriginalHtml) {
                button.innerHTML = button.dataset.waOriginalHtml;
                delete button.dataset.waOriginalHtml;
            }
        }
    }

    _friendlyError(error, fallback = 'Something went wrong. Please try again.') {
        const raw = error?.data?.message || error?.message || error?.toString?.() || '';
        const message = String(raw).replace(/^UserError:\s*/i, '').trim();
        return message || fallback;
    }

    _applyTextToComposer(input, value) {
        if (!input) return;
        input.value = value || '';
        input.focus();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        this._resizeComposer(input);
        this._updateComposerCounter(input);
    }

    async _generateAiReplyInPlace(chatId, triggerEl = null) {
        const formRoot = triggerEl?.closest?.('.o_form_view') || document;
        const mount = this._getHistoryMount();
        const preservedHistory = mount?.innerHTML || '';
        this._selectedChatId = chatId;
        this._lastChatId = chatId;
        sessionStorage.setItem('wa_selected_chat_id', chatId);
        this._setCleanChatUrl(chatId);
        this._setButtonBusy(triggerEl, true, 'Drafting...');
        try {
            const action = await this._rpc('whatsapp.chat', 'action_generate_ai_reply', [[chatId]]);
            if (action?.tag === 'display_notification') {
                await this.actionService.doAction(action);
                return;
            }
            const rows = await this._rpc('whatsapp.chat', 'read', [[chatId], [
                'ai_guidance_html',
                'ai_suggested_reply',
                'quick_reply_text',
                'ai_suggested_flow_id',
            ]]);
            this._renderAiGuidanceInPlace(rows?.[0] || {}, formRoot);
            if (mount && !mount.querySelector('[data-wa-message-id]') && preservedHistory) {
                mount.innerHTML = preservedHistory;
            }
            this._lastHtml = null;
            this._refreshAllPanes();
        } catch (error) {
            console.warn('[WhatsApp] AI draft generation failed:', error);
            this._showTransientComposerWarning(formRoot, 'AI draft could not be generated. Check AI provider settings and try again.', triggerEl);
        } finally {
            this._setButtonBusy(triggerEl, false);
        }
    }

    async _clearAiGuidanceInPlace(chatId, triggerEl = null) {
        const formRoot = triggerEl?.closest?.('.o_form_view') || document;
        this._setButtonBusy(triggerEl, true, 'Clearing...');
        try {
            await this._rpc('whatsapp.chat', 'action_clear_ai_guidance', [[chatId]]);
            const panel = formRoot.querySelector('.wa-ai-guidance');
            if (panel) {
                panel.classList.add('d-none');
                panel.style.display = 'none';
                const content = panel.querySelector('.wa-ai-guidance-runtime');
                if (content) {
                    content.innerHTML = '';
                }
            }
        } catch (error) {
            console.warn('[WhatsApp] Clearing AI guidance failed:', error);
        } finally {
            this._setButtonBusy(triggerEl, false);
        }
    }

    _renderAiGuidanceInPlace(data, formRoot = document) {
        let panel = formRoot.querySelector('.wa-ai-guidance');
        const composerSurface = formRoot.querySelector('.wa-composer-surface');
        if (!panel && composerSurface) {
            panel = document.createElement('div');
            panel.className = 'wa-ai-guidance';
            panel.setAttribute('role', 'status');
            composerSurface.appendChild(panel);
        }
        if (!panel) return;

        panel.classList.remove('d-none', 'o_invisible_modifier');
        panel.removeAttribute('invisible');
        panel.style.display = '';

        let actions = panel.querySelector('.wa-ai-actions');
        if (!actions) {
            actions = document.createElement('div');
            actions.className = 'wa-ai-actions';
            actions.innerHTML = `
                <button name="action_use_ai_suggested_reply" type="button" class="btn btn-sm btn-success">
                    <i class="fa fa-check me-1" title="Use Draft"></i> Use Draft
                </button>
                <button name="action_generate_ai_reply" type="button" class="btn btn-sm btn-outline-secondary">
                    <i class="fa fa-refresh me-1" title="Regenerate"></i> Regenerate
                </button>
                <button name="action_start_ai_suggested_flow" type="button" class="btn btn-sm btn-outline-primary">
                    <i class="fa fa-code-fork me-1" title="Start Suggested Flow"></i> Start Flow
                </button>
                <button name="action_open_ai_flow_manager" type="button" class="btn btn-sm btn-outline-primary">
                    <i class="fa fa-sitemap me-1" title="Manage Flows"></i> Manage Flows
                </button>
                <button name="action_clear_ai_guidance" type="button" class="btn btn-sm btn-link text-muted">Clear</button>
            `;
            panel.appendChild(actions);
        }

        let content = panel.querySelector('.wa-ai-guidance-runtime');
        if (!content) {
            content = document.createElement('div');
            content.className = 'wa-ai-guidance-runtime';
            panel.insertBefore(content, actions);
        }
        content.innerHTML = data.ai_guidance_html || `
            <div class="wa-ai-guidance-content">
                <div class="wa-ai-guidance-title"><i class="fa fa-lightbulb-o"></i><strong>AI draft guidance</strong></div>
                <div class="wa-ai-rows"><div class="wa-ai-row"><span>Draft ready</span><p>${this._escapeHtml(data.ai_suggested_reply || '')}</p></div></div>
            </div>
        `;

        const useBtn = actions.querySelector('button[name="action_use_ai_suggested_reply"]');
        if (useBtn) {
            useBtn.classList.toggle('d-none', !data.ai_suggested_reply);
        }
        const flowBtn = actions.querySelector('button[name="action_start_ai_suggested_flow"]');
        if (flowBtn) {
            flowBtn.classList.toggle('d-none', !data.ai_suggested_flow_id);
        }
    }

    async _loadAiGuidanceForActiveChat(formRoot = document) {
        const chatId = this._getActiveChatId();
        if (!chatId || this._aiGuidanceLoadedForChatId === chatId) return;
        this._aiGuidanceLoadedForChatId = chatId;
        try {
            const rows = await this._rpc('whatsapp.chat', 'read', [[chatId], [
                'ai_guidance_html',
                'ai_suggested_reply',
                'ai_intent',
                'ai_sentiment',
                'ai_urgency',
                'ai_next_action',
                'ai_suggested_tags',
                'ai_suggested_flow_id',
            ]]);
            const data = rows?.[0] || {};
            const hasGuidance = !!(
                data.ai_guidance_html ||
                data.ai_suggested_reply ||
                data.ai_intent ||
                data.ai_sentiment ||
                data.ai_urgency ||
                data.ai_next_action ||
                data.ai_suggested_tags ||
                data.ai_suggested_flow_id
            );
            const panel = formRoot.querySelector('.wa-ai-guidance');
            if (!hasGuidance) {
                if (panel) {
                    panel.classList.add('d-none');
                    const content = panel.querySelector('.wa-ai-guidance-runtime');
                    if (content) content.innerHTML = '';
                }
                return;
            }
            this._renderAiGuidanceInPlace(data, formRoot);
        } catch (error) {
            this._aiGuidanceLoadedForChatId = null;
            console.warn('[WhatsApp] AI guidance load failed:', error);
        }
    }

    _showTransientComposerWarning(formRoot, message, anchorEl = null) {
        const shortcutCard = anchorEl?.closest?.('.wa-action-shortcuts-card');
        const composerSurface = formRoot.querySelector('.wa-composer-surface') || formRoot;
        const target = shortcutCard || formRoot.querySelector('.wa-composer-input-wrap') || composerSurface;
        const existing = target.querySelector('.wa-transient-warning');
        if (existing) existing.remove();
        const warning = document.createElement('div');
        warning.className = 'alert alert-warning py-2 px-3 my-2 small wa-transient-warning';
        warning.textContent = message;
        target.appendChild(warning);
        setTimeout(() => warning.remove(), 5000);
    }

    _escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    _getDisplayedHistoryChatId(mount = null) {
        const historyMount = mount || document.getElementById('wa-custom-history-mount');
        const id = parseInt(historyMount?.dataset?.waChatId || '', 10);
        return id || null;
    }

    async _switchChatContext(chatId, sidebarEl) {
        if (!chatId) return;
        const switchToken = ++this._activeChatSwitchToken;

        // BUG FIX: Only skip if the chat is already fully loaded and displayed.
        // The old guard `chatId === this._lastChatId` prevented re-opening a chat
        // that appeared selected but whose form view hadn't actually rendered.
        const mount = document.getElementById('wa-custom-history-mount');
        const displayedChatId = this._getDisplayedHistoryChatId(mount);
        if (Number(chatId) === Number(this._lastChatId) && Number(displayedChatId) === Number(chatId) && mount && mount.querySelector('[data-wa-message-id]')) {
            // Chat is already displayed with messages — just ensure sidebar highlight
            document.querySelectorAll('.o_whatsapp_sidebar_item').forEach(el => {
                const elId = parseInt(el.getAttribute('data-chat-id'));
                el.classList.toggle('active', el === sidebarEl || Number(elId) === Number(chatId));
            });
            if (this._isMobileViewport()) {
                this._setMobilePanel('chat');
            }
            return;
        }

        // 1. Update state instantly
        this._lastChatId = chatId;
        this._selectedChatId = chatId;
        sessionStorage.setItem('wa_selected_chat_id', chatId);
        this._lastHtml = null;
        this._historyLimit = 50;
        this._userIsAtBottom = true;
        this._isPaging = false;
        this._aiGuidanceLoadedForChatId = null;
        this._setCleanChatUrl(chatId);

        // 2. Mark active sidebar item immediately (zero-latency visual)
        document.querySelectorAll('.o_whatsapp_sidebar_item').forEach(el => {
            const elId = parseInt(el.getAttribute('data-chat-id'));
            el.classList.toggle('active', el === sidebarEl || Number(elId) === Number(chatId));
        });

        // 3. Mark as read immediately to clear badge
        this._rpc('whatsapp.chat', 'action_mark_read', [[chatId]]).catch(() => {});
        const unreadBadge = sidebarEl?.querySelector('.o_whatsapp_unread_count');
        if (unreadBadge) unreadBadge.remove();

        // 4. Show loading skeleton in the history canvas instantly
        if (mount) {
            mount.classList.add('wa-history-switching');
            mount.dataset.waChatId = '';
            mount.dataset.waLoadingChatId = String(chatId);
            mount.innerHTML = `
                <div class="d-flex flex-column gap-3 p-4 wa-loading-skeleton">
                    <div class="d-flex justify-content-start"><div class="wa-skeleton-item rounded-3" style="width:55%;height:48px;"></div></div>
                    <div class="d-flex justify-content-end"><div class="wa-skeleton-item rounded-3" style="width:40%;height:36px;"></div></div>
                    <div class="d-flex justify-content-start"><div class="wa-skeleton-item rounded-3" style="width:65%;height:56px;"></div></div>
                    <div class="d-flex justify-content-end"><div class="wa-skeleton-item rounded-3" style="width:35%;height:36px;"></div></div>
                    <div class="d-flex justify-content-start"><div class="wa-skeleton-item rounded-3" style="width:50%;height:44px;"></div></div>
                </div>
            `;
        }

        // 5. Switch Odoo active form view record natively
        try {
            await this.actionService.doAction(this._normalizeActionViews({
                type: 'ir.actions.act_window',
                res_model: 'whatsapp.chat',
                res_id: chatId,
                views: [[false, 'form']],
                target: 'current',
                context: {
                    wa_selected_chat_id: chatId,
                    wa_history_limit: this._historyLimit,
                    wa_ts: Date.now(),
                },
            }), {
                stackPosition: 'replaceCurrentAction',
            });
            if (switchToken !== this._activeChatSwitchToken) return;
            this._setCleanChatUrl(chatId);
            if (this._isMobileViewport()) {
                this._setMobilePanel('chat');
            }
            const nextMount = await this._waitForHistoryMount(24, 80);
            if (nextMount) {
                nextMount.classList.add('wa-history-switching');
                nextMount.dataset.waChatId = '';
                nextMount.dataset.waLoadingChatId = String(chatId);
            }
            this._lastHtml = null;
            await this._surgicalRefresh(chatId);
            setTimeout(() => {
                if (switchToken === this._activeChatSwitchToken && Number(this._selectedChatId) === Number(chatId)) {
                    this._setCleanChatUrl(chatId);
                    this._lastHtml = null;
                    this._surgicalRefresh(chatId);
                }
            }, 350);
        } catch (err) {
            console.error('[WhatsApp] _switchChatContext actionService.doAction error:', err);
            if (this._isMobileViewport()) {
                this._setMobilePanel('chat');
            }
            this._lastHtml = null;
            this._surgicalRefresh(chatId);
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
    _dedupeRenderedMessages(mount) {
        const seen = new Set();
        mount.querySelectorAll('[data-wa-message-id]').forEach((row) => {
            const messageId = row.dataset.waMessageId;
            if (!messageId) return;
            if (seen.has(messageId)) {
                row.remove();
            } else {
                seen.add(messageId);
            }
        });
    }

    _mergeHistoryHtml(mount, nextHtml) {
        this._dedupeRenderedMessages(mount);
        const template = document.createElement('template');
        template.innerHTML = nextHtml || '';

        const currentRows = Array.from(mount.querySelectorAll('[data-wa-message-id]'));
        const incomingRows = Array.from(template.content.querySelectorAll('[data-wa-message-id]'));
        const currentIds = new Set(currentRows.map((row) => row.dataset.waMessageId));
        const incomingIds = new Set(incomingRows.map((row) => row.dataset.waMessageId));
        const missingIds = new Set(
            incomingRows
                .map((row) => row.dataset.waMessageId)
                .filter((messageId) => messageId && !currentIds.has(messageId))
        );

        const currentSequence = currentRows
            .map((row) => row.dataset.waMessageId)
            .filter((messageId) => incomingIds.has(messageId))
            .join('|');
        const incomingSequence = incomingRows
            .map((row) => row.dataset.waMessageId)
            .filter((messageId) => currentIds.has(messageId))
            .join('|');
        const lastExistingIndex = incomingRows.reduce((lastIndex, row, index) => {
            return currentIds.has(row.dataset.waMessageId) ? index : lastIndex;
        }, -1);
        const missingBeforeExistingTail = incomingRows.some((row, index) => {
            return missingIds.has(row.dataset.waMessageId) && index < lastExistingIndex;
        });
        if (currentSequence !== incomingSequence || missingBeforeExistingTail) {
            mount.innerHTML = nextHtml || '';
            return true;
        }

        this._patchExistingMessages(mount, template.content);
        if (!missingIds.size) return false;

        mount.querySelectorAll('.wa-optimistic-bubble').forEach((row) => row.remove());

        const htmlToAppend = [];
        let pendingDateSeparator = '';
        Array.from(template.content.childNodes).forEach((node) => {
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            if (node.matches('.wa-date-separator')) {
                pendingDateSeparator = node.outerHTML;
                return;
            }
            if (!node.matches('[data-wa-message-id]')) return;
            const messageId = node.dataset.waMessageId;
            if (!missingIds.has(messageId)) return;
            const dateKey = node.dataset.waMessageDate;
            if (pendingDateSeparator && dateKey && !mount.querySelector(`[data-wa-date-label="${dateKey}"]`)) {
                htmlToAppend.push(pendingDateSeparator);
            }
            pendingDateSeparator = '';
            htmlToAppend.push(node.outerHTML);
        });

        if (htmlToAppend.length) {
            mount.insertAdjacentHTML('beforeend', htmlToAppend.join(''));
            return true;
        }
        return false;
    }

    _patchExistingMessages(mount, incomingFragment) {
        incomingFragment.querySelectorAll('[data-wa-message-id]').forEach((incomingRow) => {
            const messageId = incomingRow.dataset.waMessageId;
            const currentRow = mount.querySelector(`[data-wa-message-id="${messageId}"]`);
            if (!currentRow) return;
            
            // Only patch the class list (for status colors/notes)
            if (currentRow.className !== incomingRow.className) {
                currentRow.className = incomingRow.className;
            }

            // Only surgically replace the tick icon, instead of the whole bubble
            const currentTick = currentRow.querySelector('.wa-msg-tick');
            const incomingTick = incomingRow.querySelector('.wa-msg-tick');
            
            if (currentTick && incomingTick) {
                if (currentTick.outerHTML !== incomingTick.outerHTML) {
                    currentTick.outerHTML = incomingTick.outerHTML;
                }
            } else if (!currentTick && incomingTick) {
                // If tick didn't exist but now does, append it to the timestamp container
                const timeContainer = currentRow.querySelector('.wa-msg-time') || currentRow.querySelector('.d-flex.justify-content-end.align-items-center');
                if (timeContainer) {
                    timeContainer.appendChild(incomingTick.cloneNode(true));
                }
            }
        });
    }

    async _surgicalRefresh(forceChatId = null) {
        const historyDiv = document.getElementById('wa_chat_history') || document.querySelector('.o_whatsapp_chat_history');
        const chatId = forceChatId || this._getActiveChatId();
        if (!historyDiv || !chatId) return;
        if (forceChatId && this._selectedChatId && Number(forceChatId) !== Number(this._selectedChatId)) {
            return;
        }

        // Mark the matching sidebar item as active so _getActiveChatId() can find it next time
        if (chatId) {
            document.querySelectorAll('.o_whatsapp_sidebar_item').forEach(el => {
                const elId = parseInt(el.getAttribute('data-chat-id'));
                el.classList.toggle('active', Number(elId) === Number(chatId));
            });
            this._selectedChatId = chatId;
            sessionStorage.setItem('wa_selected_chat_id', chatId);
        }

        // Remember scroll position BEFORE updating DOM
        const prevScrollTop = historyDiv.scrollTop;
        const prevScrollHeight = historyDiv.scrollHeight;

        try {
            // Use a timestamp in context to bust Odoo's compute field cache (history_html)
            const res_array = await this._rpc('whatsapp.chat', 'read', 
                [[chatId], ['history_html', 'unread_count', 'display_name', 'session_open']], 
                { context: { wa_history_limit: this._historyLimit, wa_ts: Date.now() } }
            );
            
            if (res_array && res_array[0]) {
                if (this._selectedChatId && Number(chatId) !== Number(this._selectedChatId)) {
                    return;
                }
                const res = res_array[0];
                const newHtml = res.history_html || '';
                if (this._lastHtml !== newHtml) {
                    const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
                    mount.dataset.waChatId = String(chatId);
                    delete mount.dataset.waLoadingChatId;
                    
                    try {
                        const historyMount = document.getElementById('wa-custom-history-mount');
                        if (!historyMount) return;

                        // --- MOBILE RESPONSIVENESS INIT ---
                        if (window.innerWidth <= 991) {
                            this._syncMobileLayout();
                        }

                        // --- BACK BUTTON HANDLER ---
                        const backBtn = document.querySelector('.wa-mobile-back-btn');
                        if (backBtn && !backBtn.dataset.bound) {
                            backBtn.dataset.bound = "true";
                            backBtn.addEventListener('click', () => {
                                this._openMobileChatList();
                            });
                        }
                    } catch(e) { console.error(e); }

                    const isInitialLoad = !this._lastHtml;
                    const shouldReplace = !newHtml || !this._lastHtml || this._isPaging || forceChatId || !mount.querySelector('[data-wa-message-id]');
                    const shouldSoftReveal = shouldReplace && !this._isPaging && (isInitialLoad || !!forceChatId);
                    if (shouldSoftReveal) {
                        this._prepareHistorySoftReveal(mount);
                    }
                    if (shouldReplace) {
                        mount.innerHTML = newHtml || '<div class="text-center text-muted py-5 small"><i class="fa fa-comments-o fa-2x d-block mb-2"></i>No messages yet</div>';
                    } else {
                        this._mergeHistoryHtml(mount, newHtml);
                    }
                    this._lastHtml = newHtml;
                    this._lastChatId = chatId;
                    // Update footer session state in real-time
                    this._updateFooterSessionState(res.session_open);

                    // Scroll logic: respect user position
                    if (this._isPaging) {
                        const addedHeight = historyDiv.scrollHeight - prevScrollHeight;
                        historyDiv.scrollTop = prevScrollTop + addedHeight;
                        this._isPaging = false;
                    } else if (isInitialLoad || this._userIsAtBottom || forceChatId) {
                        this._scrollToBottom(true, { instant: isInitialLoad || !!forceChatId });
                    }

                    this._attachScrollListener();
                    if (this._bindTopObserver) this._bindTopObserver();
                    this._injectScrollFAB();
                    this._tickSlaTimers();
                    this._enhanceComposer();
                    if (shouldSoftReveal) {
                        this._finishHistorySoftReveal(mount);
                    } else {
                        animateInboxRefresh(mount, { level: "subtle" });
                    }
                    mount.classList.remove('wa-history-switching');
                } else {
                    const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
                    mount.dataset.waChatId = String(chatId);
                    delete mount.dataset.waLoadingChatId;
                    this._lastChatId = chatId;
                    mount.classList.remove('wa-history-switching');
                }
            }
        } catch (e) {
            console.warn('[WhatsApp] Refresh error:', e);
            const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
            if (mount && (!forceChatId || Number(forceChatId) === Number(this._selectedChatId))) {
                mount.classList.remove('wa-history-switching');
                delete mount.dataset.waLoadingChatId;
                mount.innerHTML = '<div class="alert alert-danger m-4">RPC Error: ' + String(e.message || e) + '</div>';
            }
        }
    }

    // ── Send Message via RPC (Optimistic UI) ───────────────────────
    async _sendRPC(method, text, chatIdOverride = null, inputEl = null) {
        const chatId = chatIdOverride || this._getActiveChatId();
        if (!chatId) return;

        const input = inputEl || this._getComposerTextarea();
        if (input) input.value = '';

        // 1. Optimistic UI: Inject bubble instantly before server response
        const mount = document.getElementById('wa-custom-history-mount') || document.querySelector('.wa-chat-history-content-container');
        if (mount && method === 'action_send_quick_reply' && text) {
            const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            // Escape HTML to prevent XSS during optimistic render
            const safeText = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const tempBubble = `
                <div class="d-flex w-100 justify-content-end mb-3 wa-message-row wa-optimistic-bubble">
                    <div class="position-relative" style="max-width: 85%;">
                        <div class="p-2 rounded shadow-sm text-dark position-relative" style="background: #D9FDD3; border-top-right-radius: 0 !important; border: 1px solid #c2e6bc;">
                            <div class="text-break text-wrap wa-message-body" style="font-size: 0.95rem; line-height: 1.4; white-space: pre-wrap;">${safeText}</div>
                            <div class="d-flex justify-content-end align-items-center mt-1" style="font-size: 0.65rem; color: #667781; gap: 4px;">
                                <span>${time}</span>
                                <i class="fa fa-clock-o text-muted" title="Sending..."></i>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            mount.insertAdjacentHTML('beforeend', tempBubble);
            animateInboxRefresh(mount, { level: "subtle" });
            this._scrollToBottom(true);
        }

        try {
            await this._rpc('whatsapp.chat', method, [[chatId]], {
                context: { default_quick_reply_text: text }
            });
            if (method === 'action_send_quick_reply') this._playSound('sent', chatId);
            this._userIsAtBottom = true;
            // Clear the cached HTML so the next refresh ALWAYS re-renders
            this._lastHtml = null;
            // Immediate refresh — then a second pass after 1.5s (server-side async commit)
            await this._surgicalRefresh();
            setTimeout(() => { this._lastHtml = null; this._surgicalRefresh(); }, 1500);
        } catch (e) {
            console.error('[WhatsApp] Send failed:', e);
            if (mount) {
                const clockIcon = mount.querySelector('.wa-optimistic-bubble:last-child .fa-clock-o');
                if (clockIcon) {
                    clockIcon.className = 'fa fa-exclamation-circle text-danger';
                    clockIcon.title = 'Failed to send';
                }
            }
        }
    }

    // ── Presence ───────────────────────────────────────────────────
    async _touchPresence() {
        if (this._isTouchingPresence) return;
        this._isTouchingPresence = true;
        
        // Throttle presence updates to at most once every 10 seconds to prevent DB lock errors
        // (e.g., "could not serialize access due to concurrent update" on mail_presence)
        setTimeout(() => { this._isTouchingPresence = false; }, 10000);

        const chatId = this._getActiveChatId();
        const isActive = !document.hidden && document.hasFocus();
        if (this.socket?.connected) {
            this.socket.emit('presence', { chat_id: chatId, active: isActive });
        }
        if (!chatId) return;
        try {
            await this._rpc('whatsapp.chat', 'action_touch_agent_presence', [[chatId]], {
                is_active: isActive
            });
        } catch (e) { /* non-fatal */ }
    }

    // ── Composer Enhancements ───────────────────────────────────────
    _getHistoryMount() {
        return document.getElementById('wa-custom-history-mount')
            || document.querySelector('.wa-chat-history-content-container')
            || document.getElementById('wa_chat_history')
            || document.querySelector('.o_whatsapp_chat_history')
            || null;
    }

    _getComposerTextarea(root = document) {
        const scope = root || document;
        if (scope.matches?.('.wa-premium-input textarea')) return scope;
        if (scope.matches?.('textarea.wa-premium-input')) return scope;
        return scope.querySelector?.('.wa-premium-input textarea')
            || scope.querySelector?.('textarea.wa-premium-input')
            || null;
    }

    _enhanceComposer() {
        const textarea = this._getComposerTextarea();
        if (!textarea) return;
        textarea.setAttribute('maxlength', '4096');
        textarea.setAttribute('rows', textarea.getAttribute('rows') || '1');
        textarea.setAttribute('autocomplete', 'off');
        textarea.setAttribute('aria-label', 'Type a WhatsApp message');
        this._resizeComposer(textarea);
        this._updateComposerCounter(textarea);
        document.querySelectorAll('.wa-footer-icon-btn[data-wa-label], .wa-attachment-wrapper[data-wa-label]').forEach((button) => {
            const label = button.getAttribute('data-wa-label');
            if (label && !button.getAttribute('aria-label')) {
                button.setAttribute('aria-label', label);
            }
        });
        this._loadAiGuidanceForActiveChat(textarea.closest('.o_form_view') || document);
    }

    _resizeComposer(textarea) {
        if (!textarea || textarea.tagName !== 'TEXTAREA') return;
        textarea.style.height = 'auto';
        const minHeight = 44;
        const maxHeight = 112;
        const value = textarea.value || '';
        const measuredHeight = value.trim() ? (textarea.scrollHeight || minHeight) : minHeight;
        const nextHeight = Math.min(Math.max(measuredHeight, minHeight), maxHeight);
        textarea.style.height = `${nextHeight}px`;
        textarea.style.overflowY = (textarea.scrollHeight || 0) > maxHeight ? 'auto' : 'hidden';
    }

    _updateComposerCounter(textarea) {
        if (!textarea) return;
        const counter = document.getElementById('wa_composer_counter');
        const meta = counter?.closest('.wa-composer-meta');
        if (!counter || !meta) return;

        const count = (textarea.value || '').length;
        counter.textContent = `${count}/4096`;
        meta.classList.toggle('wa-counter-warn', count >= 3500 && count < 4096);
        meta.classList.toggle('wa-counter-danger', count >= 4096);
    }

    _getQuickReplyQuery(textarea) {
        if (!textarea) return null;
        const value = textarea.value || '';
        const cursor = Number.isInteger(textarea.selectionStart) ? textarea.selectionStart : value.length;
        const beforeCursor = value.slice(0, cursor);
        const match = beforeCursor.match(/(^|\s)\/([^\s]*)$/);
        return match ? (match[2] || '') : null;
    }

    _queueQuickReplySuggestions(textarea) {
        const query = this._getQuickReplyQuery(textarea);
        if (query === null) {
            this._hideQuickReplyPopover();
            return;
        }

        const chatId = this._getActiveChatId() || 'none';
        const queryKey = `${chatId}:${query}`;
        if (this._quickReplyQueryKey === queryKey && this._isQuickReplyOpen()) return;
        this._quickReplyQueryKey = queryKey;

        if (this._quickReplyFetchTimer) clearTimeout(this._quickReplyFetchTimer);
        this._quickReplyFetchTimer = setTimeout(() => {
            this._fetchQuickReplySuggestions(query, textarea);
        }, 140);
    }

    _isQuickReplyOpen() {
        const popover = document.getElementById('wa_quick_reply_popover');
        return !!(popover && !popover.classList.contains('d-none'));
    }

    async _fetchQuickReplySuggestions(query = '', textarea = null) {
        const input = textarea || this._getComposerTextarea();
        const chatId = this._getActiveChatId();
        if (!input) return;
        const requestKey = `${chatId || 'none'}:${query || ''}`;
        this._quickReplyQueryKey = requestKey;

        try {
            const items = await this._rpc('whatsapp.chat', 'get_quick_reply_suggestions', [chatId || false, query || '']);
            if (this._quickReplyQueryKey !== requestKey) return;
            this._quickReplyItems = Array.isArray(items) ? items : [];
            this._quickReplyActiveIndex = 0;
            this._renderQuickReplyPopover(this._quickReplyItems, input);
        } catch (e) {
            console.warn('[WhatsApp] Quick reply suggestions failed:', e);
            this._hideQuickReplyPopover();
        }
    }

    _renderQuickReplyPopover(items, textarea) {
        const popover = document.getElementById('wa_quick_reply_popover');
        if (!popover || !textarea) return;

        if (!items.length) {
            popover.innerHTML = '<div class="wa-quick-reply-empty">No quick replies</div>';
            popover.classList.remove('d-none');
            return;
        }

        popover.innerHTML = items.map((item, index) => `
            <button type="button" class="wa-quick-reply-item ${index === this._quickReplyActiveIndex ? 'active' : ''}" data-index="${index}">
                <span class="wa-quick-reply-shortcut">/${this._escapeHtml(item.shortcut || item.name || 'reply')}</span>
                <span class="wa-quick-reply-title">${this._escapeHtml(item.name || item.shortcut || 'Quick reply')}</span>
                <span class="wa-quick-reply-preview">${this._escapeHtml(item.preview || item.message || '')}</span>
            </button>
        `).join('');
        popover.classList.remove('d-none');
    }

    _moveQuickReplySelection(delta) {
        const total = this._quickReplyItems.length;
        if (!total) return;

        this._quickReplyActiveIndex = (this._quickReplyActiveIndex + delta + total) % total;
        document.querySelectorAll('.wa-quick-reply-item').forEach((item, index) => {
            const active = index === this._quickReplyActiveIndex;
            item.classList.toggle('active', active);
            if (active) item.scrollIntoView({ block: 'nearest' });
        });
    }

    _insertQuickReply(item, textarea = null) {
        const input = textarea || this._getComposerTextarea();
        if (!item || !input) return;

        const message = item.message || '';
        const value = input.value || '';
        const start = Number.isInteger(input.selectionStart) ? input.selectionStart : value.length;
        const end = Number.isInteger(input.selectionEnd) ? input.selectionEnd : start;
        const beforeCursor = value.slice(0, start);
        const afterSelection = value.slice(end);
        const slashMatch = beforeCursor.match(/(^|\s)\/([^\s]*)$/);

        let nextValue;
        let cursor;
        if (slashMatch) {
            const tokenStart = beforeCursor.length - slashMatch[0].length + (slashMatch[1] || '').length;
            nextValue = value.slice(0, tokenStart) + message + afterSelection;
            cursor = tokenStart + message.length;
        } else {
            const separator = value && !/[\s\n]$/.test(beforeCursor) ? ' ' : '';
            nextValue = value.slice(0, start) + separator + message + afterSelection;
            cursor = start + separator.length + message.length;
        }

        if (nextValue.length > 4096) {
            nextValue = nextValue.slice(0, 4096);
            cursor = Math.min(cursor, 4096);
        }

        input.value = nextValue;
        input.focus();
        if (input.setSelectionRange) input.setSelectionRange(cursor, cursor);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        this._resizeComposer(input);
        this._updateComposerCounter(input);
        this._hideQuickReplyPopover();
    }

    _hideQuickReplyPopover() {
        const popover = document.getElementById('wa_quick_reply_popover');
        if (popover) {
            popover.classList.add('d-none');
            popover.innerHTML = '';
        }
        this._quickReplyItems = [];
        this._quickReplyActiveIndex = 0;
        this._quickReplyQueryKey = null;
        if (this._quickReplyFetchTimer) {
            clearTimeout(this._quickReplyFetchTimer);
            this._quickReplyFetchTimer = null;
        }
    }

    _escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // ── Footer Session State ────────────────────────────────────────
    _updateFooterSessionState(sessionOpen) {
        // Instantly toggle session-closed vs session-open footer without a form reload
        const closedDiv = document.querySelector('.o_whatsapp_template_row');
        const openDiv = document.querySelector('.wa-premium-footer-bar');
        if (!closedDiv && !openDiv) return;
        if (sessionOpen) {
            if (closedDiv) closedDiv.style.display = 'none';
            if (openDiv) openDiv.style.display = '';
        } else {
            if (closedDiv) closedDiv.style.display = '';
            if (openDiv) openDiv.style.display = 'none';
        }
    }

    // ── Typing Indicator ───────────────────────────────────────────
    _showTypingIndicator(data = {}) {
        const activeChatId = this._getActiveChatId();
        if (data.chat_id && activeChatId && Number(data.chat_id) !== Number(activeChatId)) return;
        
        const historyDiv = document.querySelector('.wa-chat-history-content-container');
        if (!historyDiv) return;

        let indicator = document.getElementById('wa_typing_indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'wa_typing_indicator';
            indicator.className = 'wa-typing-bubble wa-message-row';
            indicator.innerHTML = `
                <div class="wa-typing-dots">
                    <span></span><span></span><span></span>
                </div>
            `;
            // Append to mount if exists, else historyDiv
            const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
            mount.appendChild(indicator);
            
            // Auto-scroll if user is at bottom
            if (this._userIsAtBottom) {
                this._scrollToBottom(true);
            }
        }
        
        clearTimeout(this._typingTimer);
        this._typingTimer = setTimeout(() => {
            if (indicator) indicator.remove();
        }, 3500);
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
                        const t = this._getComposerTextarea(btn.closest('.o_form_view') || document);
                        if (t) {
                            t.value = (t.value || '') + e;
                            t.focus();
                            t.dispatchEvent(new Event('input', { bubbles: true }));
                            t.dispatchEvent(new Event('change', { bubbles: true }));
                            this._resizeComposer(t);
                            this._updateComposerCounter(t);
                        }
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
    _getSidebarActiveChatId() {
        const activeItems = Array.from(document.querySelectorAll('.o_whatsapp_sidebar_item.active'));
        const sidebarActive = activeItems.find((item) => {
            const pane = item.closest('.wa-pane-mount');
            const sidebar = item.closest('.wa-left-sidebar');
            if (!sidebar) return false;
            if (pane && pane.classList.contains('d-none')) return false;
            return item.offsetParent !== null || sidebar.classList.contains('wa-mobile-chat-list-drawer');
        }) || null;
        if (!sidebarActive) return null;
        const id = parseInt(sidebarActive.getAttribute('data-chat-id'));
        return id || null;
    }

    _getChatIdForUserAction(triggerEl = null) {
        const formView = triggerEl?.closest?.('.o_form_view[data-model="whatsapp.chat"][data-res-id]');
        if (formView) {
            const id = parseInt(formView.getAttribute('data-res-id'));
            if (id) return id;
        }

        const sidebarId = this._getSidebarActiveChatId();
        if (sidebarId) return sidebarId;

        return this._getActiveChatId();
    }

    _setCleanChatUrl(chatId) {
        if (!chatId || !window.history?.replaceState) return;
        try {
            const cleanUrl = `${window.location.origin}/odoo/whatsapp.chat/${chatId}${window.location.search || ''}`;
            if (window.location.href !== cleanUrl) {
                window.history.replaceState(window.history.state || {}, '', cleanUrl);
            }
        } catch (error) {
            console.warn('[WhatsApp] Could not normalize chat URL:', error);
        }
    }

    async _waitForHistoryMount(attempts = 14, delayMs = 70) {
        for (let i = 0; i < attempts; i++) {
            const mount = document.getElementById('wa-custom-history-mount');
            const historyDiv = document.getElementById('wa_chat_history') || document.querySelector('.o_whatsapp_chat_history');
            if (mount && historyDiv) {
                return mount;
            }
            await new Promise(resolve => setTimeout(resolve, delayMs));
        }
        return document.getElementById('wa-custom-history-mount');
    }

    _getActiveChatId() {
        const hasChatDOM = !!(document.getElementById('wa_chat_history') || 
                              document.getElementById('wa-custom-history-mount') ||
                              document.querySelector('.o_whatsapp_chat_history') ||
                              document.querySelector('.wa-chat-history-content-container'));

        if (!hasChatDOM) {
            // Staleness guard: Clear all cached IDs when view is destroyed/navigated away
            this._selectedChatId = null;
            this._lastChatId = null;
            this._lastHtml = null;
            return null;
        }

        // In the Team Inbox hybrid view, the active sidebar row is the
        // freshest selection. Odoo can briefly keep the previous form res_id
        // while replacing records, so this prevents wrong-chat actions.
        const sidebarId = this._getSidebarActiveChatId();
        if (sidebarId) {
            this._selectedChatId = sidebarId;
            this._lastChatId = sidebarId;
            return sidebarId;
        }

        // 1. Strict Odoo 19 URL path checks. If the router accidentally stacked
        // paths, use the last chat id because it reflects the latest click.
        const pathMatches = Array.from(
            window.location.pathname.matchAll(/(?:\/odoo)?\/(?:whatsapp\.chat|whatsapp-chats)\/(\d+)/g)
        );
        if (pathMatches.length) {
            const id = parseInt(pathMatches[pathMatches.length - 1][1]);
            if (id) {
                this._selectedChatId = id;
                this._lastChatId = id;
                return id;
            }
        }

        // 2. Strict Odoo legacy hash check (only if model is whatsapp.chat)
        const hash = window.location.hash.slice(1);
        if (hash) {
            const params = new URLSearchParams(hash);
            const model = params.get('model');
            if (!model || model === 'whatsapp.chat') {
                const id = params.get('id') || params.get('res_id');
                if (id) {
                    const parsedId = parseInt(id);
                    if (parsedId) {
                        this._selectedChatId = parsedId;
                        this._lastChatId = parsedId;
                        return parsedId;
                    }
                }
            }
        }

        // 3. Odoo form view hidden input (only for whatsapp.chat model)
        const hiddenResId = document.querySelector('.o_form_view[data-model="whatsapp.chat"] input[name="id"]');
        if (hiddenResId) {
            const id = parseInt(hiddenResId.value);
            if (id) {
                this._selectedChatId = id;
                this._lastChatId = id;
                return id;
            }
        }

        // 4. Read from the data attribute Odoo sets on .o_form_view (whatsapp.chat only)
        const formView = document.querySelector('.o_form_view[data-model="whatsapp.chat"][data-res-id]');
        if (formView) {
            const id = parseInt(formView.getAttribute('data-res-id'));
            if (id) {
                this._selectedChatId = id;
                this._lastChatId = id;
                return id;
            }
        }

        // 6. Fallback: Explicit user selection (in‑memory)
        if (this._selectedChatId) return this._selectedChatId;

        // 7. Fallback: Persisted session selection
        const persisted = sessionStorage.getItem('wa_selected_chat_id');
        if (persisted) {
            const id = parseInt(persisted);
            if (id) {
                this._selectedChatId = id;
                this._lastChatId = id;
                return id;
            }
        }

        // 8. Fallback: State cache
        if (this._lastChatId) {
            return this._lastChatId;
        }

        return null;
    }

    destroy() {
        if (this._historyMountObserver) {
            this._historyMountObserver.disconnect();
            this._historyMountObserver = null;
        }
        if (this._componentInitInterval) {
            clearInterval(this._componentInitInterval);
            this._componentInitInterval = null;
        }
        if (this._refreshInterval) {
            clearTimeout(this._refreshInterval);
            this._refreshInterval = null;
        }
        if (this._mobileResizeTimer) {
            clearTimeout(this._mobileResizeTimer);
            this._mobileResizeTimer = null;
        }
        if (this._presenceInterval) {
            clearInterval(this._presenceInterval);
            this._presenceInterval = null;
        }
        if (this._slaInterval) {
            clearInterval(this._slaInterval);
            this._slaInterval = null;
        }
        if (this._typingTimer) {
            clearTimeout(this._typingTimer);
            this._typingTimer = null;
        }
        if (this._boundHashChange) {
            window.removeEventListener('hashchange', this._boundHashChange);
            window.removeEventListener('popstate', this._boundHashChange); // BUG 9 FIX: clean up popstate listener too
            this._boundHashChange = null;
        }
        if (this._boundVisibilityChange) {
            document.removeEventListener('visibilitychange', this._boundVisibilityChange);
            this._boundVisibilityChange = null;
        }
        if (this._boundGlobalClick) {
            document.removeEventListener('click', this._boundGlobalClick, true);
            this._boundGlobalClick = null;
        }
        if (this._boundResize) {
            window.removeEventListener('resize', this._boundResize);
            this._boundResize = null;
        }
        if (this._boundMobileKeydown) {
            window.removeEventListener('keydown', this._boundMobileKeydown);
            this._boundMobileKeydown = null;
        }
        if (this._boundKeydown) {
            document.removeEventListener('keydown', this._boundKeydown);
            this._boundKeydown = null;
        }
        if (this._boundComposerInput) {
            document.removeEventListener('input', this._boundComposerInput);
            this._boundComposerInput = null;
        }
        if (this._quickReplyFetchTimer) {
            clearTimeout(this._quickReplyFetchTimer);
            this._quickReplyFetchTimer = null;
        }
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        if (this._busSubscriptions) {
            this._busSubscriptions.forEach(({ type, callback }) => {
                this.bus.unsubscribe(type, callback);
            });
            this._busSubscriptions = null;
        }
    }

    // BUG 2 FIX: Removed duplicate _rpc definition — primary is at line 272
}

registry.category("services").add("whatsapp_realtime", {
    dependencies: ["bus_service", "action", "orm"],
    start(env, services) {
        try {
            return new WhatsAppChatHandler(env, services);
        } catch (e) {
            console.error('[WhatsApp] Fatal service start error:', e);
            return {};
        }
    },
});
