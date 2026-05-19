/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const GRID_SIZE = 24;
const NODE_WIDTH = 244;
const NODE_HEIGHT = 104;

const PALETTE_ITEMS = [
    {
        key: "text",
        type: "message",
        subtype: "text",
        label: "Text",
        description: "Send a plain WhatsApp message",
        icon: "fa-commenting-o",
        color: "#00a884",
        defaults: { message_mode: "text", message_text: "Hi {{name}}, how can we help today?" },
    },
    {
        key: "template",
        type: "message",
        subtype: "template",
        label: "Template",
        description: "Send an approved Meta template",
        icon: "fa-magic",
        color: "#4f46e5",
        defaults: { message_mode: "template", template_id: false },
    },
    {
        key: "condition",
        type: "condition",
        subtype: "if_else",
        label: "Condition",
        description: "Route by keyword or saved response",
        icon: "fa-code-fork",
        color: "#a855f7",
        defaults: { condition_type: "keyword_match", condition_value: "" },
    },
    {
        key: "assign_agent",
        type: "action",
        subtype: "assign_agent",
        label: "Assign Agent",
        description: "Transfer the chat to a user",
        icon: "fa-user-plus",
        color: "#0f766e",
        defaults: { action_kind: "assign_agent", assign_user_id: false },
    },
    {
        key: "add_label",
        type: "action",
        subtype: "add_label",
        label: "Add Label",
        description: "Apply a CRM/contact label",
        icon: "fa-tag",
        color: "#b45309",
        defaults: { action_kind: "add_label", assign_tag_id: false },
    },
    {
        key: "wait_reply",
        type: "action",
        subtype: "wait_reply",
        label: "Wait Reply",
        description: "Pause until the customer replies",
        icon: "fa-clock-o",
        color: "#f97316",
        defaults: { action_kind: "wait_reply", save_response: true, response_variable: "last_reply" },
    },
    {
        key: "end",
        type: "action",
        subtype: "end",
        label: "End",
        description: "Finish this automation path",
        icon: "fa-stop-circle",
        color: "#dc2626",
        defaults: { action_kind: "end" },
    },
];

const NODE_META = {
    trigger: { label: "Trigger", icon: "fa-bolt", color: "#f97316" },
    message: { label: "Message", icon: "fa-comment", color: "#00a884" },
    condition: { label: "Condition", icon: "fa-code-fork", color: "#a855f7" },
    action: { label: "Action", icon: "fa-play-circle", color: "#2563eb" },
};

function snap(value) {
    return Math.round(value / GRID_SIZE) * GRID_SIZE;
}

function safeNumber(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
}

