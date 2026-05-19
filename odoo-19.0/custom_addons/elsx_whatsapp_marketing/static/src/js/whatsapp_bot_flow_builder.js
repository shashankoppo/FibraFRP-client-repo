/** @odoo-module **/

import { Component, xml, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const NODE_TYPES = {
    trigger: { label: "Trigger", icon: "fa-bolt", color: "#ff6b35" },
    message: { label: "Message", icon: "fa-comment", color: "#00a884" },
    action: { label: "Action", icon: "fa-play-circle", color: "#2563eb" },
    send_text: { label: "Send Text", icon: "fa-comment", color: "#00a884" },
    send_template: { label: "Template", icon: "fa-magic", color: "#5b5ea6" },
    send_buttons: { label: "Buttons", icon: "fa-th-list", color: "#2196f3" },
    send_list: { label: "List Menu", icon: "fa-bars", color: "#00bcd4" },
    send_media: { label: "Send Media", icon: "fa-image", color: "#e91e63" },
    wait_reply: { label: "Wait Reply", icon: "fa-clock-o", color: "#ff9800" },
    condition: { label: "Condition", icon: "fa-code-fork", color: "#9c27b0" },
    assign_agent: { label: "Assign Agent", icon: "fa-user-plus", color: "#607d8b" },
    add_tag: { label: "Add Tag", icon: "fa-tag", color: "#795548" },
    delay: { label: "Delay", icon: "fa-hourglass-half", color: "#ff5722" },
    api_call: { label: "API Call", icon: "fa-cloud", color: "#3f51b5" },
    end: { label: "End", icon: "fa-stop-circle", color: "#f44336" },
};

const CONFIG_HINTS = {
    send_text: "Configure text body",
    send_template: "Configure template id",
    send_buttons: "Configure text + branches",
    send_media: "Configure media id",
    condition: "Configure condition",
    wait_reply: "Configure response variable",
    assign_agent: "Configure user id",
    add_tag: "Configure tag id",
    delay: "Configure delay seconds",
    api_call: "Configure method/url/payload",
    trigger: "Configure trigger settings",
};

export class WhatsAppBotFlowBuilder extends Component {
    static template = xml`
        <div class="wa-flow-builder o_field_widget">
            <div class="wa-fb-palette">
                <div class="wa-fb-palette-header">
                    <i class="fa fa-puzzle-piece"></i>
                    <span>Node Palette</span>
                </div>
                <div class="wa-fb-palette-items">
                    <t t-foreach="Object.keys(nodeTypes)" t-as="type" t-key="type">
                        <div class="wa-fb-palette-item" draggable="true" t-on-dragstart="(ev) => this.onDragStartPalette(ev, type)">
                            <div class="wa-fb-pi-icon" t-attf-style="background: {{nodeTypes[type].color}}">
                                <i t-attf-class="fa {{nodeTypes[type].icon}}"></i>
                            </div>
                            <span t-esc="nodeTypes[type].label"/>
                        </div>
                    </t>
                </div>
                <div class="wa-fb-palette-footer">
                    <small>Drag nodes onto canvas</small>
                </div>
            </div>

            <div class="wa-fb-canvas-wrap"
                 t-ref="canvasWrap"
                 t-on-dragover.prevent=""
                 t-on-drop="onDropCanvas"
                 t-on-mousedown="onMouseDownCanvas"
                 t-on-click="onClickCanvas">
                <svg class="wa-fb-svg">
                    <defs>
                        <marker id="wa-fb-arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                            <polygon points="0 0, 10 3.5, 0 7" fill="#00a884"/>
                        </marker>
                    </defs>
                    <t t-foreach="state.connections" t-as="conn" t-key="conn.from + '-' + conn.to">
                        <t t-set="pathData" t-value="getConnPath(conn)"/>
                        <path t-att-d="pathData.path" class="wa-fb-connection" marker-end="url(#wa-fb-arrow)"/>
                        <circle t-att-cx="pathData.midX" t-att-cy="pathData.midY" r="8" class="wa-fb-conn-del"
                                t-on-click.stop="() => this.deleteConnection(conn)"/>
                    </t>
                </svg>

                <div class="wa-fb-nodes-layer" t-attf-style="transform: translate({{state.offset.x}}px, {{state.offset.y}}px) scale({{state.zoom}})">
                    <t t-foreach="state.nodes" t-as="node" t-key="node.id">
                        <div class="wa-fb-node"
                             t-att-class="{selected: state.selectedNode === node.id}"
                             t-att-data-id="node.id"
                             t-attf-style="left: {{node.x}}px; top: {{node.y}}px"
                             t-on-mousedown.stop="(ev) => this.onMouseDownNode(ev, node)">
                            <div class="wa-fb-node-header" t-attf-style="background: {{nodeTypes[node.type] ? nodeTypes[node.type].color : '#6b7280'}}">
                                <i t-attf-class="fa {{nodeTypes[node.type] ? nodeTypes[node.type].icon : 'fa-cube'}}"></i>
                                <span class="wa-fb-node-label" t-esc="node.label" t-on-dblclick.stop="() => this.editNodeLabel(node)"/>
                                <button type="button" class="wa-fb-conn-btn" title="Connect" t-on-mousedown.stop="(ev) => this.startConnecting(ev, node)">
                                    <i class="fa fa-arrow-right"></i>
                                </button>
                            </div>
                            <div class="wa-fb-node-body">
                                <div class="wa-fb-node-type" t-esc="node.type.split('_').join(' ')"/>
                                <div class="wa-fb-node-preview" t-esc="this.getNodePreview(node)"/>
                                <button type="button" class="wa-fb-node-config-btn" t-on-click.stop="() => this.configureNode(node)">
                                    Configure
                                </button>
                            </div>
                        </div>
                    </t>
                </div>

                <div class="wa-fb-toolbar">
                    <button type="button" class="wa-fb-tb-btn" t-on-click="() => this.adjustZoom(0.1)" title="Zoom In"><i class="fa fa-search-plus"></i></button>
                    <button type="button" class="wa-fb-tb-btn" t-on-click="() => this.adjustZoom(-0.1)" title="Zoom Out"><i class="fa fa-search-minus"></i></button>
                    <button type="button" class="wa-fb-tb-btn" t-on-click="resetView" title="Reset View"><i class="fa fa-compress"></i></button>
                    <button type="button" class="wa-fb-tb-btn" t-on-click="deleteSelected" title="Delete Node"><i class="fa fa-trash"></i></button>
                    <span class="wa-fb-tb-sep"></span>
                    <span class="wa-fb-tb-info"><i class="fa fa-info-circle"></i> <t t-esc="state.nodes.length"/> nodes</span>
                </div>
            </div>

            <!-- Configuration Drawer -->
            <div t-if="state.editingNode" class="wa-fb-drawer" t-att-class="{open: state.drawerOpen}">
                <div class="wa-fb-drawer-header">
                    <i t-attf-class="fa {{nodeTypes[state.editingNode.type].icon}}"></i>
                    <span t-esc="state.editingNode.label"/>
                    <button type="button" class="btn-close" t-on-click="closeDrawer"></button>
                </div>
                <div class="wa-fb-drawer-body">
                    <div class="mb-3">
                        <label class="form-label">Step Label</label>
                        <input type="text" class="form-control" t-model="state.editingNode.label" t-on-input="saveData"/>
                    </div>
                    
                    <hr/>

                    <t t-if="state.editingNode.type === 'send_text'">
                        <div class="mb-3">
                            <label class="form-label">Message Text</label>
                            <textarea class="form-control" rows="5" t-model="state.editingNode.config.text" t-on-input="saveData"></textarea>
                            <small class="text-muted">Use {{name}} for dynamic data</small>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'send_template'">
                        <div class="mb-3">
                            <label class="form-label">Template ID</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.template_id" t-on-input="saveData"/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'condition'">
                        <div class="mb-3">
                            <label class="form-label">Condition Type</label>
                            <select class="form-select" t-model="state.editingNode.config.condition_type" t-on-change="saveData">
                                <option value="keyword_match">Keyword Match</option>
                                <option value="response_contains">Response Contains</option>
                                <option value="json_path">JSON Path</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Match Value</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.condition_value" t-on-input="saveData"/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'wait_reply'">
                        <div class="mb-3">
                            <label class="form-label">Save response to variable</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.variable_name" t-on-input="saveData" placeholder="e.g. user_choice"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Timeout (seconds)</label>
                            <input type="number" class="form-control" t-model="state.editingNode.config.timeout" t-on-input="saveData"/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'trigger'">
                        <div class="mb-3">
                            <label class="form-label">Trigger Mode</label>
                            <select class="form-select" t-model="state.editingNode.config.trigger_type" t-on-change="saveData">
                                <option value="keyword">Keyword Match</option>
                                <option value="first_message">First Message</option>
                                <option value="manual">Manual Trigger</option>
                            </select>
                        </div>
                        <t t-if="state.editingNode.config.trigger_type === 'keyword'">
                            <div class="mb-3">
                                <label class="form-label">Keywords</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.keywords" t-on-input="saveData" placeholder="hello, hi, start"/>
                            </div>
                        </t>
                    </t>

                    <t t-if="state.editingNode.type === 'api_call'">
                        <div class="mb-3">
                            <label class="form-label">Method</label>
                            <select class="form-select" t-model="state.editingNode.config.http_method" t-on-change="saveData">
                                <option value="GET">GET</option>
                                <option value="POST">POST</option>
                                <option value="PUT">PUT</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">URL</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.http_url" t-on-input="saveData"/>
                        </div>
                    </t>
                </div>
                <div class="wa-fb-drawer-footer">
                    <button type="button" class="btn btn-primary w-100" t-on-click="closeDrawer">Done</button>
                </div>
            </div>
        </div>
    `;

    setup() {
        this.nodeTypes = NODE_TYPES;
        this.canvasWrap = useRef("canvasWrap");

        this.state = useState({
            nodes: [],
            connections: [],
            offset: { x: 0, y: 0 },
            zoom: 1,
            selectedNode: null,
            editingNode: null,
            drawerOpen: false,
            nextId: 1,
        });

        this.dragData = {
            node: null,
            nodeOffsetX: 0,
            nodeOffsetY: 0,
            panStartX: 0,
            panStartY: 0,
            panOriginX: 0,
            panOriginY: 0,
            panning: false,
            connectingFrom: null,
        };

        this._boundMouseMove = this.onMouseMove.bind(this);
        this._boundMouseUp = this.onMouseUp.bind(this);

        onMounted(() => {
            this.loadData();
            window.addEventListener("mousemove", this._boundMouseMove);
            window.addEventListener("mouseup", this._boundMouseUp);
        });

        onWillUnmount(() => {
            window.removeEventListener("mousemove", this._boundMouseMove);
            window.removeEventListener("mouseup", this._boundMouseUp);
        });
    }

    loadData() {
        try {
            const raw = this.props.record.data[this.props.name] || "{}";
            const data = JSON.parse(raw);
            if (Array.isArray(data.nodes)) {
                this.state.nodes = data.nodes.map((node) => ({
                    id: node.id,
                    type: node.type || "send_text",
                    label: node.label || "Step",
                    x: Number(node.x || 0),
                    y: Number(node.y || 0),
                    config: typeof node.config === "object" && node.config ? node.config : {},
                }));
            } else {
                this.state.nodes = [];
            }

            if (Array.isArray(data.connections)) {
                const nodeIds = new Set(this.state.nodes.map((n) => n.id));
                this.state.connections = data.connections.filter(
                    (c) => c && nodeIds.has(c.from) && nodeIds.has(c.to) && c.from !== c.to
                );
            } else {
                this.state.connections = [];
            }

            this.state.nextId = Number(data.nextId || this.state.nodes.length + 1) || 1;
        } catch (error) {
            this.state.nodes = [];
            this.state.connections = [];
            this.state.nextId = 1;
            // Non-fatal: invalid persisted JSON can happen after manual edits.
            console.warn("[WA Flow Builder] Invalid canvas data, resetting.", error);
        }
    }

    saveData() {
        const payload = JSON.stringify({
            nodes: this.state.nodes,
            connections: this.state.connections,
            nextId: this.state.nextId,
        });
        this.props.record.update({ [this.props.name]: payload });
    }

    getNodePreview(node) {
        if (node.type === "message") return node.config.message_text || node.config.text || node.config.message_mode || "Message node";
        if (node.type === "action") return node.config.action_kind || node.config.action_type || "Action node";
        if (node.type === "send_text") return node.config.text || "Empty message...";
        if (node.type === "send_template") return node.config.template_id || "No template...";
        if (node.type === "condition") return `${node.config.condition_type || "No condition"}: ${node.config.condition_value || ""}`;
        if (node.type === "trigger") return node.config.trigger_type || "keyword";
        return CONFIG_HINTS[node.type] || "Configure node";
    }

    onDragStartPalette(ev, type) {
        ev.dataTransfer.setData("nodeType", type);
    }

    onDropCanvas(ev) {
        const type = ev.dataTransfer.getData("nodeType");
        if (!type || !NODE_TYPES[type]) {
            return;
        }
        const point = this.toCanvasPoint(ev.clientX, ev.clientY);
        const node = {
            id: `node_${this.state.nextId++}`,
            type,
            x: point.x - 100,
            y: point.y - 25,
            label: NODE_TYPES[type].label,
            config: {},
        };
        this.state.nodes.push(node);
        this.state.selectedNode = node.id;
        this.saveData();
    }

    onMouseDownNode(ev, node) {
        this.state.selectedNode = node.id;
        this.dragData.node = node;
        const nodeEl = ev.currentTarget;
        const rect = nodeEl.getBoundingClientRect();
        this.dragData.nodeOffsetX = ev.clientX - rect.left;
        this.dragData.nodeOffsetY = ev.clientY - rect.top;
    }

    onMouseDownCanvas(ev) {
        if (ev.target.closest(".wa-fb-node")) {
            return;
        }
        if (ev.button !== 0 && ev.button !== 1) {
            return;
        }
        this.dragData.panning = true;
        this.dragData.panStartX = ev.clientX;
        this.dragData.panStartY = ev.clientY;
        this.dragData.panOriginX = this.state.offset.x;
        this.dragData.panOriginY = this.state.offset.y;
    }

    onClickCanvas(ev) {
        if (!ev.target.closest(".wa-fb-node")) {
            this.state.selectedNode = null;
        }
    }

    startConnecting(ev, node) {
        this.dragData.connectingFrom = node.id;
        if (this.canvasWrap.el) {
            this.canvasWrap.el.classList.add("wa-fb-connecting");
        }
    }

    onMouseMove(ev) {
        if (this.dragData.node) {
            const point = this.toCanvasPoint(ev.clientX, ev.clientY);
            this.dragData.node.x = point.x - this.dragData.nodeOffsetX / this.state.zoom;
            this.dragData.node.y = point.y - this.dragData.nodeOffsetY / this.state.zoom;
            return;
        }

        if (this.dragData.panning) {
            this.state.offset.x = this.dragData.panOriginX + (ev.clientX - this.dragData.panStartX);
            this.state.offset.y = this.dragData.panOriginY + (ev.clientY - this.dragData.panStartY);
        }
    }

    onMouseUp(ev) {
        if (this.dragData.connectingFrom) {
            const target = ev.target.closest(".wa-fb-node");
            if (target && target.dataset.id && target.dataset.id !== this.dragData.connectingFrom) {
                const exists = this.state.connections.some(
                    (connection) => connection.from === this.dragData.connectingFrom && connection.to === target.dataset.id
                );
                if (!exists) {
                    this.state.connections.push({
                        from: this.dragData.connectingFrom,
                        to: target.dataset.id,
                    });
                    this.saveData();
                }
            }
            this.dragData.connectingFrom = null;
            if (this.canvasWrap.el) {
                this.canvasWrap.el.classList.remove("wa-fb-connecting");
            }
        }

        if (this.dragData.node) {
            this.dragData.node = null;
            this.saveData();
        }

        if (this.dragData.panning) {
            this.dragData.panning = false;
        }
    }

    toCanvasPoint(clientX, clientY) {
        const rect = this.canvasWrap.el.getBoundingClientRect();
        return {
            x: (clientX - rect.left - this.state.offset.x) / this.state.zoom,
            y: (clientY - rect.top - this.state.offset.y) / this.state.zoom,
        };
    }

    editNodeLabel(node) {
        this.configureNode(node);
    }

    configureNode(node) {
        this.state.editingNode = node;
        // Ensure config is reactive and has defaults
        if (!node.config) node.config = {};
        
        // Slight delay to trigger CSS transition
        setTimeout(() => {
            this.state.drawerOpen = true;
        }, 10);
    }

    closeDrawer() {
        this.state.drawerOpen = false;
        setTimeout(() => {
            this.state.editingNode = null;
        }, 300);
        this.saveData();
    }

    deleteSelected() {
        const nodeId = this.state.selectedNode;
        if (!nodeId) {
            return;
        }
        this.state.nodes = this.state.nodes.filter((node) => node.id !== nodeId);
        this.state.connections = this.state.connections.filter(
            (connection) => connection.from !== nodeId && connection.to !== nodeId
        );
        this.state.selectedNode = null;
        this.saveData();
    }

    deleteConnection(conn) {
        this.state.connections = this.state.connections.filter(
            (connection) => !(connection.from === conn.from && connection.to === conn.to)
        );
        this.saveData();
    }

    adjustZoom(delta) {
        this.state.zoom = Math.max(0.3, Math.min(2, this.state.zoom + delta));
    }

    resetView() {
        this.state.zoom = 1;
        this.state.offset.x = 0;
        this.state.offset.y = 0;
    }

    getConnPath(conn) {
        const from = this.state.nodes.find((node) => node.id === conn.from);
        const to = this.state.nodes.find((node) => node.id === conn.to);
        if (!from || !to) {
            return { path: "", midX: 0, midY: 0 };
        }

        const x1 = (from.x + 200) * this.state.zoom + this.state.offset.x;
        const y1 = (from.y + 25) * this.state.zoom + this.state.offset.y;
        const x2 = to.x * this.state.zoom + this.state.offset.x;
        const y2 = (to.y + 25) * this.state.zoom + this.state.offset.y;
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;

        return {
            path: `M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`,
            midX,
            midY,
        };
    }
}

WhatsAppBotFlowBuilder.props = { ...standardFieldProps };

registry.category("fields").add("wa_flow_builder", {
    component: WhatsAppBotFlowBuilder,
});
