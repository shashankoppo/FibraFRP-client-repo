/** @odoo-module **/

import { registry } from "@web/core/registry";
import { playTone } from "@elsx_whatsapp_marketing/js/notification_tones";

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
        this._historyLimit = 100;
        this._isPaging = false;
        this._userIsAtBottom = true;
        this._notificationPreferencesByAccount = {};
        this._accountByChat = {};
        this._boundHashChange = null;
        this._lastPlayedMessageId = new Set();
        this._processedMessageIds = new Set();
        
        // --- Sidebar State ---
        this._sidebarFilter = sessionStorage.getItem('wa_sidebar_filter') || 'all';
        this._sidebarQuery = '';
        // Per-pane fetch guards and pagination (map keyed by paneKey)
        this._isFetchingSidebar = { active: false, request: false, intervened: false };
        this._hasMoreSidebar = { active: true, request: true, intervened: true };
        this._sidebarOffsets = { active: 0, request: 0, intervened: 0 };
        
        console.log('[WhatsApp] Handler Service Initialized (v7.6 - SPA Engine)');

        this._initGlobalComponents();
        
        this._boundHashChange = () => {
            setTimeout(() => this._surgicalRefresh(), 250);
        };
        window.addEventListener('hashchange', this._boundHashChange);
        window.addEventListener('popstate', this._boundHashChange);

        this._componentInitInterval = setInterval(() => this._initGlobalComponents(), 5000);

        try { this.init(); } catch (e) { console.warn('[WhatsApp] Service init error:', e); }
        try { this.initSocket(); } catch (e) { console.warn('[WhatsApp] Socket init error:', e); }
    }

    _initGlobalComponents() {
        // Run safely without crashing if DOM is not ready
        if (!document.head) {
            setTimeout(() => this._initGlobalComponents(), 100);
            return;
        }

        // Hide the "WhatsApp Marketing" app from the main Odoo menu instantly via CSS
        if (!document.getElementById('wa_hide_menu_style')) {
            const style = document.createElement('style');
            style.id = 'wa_hide_menu_style';
            style.innerHTML = `
                /* Hide from Enterprise Home Screen (App Switcher) */
                a.o_app[data-menu-xmlid="elsx_whatsapp_marketing.menu_whatsapp_root"] { display: none !important; }
                /* Hide from Community Navbar / Dropdown */
                a.dropdown-item[data-menu-xmlid="elsx_whatsapp_marketing.menu_whatsapp_root"] { display: none !important; }
                .o_menu_sections a[data-menu-xmlid="elsx_whatsapp_marketing.menu_whatsapp_root"] { display: none !important; }
            `;
            document.head.appendChild(style);
        }

        if (!document.body) {
            // Document body not ready yet, defer FAB injection
            setTimeout(() => this._initGlobalComponents(), 100);
            return;
        }

        if (!document.getElementById('wa_global_fab')) {
            const fab = document.createElement('div');
            fab.id = 'wa_global_fab';
            fab.className = 'wa-floating-fab animate-bounce-in';
            fab.title = 'Open WhatsApp';
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

        await this.actionService.doAction(actionObj);

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

        let socketUrl = 'http://localhost:3000';
        try {
            const sysParam = await this._rpc('whatsapp.chat', 'get_sidecar_url', []);
            if (sysParam) {
                socketUrl = sysParam;
            } else {
                const origin = window.location.origin;
                if (!origin.includes('localhost')) {
                    socketUrl = origin.replace('8069', '3000');
                }
            }
        } catch (e) {
            console.warn('[WhatsApp] Could not fetch sidecar url:', e);
        }

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
            if (this._isDuplicateNewMessage(data || {})) {
                return;
            }
            const activeChatId = this._getActiveChatId();
            
            // 1. Refresh UI if it's for the current chat (or we are in list view)
            if (!activeChatId || activeChatId == data.chat_id) {
                this._surgicalRefresh();
            }

            // 1b. Refresh sidebar preview for this chat
            if (data.chat_id) {
                this._updateSidebarForChat(data.chat_id);
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
            
            // Listen for notifications
            this.bus.addEventListener('notification', ({ detail: notifications }) => {
                for (const { type, payload } of notifications) {
                    if (WA_NOTIFICATION_TYPES.includes(type)) {
                        this._onNotification(type, payload);
                    } else if (type === 'whatsapp_typing') {
                        this._showTypingIndicator(payload || {});
                    }
                }
            });
        } catch (e) {
            console.error('[WhatsApp] Bus subscription error:', e);
        }

        // Initial load of history — wait for Odoo form DOM to settle then fetch
        setTimeout(() => {
            this._attachScrollListener();
            this._injectScrollFAB();
            this._injectMobileBackButton();
            this._applyRightPanePreference();
            this._tickSlaTimers();
            this._initSidebarEngine();

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
                this._tickSlaTimers();
                this._initSidebarEngine();
            }
        });
        this._historyMountObserver.observe(document.body, { childList: true, subtree: true });

        // Fallback polling — fires every 8 seconds as safety net when bus/socket is absent.
        // This ensures messages are always visible even without a sidecar.
        this._refreshInterval = setInterval(() => {
            const chatId = this._getActiveChatId();
            if (chatId) this._surgicalRefresh();
        }, 8000);

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

        // Enter to Send
        if (!this._boundKeydown) {
            this._boundKeydown = (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    const textarea = e.target.closest('.wa-premium-input textarea') || e.target.closest('.wa-premium-input');
                    if (textarea) {
                        e.preventDefault();
                        const sendBtn = document.querySelector('button[name="action_send_quick_reply"]');
                        if (sendBtn) sendBtn.click();
                    }
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
        filters.forEach(btn => {
            if (btn._waFilterBound) return;
            btn._waFilterBound = true;
            btn.addEventListener('click', () => {
                filters.forEach(f => {
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
            // Restore active state
            if (btn.dataset.filter === this._sidebarFilter) {
                filters.forEach(f => {
                    f.classList.remove('bg-success', 'text-white');
                    f.classList.add('bg-light', 'text-muted');
                });
                btn.classList.remove('bg-light', 'text-muted');
                btn.classList.add('bg-success', 'text-white');
            }
        });

        // Initial Load: render all three panes
        this._refreshAllPanes();
    }

    // Helper: refresh all sidebar panes from offset 0
    _refreshAllPanes() {
        Object.keys(this._paneIds).forEach(paneKey => {
            this._fetchAndRenderSidebar(paneKey, 0, false);
        });
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
                pane: paneKey // optional, backend can ignore
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

            const badge = document.querySelector(`.wa-pane-count-${paneKey}`);
            if (badge) {
                const totalLoaded = this._sidebarOffsets[paneKey];
                badge.textContent = totalLoaded + (this._hasMoreSidebar[paneKey] ? '+' : '');
            }

            let html = '';
            chats.forEach(chat => {
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
                
                // AiSensy Premium Avatar Generation
                const initial = chat.display_name_initial || '?';
                const colors = ['#1abc9c', '#2ecc71', '#3498db', '#9b59b6', '#34495e', '#16a085', '#27ae60', '#2980b9', '#8e44ad', '#2c3e50', '#f1c40f', '#e67e22', '#e74c3c', '#95a5a6', '#f39c12', '#d35400', '#c0392b', '#7f8c8d'];
                let hash = 0;
                for (let i = 0; i < safeName.length; i++) hash = safeName.charCodeAt(i) + ((hash << 5) - hash);
                const avatarColor = colors[Math.abs(hash) % colors.length];

                html += `
                    <button type="button" class="o_whatsapp_sidebar_btn p-0 border-0 bg-transparent w-100 text-start">
                        <div class="p-2 px-3 border-bottom cursor-pointer o_whatsapp_sidebar_item hover-bg-light position-relative ${isActive}" 
                            data-chat-id="${chat.id}" style="transition: all 0.2s; border-left: 4px solid transparent;">
                            <div class="d-flex align-items-center">
                                <div class="o_whatsapp_avatar position-relative shadow-sm d-flex align-items-center justify-content-center text-white fw-bold" style="background: ${avatarColor} !important; border-radius: 50%; user-select: none;">${initial}</div>
                                <div class="ms-3 flex-grow-1 overflow-hidden">
                                    <div class="d-flex justify-content-between align-items-start mb-1">
                                        <div class="fw-bold text-truncate o_whatsapp_chat_item_name" style="max-width: 140px; font-size: 1.05rem;">${safeName}</div>
                                        <div class="d-flex flex-column align-items-end">
                                            <div class="small text-muted text-nowrap" style="font-size: 0.75rem; min-width: 60px text-align: right;">${chat.last_message_date_str || ''}</div>
                                            ${slaBadge}
                                        </div>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div class="small text-muted text-truncate d-flex align-items-center gap-1" style="max-width: 140px; font-size: 0.85rem;">
                                            ${statusIcon}
                                            ${safeBody}
                                        </div>
                                        <div class="d-flex align-items-center gap-1">
                                            ${pinnedIcon}
                                            ${archivedIcon}
                                            ${unreadBadge}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </button>
                `;
            });
            mount.insertAdjacentHTML('beforeend', html);
        } catch (e) {
            console.error('[WhatsApp] Sidebar fetch error:', e);
            if (!append && mount) mount.innerHTML = '<div class="text-center p-3 text-danger"><i class="fa fa-warning"></i> Error loading</div>';
        }
        this._isFetchingSidebar[paneKey] = false;
        this._bindSidebarClickHandlers();
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

    _scrollToBottom(force = false) {
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

        if (force || this._userIsAtBottom) {
            this._isInitialScroll = true;
            
            const doScroll = () => {
                historyDiv.scrollTop = historyDiv.scrollHeight + 1000;
                if (oContent) {
                    oContent.scrollTop = oContent.scrollHeight + 1000;
                }
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
            setTimeout(doScroll, 1200);
        } else {
            this._isInitialScroll = false;
        }
    }

    // ── Scroll-to-Bottom FAB ───────────────────────────────────────
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

    _setRightPaneOpen(isOpen) {
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
    _onNotification(type, payload) {
        if (type === 'whatsapp_typing') {
            this._showTypingIndicator(payload || {});
            return;
        }
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

        // Also instantly update the sidebar for the chat receiving the message!
        if (payload?.chat_id) {
            this._updateSidebarForChat(payload.chat_id);
        }
    }

    async _updateSidebarForChat(chatId) {
        if (!chatId) return;
        try {
            const res = await this._rpc('whatsapp.chat', 'read', [[parseInt(chatId)], ['last_message_body', 'last_message_date', 'unread_count']]);
            if (!res || !res[0]) return;
            const data = res[0];

            const sidebarItem = document.querySelector(`.o_whatsapp_sidebar_item[data-chat-id="${chatId}"]`);
            if (sidebarItem) {
                // Update preview text
                const bodyEl = sidebarItem.querySelector('.text-muted.text-truncate.d-flex');
                if (bodyEl) bodyEl.innerHTML = data.last_message_body || 'No messages yet';
                const dateEl = sidebarItem.querySelector('.d-flex.flex-column.align-items-end .small.text-muted');
                if (dateEl) dateEl.innerText = data.last_message_date || '';
                // Move to top of its pane
                const btnContainer = sidebarItem.closest('button.o_whatsapp_sidebar_btn');
                if (btnContainer) {
                    const pane = btnContainer.parentElement;
                    if (pane && pane.firstChild !== btnContainer) pane.prepend(btnContainer);
                }
                // Update unread badge
                let badge = sidebarItem.querySelector('.bg-success.rounded-pill');
                if (data.unread_count > 0 && this._getActiveChatId() !== parseInt(chatId)) {
                    if (!badge) {
                        badge = document.createElement('div');
                        badge.className = 'badge rounded-pill bg-success shadow-sm';
                        badge.style.cssText = 'padding: 4px 8px; font-size: 0.7rem;';
                        const rightSide = sidebarItem.querySelector('.d-flex.align-items-center.gap-1');
                        if (rightSide) rightSide.appendChild(badge);
                    }
                    badge.innerText = data.unread_count;
                } else if (badge) {
                    badge.remove();
                }
            } else {
                // Not found in any pane — new chat, re-fetch all panes
                this._refreshAllPanes();
            }
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
                    const sidebar = document.querySelector('.wa-left-sidebar');
                    const main = document.querySelector('.o_whatsapp_chat_main');
                    if (sidebar) { sidebar.classList.add('d-none'); sidebar.classList.remove('d-flex'); }
                    if (main) main.classList.remove('d-none');
                }
            }
            return;
        }
        // Mobile Back Button
        const mobileBackBtn = e.target.closest('.wa-mobile-back-btn');
        if (mobileBackBtn) {
            e.preventDefault(); e.stopPropagation();
            const sidebar = document.querySelector('.wa-left-sidebar');
            const main = document.querySelector('.o_whatsapp_chat_main');
            if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
            if (main) main.classList.add('d-none');
            // Optionally reset active chat context if you want to force them to pick again
            // this._switchChatContext(null, null); 
            return;
        }
        
        // Send Template Wizard Intercept
        const templateBtn = e.target.closest('button[name="action_open_send_wizard"]');
        if (templateBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getActiveChatId();
            if (chatId) {
                this.actionService.doAction({
                    type: 'ir.actions.act_window',
                    name: 'Send WhatsApp Message',
                    res_model: 'whatsapp.send.wizard',
                    view_mode: 'form',
                    target: 'new',
                    views: [[false, 'form']],
                    context: { default_chat_id: chatId, active_id: chatId, active_model: 'whatsapp.chat', active_ids: [chatId] }
                }, {
                    onClose: () => {
                        this._surgicalRefresh(chatId);
                        this._refreshAllPanes();
                    }
                });
            }
            return;
        }

        // View Partner Intercept
        const partnerBtn = e.target.closest('button[name="action_view_partner"]');
        if (partnerBtn) {
            e.preventDefault(); e.stopPropagation();
            const chatId = this._getActiveChatId();
            if (chatId) {
                this._rpc('whatsapp.chat', 'read', [[chatId], ['partner_id']]).then((res) => {
                    if (res && res[0] && res[0].partner_id) {
                        const pid = Array.isArray(res[0].partner_id) ? res[0].partner_id[0] : res[0].partner_id;
                        this.actionService.doAction({
                            type: 'ir.actions.act_window',
                            res_model: 'res.partner',
                            res_id: pid,
                            view_mode: 'form',
                            views: [[false, 'form']],
                            target: 'current'
                        });
                    }
                });
            }
            return;
        }

        // Send message
        const sendBtn = e.target.closest('button[name="action_send_quick_reply"]');
        if (sendBtn) {
            const mediaPreview = document.querySelector('.wa-floating-attachment-preview');
            if (mediaPreview && !mediaPreview.parentElement.hasAttribute('invisible') && mediaPreview.offsetParent !== null) {
                return; // Let Odoo native form handle file upload
            }
            
            const input = document.querySelector('.wa-premium-input textarea') || document.querySelector('.wa-premium-input');
            if (input && input.value.trim()) {
                e.preventDefault(); e.stopPropagation();
                const chatId = this._getActiveChatId();
                if (chatId) {
                    this._sendRPC('action_send_quick_reply', input.value.trim()).then(() => {
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

    // ── Twilio-Style Atomic Chat Context Switch ──────────────────────
    async _switchChatContext(chatId, sidebarEl) {
        if (!chatId || chatId === this._lastChatId) return;

        // 1. Update state instantly
        this._lastChatId = chatId;
        this._selectedChatId = chatId;
        sessionStorage.setItem('wa_selected_chat_id', chatId);
        this._lastHtml = null;
        this._historyLimit = 100;
        this._userIsAtBottom = true;
        this._isPaging = false;

        // 2. Mark active sidebar item immediately (zero-latency visual)
        document.querySelectorAll('.o_whatsapp_sidebar_item').forEach(el => {
            const elId = parseInt(el.getAttribute('data-chat-id'));
            el.classList.toggle('active', el === sidebarEl || elId === chatId);
        });

        // 3. Mark as read immediately to clear badge
        this._rpc('whatsapp.chat', 'action_mark_read', [[chatId]]).catch(() => {});
        const unreadBadge = sidebarEl?.querySelector('.o_whatsapp_unread_count');
        if (unreadBadge) unreadBadge.remove();

        // 4. Show loading skeleton in the history canvas instantly
        const mount = document.getElementById('wa-custom-history-mount') || document.querySelector('.wa-chat-history-content-container');
        if (mount) {
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
            await this.actionService.doAction({
                type: 'ir.actions.act_window',
                res_model: 'whatsapp.chat',
                res_id: chatId,
                views: [[false, 'form']],
                target: 'current',
            }, {
                stackPosition: 'replaceCurrentAction',
            });
        } catch (err) {
            console.error('[WhatsApp] _switchChatContext actionService.doAction error:', err);
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
    _mergeHistoryHtml(mount, nextHtml) {
        const template = document.createElement('template');
        template.innerHTML = nextHtml || '';

        const currentIds = new Set(
            Array.from(mount.querySelectorAll('[data-wa-message-id]')).map((row) => row.dataset.waMessageId)
        );
        const incomingRows = Array.from(template.content.querySelectorAll('[data-wa-message-id]'));
        const missingIds = new Set(
            incomingRows
                .map((row) => row.dataset.waMessageId)
                .filter((messageId) => messageId && !currentIds.has(messageId))
        );

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
                const timeContainer = currentRow.querySelector('.d-flex.justify-content-end.align-items-center');
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

        // Mark the matching sidebar item as active so _getActiveChatId() can find it next time
        if (chatId) {
            document.querySelectorAll('.o_whatsapp_sidebar_item').forEach(el => {
                const elId = parseInt(el.getAttribute('data-chat-id'));
                el.classList.toggle('active', elId === chatId);
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
                const res = res_array[0];
                const newHtml = res.history_html || '';
                if (this._lastHtml !== newHtml) {
                    const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
                    
                    try {
                        const historyMount = document.getElementById('wa-custom-history-mount');
                        if (!historyMount) return;

                        // --- MOBILE RESPONSIVENESS INIT ---
                        if (window.innerWidth <= 991) {
                            const sidebar = document.querySelector('.wa-left-sidebar');
                            const main = document.querySelector('.o_whatsapp_chat_main');
                            const chatId = this._getActiveChatId();
                            if (!chatId) {
                                // No chat selected: show sidebar, hide main chat
                                if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
                                if (main) main.classList.add('d-none');
                            } else if (main && main.classList.contains('d-none')) {
                                // Chat selected but main is hidden (shouldn't happen on refresh, but just in case)
                                if (sidebar) { sidebar.classList.add('d-none'); sidebar.classList.remove('d-flex'); }
                                main.classList.remove('d-none');
                            }
                        }

                        // --- BACK BUTTON HANDLER ---
                        const backBtn = document.querySelector('.wa-mobile-back-btn');
                        if (backBtn && !backBtn.dataset.bound) {
                            backBtn.dataset.bound = "true";
                            backBtn.addEventListener('click', () => {
                                const sidebar = document.querySelector('.wa-left-sidebar');
                                const main = document.querySelector('.o_whatsapp_chat_main');
                                if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
                                if (main) main.classList.add('d-none');
                            });
                        }
                    } catch(e) { console.error(e); }

                    const shouldReplace = this._isPaging || forceChatId || !mount.querySelector('[data-wa-message-id]');
                    if (shouldReplace) {
                        mount.innerHTML = newHtml || '<div class="text-center text-muted py-5 small"><i class="fa fa-comments-o fa-2x d-block mb-2"></i>No messages yet</div>';
                    } else {
                        this._mergeHistoryHtml(mount, newHtml);
                    }
                    const isInitialLoad = !this._lastHtml;
                    this._lastHtml = newHtml;
                    // Update footer session state in real-time
                    this._updateFooterSessionState(res.session_open);

                    // Scroll logic: respect user position
                    if (this._isPaging) {
                        const addedHeight = historyDiv.scrollHeight - prevScrollHeight;
                        historyDiv.scrollTop = prevScrollTop + addedHeight;
                        this._isPaging = false;
                    } else if (isInitialLoad || this._userIsAtBottom || forceChatId) {
                        this._scrollToBottom(true);
                    }

                    this._attachScrollListener();
                    if (this._bindTopObserver) this._bindTopObserver();
                    this._injectScrollFAB();
                    this._tickSlaTimers();
                }
            }
        } catch (e) {
            console.warn('[WhatsApp] Refresh error:', e);
            const mount = document.getElementById('wa-custom-history-mount') || historyDiv;
            if (mount) mount.innerHTML = '<div class="alert alert-danger m-4">RPC Error: ' + String(e.message || e) + '</div>';
        }
    }

    // ── Send Message via RPC (Optimistic UI) ───────────────────────
    async _sendRPC(method, text) {
        const chatId = this._getActiveChatId();
        if (!chatId) return;

        const input = document.querySelector('.wa-premium-input textarea') || document.querySelector('.wa-premium-input');
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
        const hasChatDOM = !!(document.getElementById('wa_chat_history') || 
                              document.getElementById('wa-custom-history-mount') ||
                              document.querySelector('.o_whatsapp_chat_history') ||
                              document.querySelector('.wa-chat-history-content-container'));

        if (hasChatDOM) {
            // 1. Odoo 19 URL path: /odoo/whatsapp.chat/123 or /odoo/whatsapp-chats/123
            const pathMatch = window.location.pathname.match(/\/odoo\/whatsapp\.chat\/(\d+)/) || 
                              window.location.pathname.match(/\/odoo\/whatsapp-chats\/(\d+)/) ||
                              window.location.pathname.match(/\/odoo\/[^/]+\/(\d+)/);
            if (pathMatch) {
                const id = parseInt(pathMatch[1]);
                if (id) {
                    this._selectedChatId = id;
                    this._lastChatId = id;
                    return id;
                }
            }

            // 2. Odoo legacy hash: #id=123 or #res_id=123
            const hash = window.location.hash.slice(1);
            if (hash) {
                const params = new URLSearchParams(hash);
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

            // 3. Odoo form view hidden input (injected by form renderer)
            const hiddenResId = document.querySelector('input[name="id"], [data-res-id]');
            if (hiddenResId) {
                const id = parseInt(hiddenResId.value || hiddenResId.getAttribute('data-res-id'));
                if (id) {
                    this._selectedChatId = id;
                    this._lastChatId = id;
                    return id;
                }
            }

            // 4. Read from the data attribute Odoo sets on .o_form_view
            const formView = document.querySelector('.o_form_view[data-res-id]');
            if (formView) {
                const id = parseInt(formView.getAttribute('data-res-id'));
                if (id) {
                    this._selectedChatId = id;
                    this._lastChatId = id;
                    return id;
                }
            }

            // 5. Sidebar active item (team inbox list-form hybrid view)
            const sidebarActive = document.querySelector('.o_whatsapp_sidebar_item.active');
            if (sidebarActive) {
                const id = parseInt(sidebarActive.getAttribute('data-chat-id'));
                if (id) {
                    this._selectedChatId = id;
                    this._lastChatId = id;
                    return id;
                }
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

        // 8. Fallback: State atomic cache
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
            clearInterval(this._refreshInterval);
            this._refreshInterval = null;
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
        if (this._boundKeydown) {
            document.removeEventListener('keydown', this._boundKeydown);
            this._boundKeydown = null;
        }
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
    }

    async _rpc(model, method, args = [], kwargs = {}) {
        return this.orm.call(model, method, args, kwargs);
    }
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