export class WhatsAppBotFlowAction extends Component {
    static template = xml`
        <div class="wa-flow-action">
            <aside class="wa-flow-action-sidebar">
                <div class="wa-flow-brand">
                    <div class="wa-flow-brand-icon"><i class="fa fa-sitemap"/></div>
                    <div>
                        <div class="wa-flow-brand-title">Visual Flow Builder</div>
                        <div class="wa-flow-brand-subtitle" t-esc="state.flowName || 'WhatsApp automation'"/>
                    </div>
                </div>

                <button type="button" class="wa-flow-trigger-card" t-on-click="addTriggerNode">
                    <div class="wa-flow-trigger-icon"><i class="fa fa-bolt"/></div>
                    <div>
                        <div class="wa-flow-trigger-title">Keyword/Event Trigger</div>
                        <div class="wa-flow-trigger-subtitle">Start point for this journey</div>
                    </div>
                </button>

                <div class="wa-flow-palette-title">Drag Components</div>
                <div class="wa-flow-palette-list">
                    <t t-foreach="paletteItems" t-as="item" t-key="item.key">
                        <div class="wa-flow-palette-card"
                             draggable="true"
                             t-on-dragstart="(ev) => this.onPaletteDragStart(ev, item.key)"
                             t-on-click="() => this.addPaletteNode(item.key)">
                            <div class="wa-flow-palette-icon" t-att-style="'background:' + item.color">
                                <i t-att-class="'fa ' + item.icon"/>
                            </div>
                            <div class="wa-flow-palette-copy">
                                <div class="wa-flow-palette-label" t-esc="item.label"/>
                                <div class="wa-flow-palette-description" t-esc="item.description"/>
                            </div>
                        </div>
                    </t>
                </div>
            </aside>

            <main class="wa-flow-workspace">
                <header class="wa-flow-topbar">
                    <div>
                        <h2 t-esc="state.flowName || 'Flow Builder'"/>
                        <p>
                            <t t-esc="state.nodes.length"/> nodes,
                            <t t-esc="state.edges.length"/> connections
                        </p>
                    </div>
                    <div class="wa-flow-topbar-actions">
                        <button type="button" class="btn btn-light" t-on-click="resetView" title="Reset view">
                            <i class="fa fa-compress me-1"/> Reset
                        </button>
                        <button type="button" class="btn btn-outline-secondary" t-on-click="openFlowForm" title="Open form">
                            <i class="fa fa-external-link me-1"/> Form
                        </button>
                        <button type="button" class="btn btn-primary wa-flow-save-btn" t-att-disabled="state.saving" t-on-click="saveFlow">
                            <i t-att-class="'fa ' + (state.saving ? 'fa-spinner fa-spin' : 'fa-save') + ' me-1'"/>
                            <t t-esc="state.saving ? 'Saving' : 'Save Flow'"/>
                        </button>
                    </div>
                </header>

                <section class="wa-flow-body">
                    <div class="wa-flow-canvas"
                         t-ref="canvas"
                         t-on-dragover.prevent="noop"
                         t-on-drop="onCanvasDrop"
                         t-on-wheel="onWheel"
                         t-on-mousedown="onCanvasMouseDown"
                         t-on-click="onCanvasClick">
                        <t t-if="state.loading">
                            <div class="wa-flow-loading">
                                <i class="fa fa-spinner fa-spin"/>
                                <span>Loading flow graph</span>
                            </div>
                        </t>

                        <svg class="wa-flow-svg">
                            <defs>
                                <marker id="wa-flow-arrow" markerWidth="12" markerHeight="8" refX="11" refY="4" orient="auto">
                                    <polygon points="0 0, 12 4, 0 8" fill="#00a884"/>
                                </marker>
                            </defs>
                            <t t-foreach="state.edges" t-as="edge" t-key="edge.id">
                                <t t-set="edgePath" t-value="getEdgePath(edge)"/>
                                <path t-att-d="edgePath.path" class="wa-flow-edge-path" marker-end="url(#wa-flow-arrow)"/>
                                <circle t-if="edgePath.midX"
                                        class="wa-flow-edge-delete"
                                        t-att-cx="edgePath.midX"
                                        t-att-cy="edgePath.midY"
                                        r="9"
                                        t-on-click.stop="() => this.deleteEdge(edge.id)"/>
                                <text t-if="edge.label" t-att-x="edgePath.midX + 18" t-att-y="edgePath.midY - 8" class="wa-flow-edge-label">
                                    <t t-esc="edge.label"/>
                                </text>
                            </t>
                            <path t-if="state.draftEdge" t-att-d="draftEdgePath()" class="wa-flow-edge-path wa-flow-edge-draft"/>
                        </svg>

                        <div class="wa-flow-node-layer" t-att-style="nodeLayerStyle()">
                            <t t-foreach="state.nodes" t-as="node" t-key="node.id">
                                <div t-att-class="nodeClass(node)"
                                     t-att-data-node-id="node.id"
                                     t-att-style="'left:' + node.x + 'px; top:' + node.y + 'px'"
                                     t-on-mousedown.stop="(ev) => this.onNodeMouseDown(ev, node)"
                                     t-on-dblclick.stop="() => this.selectNode(node.id)">
                                    <div class="wa-flow-node-head" t-att-style="'border-color:' + nodeColor(node)">
                                        <div class="wa-flow-node-icon" t-att-style="'background:' + nodeColor(node)">
                                            <i t-att-class="'fa ' + nodeIcon(node)"/>
                                        </div>
                                        <div class="wa-flow-node-title">
                                            <div t-esc="node.label"/>
                                            <small t-esc="nodeSubtitle(node)"/>
                                        </div>
                                        <button type="button" class="wa-flow-node-connect"
                                                t-on-mousedown.stop="(ev) => this.startEdge(ev, node)"
                                                title="Connect">
                                            <i class="fa fa-arrow-right"/>
                                        </button>
                                    </div>
                                    <div class="wa-flow-node-preview" t-esc="nodePreview(node)"/>
                                </div>
                            </t>
                        </div>

                        <div class="wa-flow-zoom">
                            <button type="button" title="Zoom out" t-on-click="() => this.zoomBy(-0.1)"><i class="fa fa-search-minus"/></button>
                            <span><t t-esc="Math.round(state.viewport.zoom * 100)"/>%</span>
                            <button type="button" title="Zoom in" t-on-click="() => this.zoomBy(0.1)"><i class="fa fa-search-plus"/></button>
                        </div>
                    </div>

                    <aside class="wa-flow-inspector">
                        <t t-if="!selectedNode">
                            <div class="wa-flow-empty-inspector">
                                <i class="fa fa-mouse-pointer"/>
                                <h3>Select a node</h3>
                                <p>Configure labels, messages, conditions, and actions from here.</p>
                            </div>
                        </t>
                        <t t-if="selectedNode">
                            <div class="wa-flow-inspector-header">
                                <div class="wa-flow-inspector-icon" t-att-style="'background:' + nodeColor(selectedNode)">
                                    <i t-att-class="'fa ' + nodeIcon(selectedNode)"/>
                                </div>
                                <div>
                                    <h3 t-esc="selectedNode.label"/>
                                    <p t-esc="nodeSubtitle(selectedNode)"/>
                                </div>
                            </div>

                            <label class="wa-flow-field">
                                <span>Label</span>
                                <input type="text" t-att-value="selectedNode.label" t-on-input="(ev) => this.updateNode('label', ev.target.value)"/>
                            </label>

                            <t t-if="selectedNode.type === 'trigger'">
                                <label class="wa-flow-field">
                                    <span>Trigger Type</span>
                                    <select t-att-value="selectedNode.config.trigger_type || 'keyword'" t-on-change="(ev) => this.updateConfig('trigger_type', ev.target.value)">
                                        <option value="keyword">Keyword Match</option>
                                        <option value="first_message">First Message</option>
                                        <option value="manual">Manual Trigger</option>
                                        <option value="schedule">Scheduled</option>
                                        <option value="webhook">Webhook Event</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.trigger_type || 'keyword') === 'keyword'">
                                    <span>Keywords</span>
                                    <input type="text" placeholder="hello, support, quote" t-att-value="selectedNode.config.keywords || ''" t-on-input="(ev) => this.updateConfig('keywords', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="selectedNode.config.trigger_type === 'webhook'">
                                    <span>Webhook Event</span>
                                    <input type="text" placeholder="order.created" t-att-value="selectedNode.config.webhook_event || ''" t-on-input="(ev) => this.updateConfig('webhook_event', ev.target.value)"/>
                                </label>
                            </t>

                            <t t-if="selectedNode.type === 'message'">
                                <label class="wa-flow-field">
                                    <span>Message Type</span>
                                    <select t-att-value="selectedNode.config.message_mode || selectedNode.subtype || 'text'" t-on-change="(ev) => this.updateMessageMode(ev.target.value)">
                                        <option value="text">Text</option>
                                        <option value="template">Template</option>
                                        <option value="buttons">Buttons</option>
                                        <option value="media">Media</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype || 'text') !== 'template'">
                                    <span>Message Text</span>
                                    <textarea rows="7" t-att-value="selectedNode.config.message_text || selectedNode.config.text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'template'">
                                    <span>Template ID</span>
                                    <input type="number" placeholder="Odoo template record ID" t-att-value="selectedNode.config.template_id || ''" t-on-input="(ev) => this.updateConfig('template_id', ev.target.value)"/>
                                </label>
                            </t>

                            <t t-if="selectedNode.type === 'condition'">
                                <label class="wa-flow-field">
                                    <span>Condition Type</span>
                                    <select t-att-value="selectedNode.config.condition_type || 'keyword_match'" t-on-change="(ev) => this.updateConfig('condition_type', ev.target.value)">
                                        <option value="keyword_match">Keyword Match</option>
                                        <option value="response_contains">Response Contains</option>
                                        <option value="json_path">Saved Variable Exists</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field">
                                    <span>Match Value</span>
                                    <input type="text" t-att-value="selectedNode.config.condition_value || ''" t-on-input="(ev) => this.updateConfig('condition_value', ev.target.value)"/>
                                </label>
                                <div class="wa-flow-hint">The first outgoing connection is treated as true, the second as false.</div>
                            </t>

                            <t t-if="selectedNode.type === 'action'">
                                <label class="wa-flow-field">
                                    <span>Action</span>
                                    <select t-att-value="selectedNode.config.action_kind || selectedNode.subtype || 'assign_agent'" t-on-change="(ev) => this.updateActionKind(ev.target.value)">
                                        <option value="assign_agent">Assign Agent</option>
                                        <option value="add_label">Add Label</option>
                                        <option value="wait_reply">Wait Reply</option>
                                        <option value="api_call">API Call</option>
                                        <option value="delay">Delay</option>
                                        <option value="end">End Flow</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'assign_agent'">
                                    <span>User ID</span>
                                    <input type="number" placeholder="res.users ID" t-att-value="selectedNode.config.assign_user_id || ''" t-on-input="(ev) => this.updateConfig('assign_user_id', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'add_label'">
                                    <span>Label ID</span>
                                    <input type="number" placeholder="res.partner.category ID" t-att-value="selectedNode.config.assign_tag_id || ''" t-on-input="(ev) => this.updateConfig('assign_tag_id', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'wait_reply'">
                                    <span>Response Variable</span>
                                    <input type="text" t-att-value="selectedNode.config.response_variable || selectedNode.config.variable_name || 'last_reply'" t-on-input="(ev) => this.updateConfig('response_variable', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'delay'">
                                    <span>Delay Seconds</span>
                                    <input type="number" t-att-value="selectedNode.config.delay_seconds || 0" t-on-input="(ev) => this.updateConfig('delay_seconds', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'api_call'">
                                    <span>Webhook URL</span>
                                    <input type="url" t-att-value="selectedNode.config.http_url || ''" t-on-input="(ev) => this.updateConfig('http_url', ev.target.value)"/>
                                </label>
                            </t>

                            <div class="wa-flow-inspector-actions">
                                <button type="button" class="btn btn-outline-danger" t-on-click="deleteSelectedNode">
                                    <i class="fa fa-trash me-1"/> Delete Node
                                </button>
                            </div>
                        </t>
                    </aside>
                </section>
            </main>
        </div>
    `;

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.canvas = useRef("canvas");
        this.paletteItems = PALETTE_ITEMS;

        const params = this.props.action?.params || {};
        const context = this.props.action?.context || {};
        this.flowId = params.flow_id || context.active_id || context.default_flow_id;

        this.state = useState({
            loading: true,
            saving: false,
            flowName: params.flow_name || "",
            nodes: [],
            edges: [],
            nextId: 1,
            selectedNodeId: null,
            viewport: { x: 32, y: 32, zoom: 1 },
            draftEdge: null,
        });

        this.drag = null;
        this._onMouseMove = this.onWindowMouseMove.bind(this);
        this._onMouseUp = this.onWindowMouseUp.bind(this);

        onWillStart(async () => {
            await this.loadFlow();
        });

        onMounted(() => {
            window.addEventListener("mousemove", this._onMouseMove);
            window.addEventListener("mouseup", this._onMouseUp);
        });

        onWillUnmount(() => {
            window.removeEventListener("mousemove", this._onMouseMove);
            window.removeEventListener("mouseup", this._onMouseUp);
        });
    }

    get selectedNode() {
        return this.state.nodes.find((node) => node.id === this.state.selectedNodeId) || null;
    }

    noop() {}

    async loadFlow() {
        if (!this.flowId) {
            this.state.loading = false;
            this.notification.add("Open the builder from a saved Bot Flow record.", { type: "warning" });
            return;
        }
        this.state.loading = true;
        try {
            const graph = await this.orm.call("whatsapp.bot.flow", "get_visual_graph", [[this.flowId]]);
            this.applyGraph(graph || {});
        } catch (error) {
            console.error("[WA Flow Builder] Load failed", error);
            this.notification.add("Could not load the visual flow graph.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    applyGraph(graph) {
        this.state.flowName = graph.flow?.name || this.state.flowName;
        this.state.nodes = (graph.nodes || []).map((node) => ({
            id: String(node.id),
            type: node.type || "message",
            subtype: node.subtype || node.legacy_type || node.type || "text",
            legacy_type: node.legacy_type || node.type || "message",
            label: node.label || "Node",
            x: safeNumber(node.x),
            y: safeNumber(node.y),
            config: { ...(node.config || {}) },
        }));

        const nodeIds = new Set(this.state.nodes.map((node) => node.id));
        const rawEdges = Array.isArray(graph.edges) ? graph.edges : (graph.connections || []);
        this.state.edges = rawEdges
            .map((edge, index) => ({
                id: String(edge.id || `edge_${index + 1}`),
                from: String(edge.from || edge.source || ""),
                to: String(edge.to || edge.target || ""),
                label: edge.label || "",
                config: { ...(edge.config || {}) },
            }))
            .filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to) && edge.from !== edge.to);

        const viewport = graph.viewport || {};
        this.state.viewport = {
            x: safeNumber(viewport.x, 32),
            y: safeNumber(viewport.y, 32),
            zoom: Math.max(0.35, Math.min(1.8, safeNumber(viewport.zoom, 1))),
        };
        this.state.nextId = safeNumber(graph.nextId || graph.next_id, this.state.nodes.length + 1);
        this.state.selectedNodeId = this.state.nodes[0]?.id || null;
    }

    serializeGraph() {
        return {
            nodes: this.state.nodes.map((node) => ({
                id: node.id,
                type: node.type,
                subtype: node.subtype,
                legacy_type: node.legacy_type || node.type,
                label: node.label,
                x: node.x,
                y: node.y,
                config: { ...(node.config || {}) },
            })),
            edges: this.state.edges.map((edge) => ({
                id: edge.id,
                from: edge.from,
                to: edge.to,
                label: edge.label || "",
                config: { ...(edge.config || {}) },
            })),
            connections: this.state.edges.map((edge) => ({ from: edge.from, to: edge.to, label: edge.label || "" })),
            nextId: this.state.nextId,
            viewport: { ...this.state.viewport },
        };
    }

    async saveFlow() {
        if (!this.flowId || this.state.saving) return;
        this.state.saving = true;
        try {
            const graph = await this.orm.call("whatsapp.bot.flow", "save_visual_graph", [[this.flowId], this.serializeGraph()]);
            this.applyGraph(graph || {});
            this.notification.add("Flow saved and synchronized with bot steps.", { type: "success" });
        } catch (error) {
            console.error("[WA Flow Builder] Save failed", error);
            this.notification.add("Could not save the flow graph.", { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    openFlowForm() {
        if (!this.flowId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "whatsapp.bot.flow",
            res_id: this.flowId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onPaletteDragStart(ev, key) {
        ev.dataTransfer.setData("application/x-wa-flow-node", key);
        ev.dataTransfer.effectAllowed = "copy";
    }

    onCanvasDrop(ev) {
        const key = ev.dataTransfer.getData("application/x-wa-flow-node");
        const item = PALETTE_ITEMS.find((candidate) => candidate.key === key);
        if (!item) return;
        const point = this.toCanvasPoint(ev.clientX, ev.clientY);
        this.addNodeFromPalette(item, point.x - NODE_WIDTH / 2, point.y - NODE_HEIGHT / 2);
    }

    addPaletteNode(key) {
        const item = PALETTE_ITEMS.find((candidate) => candidate.key === key);
        if (!item) return;
        const offset = this.state.nodes.length * 28;
        this.addNodeFromPalette(item, 360 + offset, 180 + offset);
    }

    addTriggerNode() {
        if (this.state.nodes.some((node) => node.type === "trigger")) {
            const trigger = this.state.nodes.find((node) => node.type === "trigger");
            this.state.selectedNodeId = trigger.id;
            return;
        }
        const node = {
            id: `trigger_${this.state.nextId++}`,
            type: "trigger",
            subtype: "keyword",
            legacy_type: "trigger",
            label: "Keyword Trigger",
            x: 80,
            y: 180,
            config: { trigger_type: "keyword", keywords: "" },
        };
        this.state.nodes.unshift(node);
        this.state.selectedNodeId = node.id;
    }

    addNodeFromPalette(item, x, y) {
        const node = {
            id: `${item.key}_${this.state.nextId++}`,
            type: item.type,
            subtype: item.subtype,
            legacy_type: item.type,
            label: item.label,
            x: snap(x),
            y: snap(y),
            config: { ...item.defaults },
        };
        this.state.nodes.push(node);
        this.state.selectedNodeId = node.id;
    }

    onNodeMouseDown(ev, node) {
        this.state.selectedNodeId = node.id;
        const rect = ev.currentTarget.getBoundingClientRect();
        this.drag = {
            mode: "node",
            nodeId: node.id,
            dx: (ev.clientX - rect.left) / this.state.viewport.zoom,
            dy: (ev.clientY - rect.top) / this.state.viewport.zoom,
        };
    }

    onCanvasMouseDown(ev) {
        if (ev.button !== 0 || ev.target.closest(".wa-flow-node")) return;
        this.drag = {
            mode: "pan",
            startX: ev.clientX,
            startY: ev.clientY,
            originX: this.state.viewport.x,
            originY: this.state.viewport.y,
        };
    }

    onCanvasClick(ev) {
        if (!ev.target.closest(".wa-flow-node") && !ev.target.closest(".wa-flow-edge-delete")) {
            this.state.selectedNodeId = null;
        }
    }

    startEdge(ev, node) {
        const point = this.relativeCanvasPoint(ev.clientX, ev.clientY);
        this.drag = { mode: "edge", from: node.id };
        this.state.draftEdge = { from: node.id, x: point.x, y: point.y };
    }

    onWindowMouseMove(ev) {
        if (!this.drag) return;
        if (this.drag.mode === "node") {
            const node = this.state.nodes.find((candidate) => candidate.id === this.drag.nodeId);
            if (!node) return;
            const point = this.toCanvasPoint(ev.clientX, ev.clientY);
            node.x = snap(point.x - this.drag.dx);
            node.y = snap(point.y - this.drag.dy);
        } else if (this.drag.mode === "pan") {
            this.state.viewport.x = this.drag.originX + ev.clientX - this.drag.startX;
            this.state.viewport.y = this.drag.originY + ev.clientY - this.drag.startY;
        } else if (this.drag.mode === "edge") {
            const point = this.relativeCanvasPoint(ev.clientX, ev.clientY);
            this.state.draftEdge = { from: this.drag.from, x: point.x, y: point.y };
        }
    }

    onWindowMouseUp(ev) {
        if (this.drag?.mode === "edge") {
            const targetEl = ev.target.closest(".wa-flow-node");
            const targetId = targetEl?.dataset?.nodeId;
            if (targetId && targetId !== this.drag.from) {
                this.addEdge(this.drag.from, targetId);
            }
            this.state.draftEdge = null;
        }
        this.drag = null;
    }

    addEdge(from, to) {
        const exists = this.state.edges.some((edge) => edge.from === from && edge.to === to);
        if (exists) return;
        const source = this.state.nodes.find((node) => node.id === from);
        let label = "";
        if (source?.type === "condition") {
            const outgoingCount = this.state.edges.filter((edge) => edge.from === from).length;
            label = outgoingCount === 0 ? "true" : "false";
        }
        this.state.edges.push({
            id: `edge_${from}_${to}_${Date.now()}`,
            from,
            to,
            label,
            config: {},
        });
    }

    deleteEdge(edgeId) {
        this.state.edges = this.state.edges.filter((edge) => edge.id !== edgeId);
    }

    deleteSelectedNode() {
        const nodeId = this.state.selectedNodeId;
        if (!nodeId) return;
        this.state.nodes = this.state.nodes.filter((node) => node.id !== nodeId);
        this.state.edges = this.state.edges.filter((edge) => edge.from !== nodeId && edge.to !== nodeId);
        this.state.selectedNodeId = null;
    }

    selectNode(nodeId) {
        this.state.selectedNodeId = nodeId;
    }

    updateNode(field, value) {
        if (!this.selectedNode) return;
        this.selectedNode[field] = value;
    }

    updateConfig(field, value) {
        if (!this.selectedNode) return;
        this.selectedNode.config = { ...(this.selectedNode.config || {}), [field]: value };
    }

    updateMessageMode(mode) {
        if (!this.selectedNode) return;
        this.selectedNode.subtype = mode;
        this.selectedNode.config = {
            ...(this.selectedNode.config || {}),
            message_mode: mode,
        };
    }

    updateActionKind(kind) {
        if (!this.selectedNode) return;
        this.selectedNode.subtype = kind;
        this.selectedNode.config = {
            ...(this.selectedNode.config || {}),
            action_kind: kind,
        };
    }

    onWheel(ev) {
        if (!ev.ctrlKey && !ev.metaKey) return;
        ev.preventDefault();
        this.zoomBy(ev.deltaY > 0 ? -0.08 : 0.08);
    }

    zoomBy(delta) {
        this.state.viewport.zoom = Math.max(0.35, Math.min(1.8, this.state.viewport.zoom + delta));
    }

    resetView() {
        this.state.viewport = { x: 32, y: 32, zoom: 1 };
    }

    toCanvasPoint(clientX, clientY) {
        const point = this.relativeCanvasPoint(clientX, clientY);
        return {
            x: (point.x - this.state.viewport.x) / this.state.viewport.zoom,
            y: (point.y - this.state.viewport.y) / this.state.viewport.zoom,
        };
    }

    relativeCanvasPoint(clientX, clientY) {
        const rect = this.canvas.el.getBoundingClientRect();
        return {
            x: clientX - rect.left,
            y: clientY - rect.top,
        };
    }

    nodeLayerStyle() {
        const { x, y, zoom } = this.state.viewport;
        return `transform: translate(${x}px, ${y}px) scale(${zoom});`;
    }

    getEdgePath(edge) {
        const from = this.state.nodes.find((node) => node.id === edge.from);
        const to = this.state.nodes.find((node) => node.id === edge.to);
        if (!from || !to) return { path: "", midX: 0, midY: 0 };
        const { x, y, zoom } = this.state.viewport;
        const x1 = (from.x + NODE_WIDTH) * zoom + x;
        const y1 = (from.y + NODE_HEIGHT / 2) * zoom + y;
        const x2 = to.x * zoom + x;
        const y2 = (to.y + NODE_HEIGHT / 2) * zoom + y;
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        return {
            path: `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`,
            midX,
            midY,
        };
    }

    draftEdgePath() {
        if (!this.state.draftEdge) return "";
        const from = this.state.nodes.find((node) => node.id === this.state.draftEdge.from);
        if (!from) return "";
        const { x, y, zoom } = this.state.viewport;
        const x1 = (from.x + NODE_WIDTH) * zoom + x;
        const y1 = (from.y + NODE_HEIGHT / 2) * zoom + y;
        const x2 = this.state.draftEdge.x;
        const y2 = this.state.draftEdge.y;
        const midX = (x1 + x2) / 2;
        return `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
    }

    nodeClass(node) {
        const selected = node.id === this.state.selectedNodeId ? " is-selected" : "";
        return `wa-flow-node wa-flow-node-${node.type}${selected}`;
    }

    nodeMeta(node) {
        return NODE_META[node.type] || NODE_META.message;
    }

    nodeColor(node) {
        if (node.type === "message") {
            return PALETTE_ITEMS.find((item) => item.type === "message" && item.subtype === (node.config?.message_mode || node.subtype))?.color || NODE_META.message.color;
        }
        if (node.type === "action") {
            return PALETTE_ITEMS.find((item) => item.type === "action" && item.subtype === (node.config?.action_kind || node.subtype))?.color || NODE_META.action.color;
        }
        return this.nodeMeta(node).color;
    }

    nodeIcon(node) {
        if (node.type === "message") {
            return PALETTE_ITEMS.find((item) => item.type === "message" && item.subtype === (node.config?.message_mode || node.subtype))?.icon || NODE_META.message.icon;
        }
        if (node.type === "action") {
            return PALETTE_ITEMS.find((item) => item.type === "action" && item.subtype === (node.config?.action_kind || node.subtype))?.icon || NODE_META.action.icon;
        }
        return this.nodeMeta(node).icon;
    }

    nodeSubtitle(node) {
        if (node.type === "message") return `Message: ${node.config?.message_mode || node.subtype || "text"}`;
        if (node.type === "action") return `Action: ${node.config?.action_kind || node.subtype || "assign_agent"}`;
        if (node.type === "trigger") return `Trigger: ${node.config?.trigger_type || "keyword"}`;
        return "If / else branch";
    }

    nodePreview(node) {
        if (node.type === "trigger") {
            return node.config?.keywords || node.config?.trigger_type || "keyword";
        }
        if (node.type === "message") {
            if ((node.config?.message_mode || node.subtype) === "template") {
                return node.config?.template_id ? `Template #${node.config.template_id}` : "Select template";
            }
            return node.config?.message_text || node.config?.text || "Write a message";
        }
        if (node.type === "condition") {
            return `${node.config?.condition_type || "keyword_match"}: ${node.config?.condition_value || "set value"}`;
        }
        if (node.type === "action") {
            return node.config?.action_kind || node.subtype || "assign_agent";
        }
        return "";
    }
}

registry.category("actions").add("elsx_whatsapp_flow_builder", WhatsAppBotFlowAction);
