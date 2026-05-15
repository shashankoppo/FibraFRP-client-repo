/** @odoo-module **/

import { Component, xml, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const NODE_TYPES = {
    trigger: { label: 'Trigger', icon: 'fa-bolt', color: '#FF6B35' },
    send_text: { label: 'Send Text', icon: 'fa-comment', color: '#00A884' },
    send_template: { label: 'Template', icon: 'fa-magic', color: '#5B5EA6' },
    send_buttons: { label: 'Buttons', icon: 'fa-th-list', color: '#2196F3' },
    send_list: { label: 'List Menu', icon: 'fa-bars', color: '#00BCD4' },
    send_media: { label: 'Send Media', icon: 'fa-image', color: '#E91E63' },
    wait_reply: { label: 'Wait Reply', icon: 'fa-clock-o', color: '#FF9800' },
    condition: { label: 'Condition', icon: 'fa-code-fork', color: '#9C27B0' },
    assign_agent: { label: 'Assign Agent', icon: 'fa-user-plus', color: '#607D8B' },
    add_tag: { label: 'Add Tag', icon: 'fa-tag', color: '#795548' },
    delay: { label: 'Delay', icon: 'fa-hourglass-half', color: '#FF5722' },
    api_call: { label: 'API Call', icon: 'fa-cloud', color: '#3F51B5' },
    end: { label: 'End', icon: 'fa-stop-circle', color: '#F44336' },
};

/**
 * WhatsApp Visual Bot Flow Builder — OWL 2.0 Version
 * This replaces the legacy setInterval-based implementation with a robust Odoo 19 Field Widget.
 */
export class WhatsAppBotFlowBuilder extends Component {
    static template = xml`
        <div class="wa-flow-builder o_field_widget" t-ref="container">
            <!-- Palette sidebar -->
            <div class="wa-fb-palette">
                <div class="wa-fb-palette-header">
                    <i class="fa fa-puzzle-piece"></i> Node Palette
                </div>
                <div class="wa-fb-palette-items">
                    <t t-foreach="Object.keys(nodeTypes)" t-as="type" t-key="type">
                        <div class="wa-fb-palette-item" 
                             draggable="true" 
                             t-on-dragstart="(ev) => this.onDragStartPalette(ev, type)">
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

            <!-- Canvas area -->
            <div class="wa-fb-canvas-wrap" 
                 t-ref="canvasWrap"
                 t-on-dragover.prevent="" 
                 t-on-drop="onDropCanvas"
                 t-on-mousedown="onMouseDownCanvas"
                 t-on-click="onClickCanvas">
                
                <!-- SVG for connections -->
                <svg class="wa-fb-svg" t-ref="svg">
                    <defs>
                        <marker id="wa-fb-arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                            <polygon points="0 0, 10 3.5, 0 7" fill="#00A884"/>
                        </marker>
                    </defs>
                    <t t-foreach="state.connections" t-as="conn" t-key="conn.from + '-' + conn.to">
                        <t t-set="pathData" t-value="getConnPath(conn)"/>
                        <path t-att-d="pathData.path" class="wa-fb-connection" marker-end="url(#wa-fb-arrow)"/>
                        <circle t-att-cx="pathData.midX" t-att-cy="pathData.midY" r="8" class="wa-fb-conn-del" 
                                t-on-click.stop="() => this.deleteConnection(conn)"/>
                    </t>
                </svg>

                <!-- Nodes layer -->
                <div class="wa-fb-nodes-layer" t-attf-style="transform: translate({{state.offset.x}}px, {{state.offset.y}}px) scale({{state.zoom}})">
                    <t t-foreach="state.nodes" t-as="node" t-key="node.id">
                        <div class="wa-fb-node" 
                             t-att-class="{selected: state.selectedNode === node.id}"
                             t-att-data-id="node.id"
                             t-attf-style="left: {{node.x}}px; top: {{node.y}}px"
                             t-on-mousedown.stop="(ev) => this.onMouseDownNode(ev, node)">
                            <div class="wa-fb-node-header" t-attf-style="background: {{nodeTypes[node.type].color}}">
                                <i t-attf-class="fa {{nodeTypes[node.type].icon}}"></i>
                                <span class="wa-fb-node-label" t-esc="node.label" t-on-dblclick.stop="() => this.editNodeLabel(node)"/>
                                <button type="button" class="wa-fb-conn-btn" title="Connect" t-on-mousedown.stop="(ev) => this.startConnecting(ev, node)">
                                    <i class="fa fa-arrow-right"></i>
                                </button>
                            </div>
                            <div class="wa-fb-node-body">
                                <div class="wa-fb-node-type" t-esc="node.type.split('_').join(' ')"/>
                                <div class="wa-fb-node-config-hint">Click to configure</div>
                            </div>
                        </div>
                    </t>
                </div>

                <!-- Toolbar -->
                <div class="wa-fb-toolbar">
                    <button type="button" class="wa-fb-tb-btn" t-on-click="() => this.adjustZoom(0.1)" title="Zoom In"><i class="fa fa-search-plus"></i></button>
                    <button type="button" class="wa-fb-tb-btn" t-on-click="() => this.adjustZoom(-0.1)" title="Zoom Out"><i class="fa fa-search-minus"></i></button>
                    <button type="button" class="wa-fb-tb-btn" t-on-click="resetView" title="Reset"><i class="fa fa-compress"></i></button>
                    <button type="button" class="wa-fb-tb-btn text-danger" t-on-click="deleteSelected" title="Delete"><i class="fa fa-trash"></i></button>
                    <span class="wa-fb-tb-sep"></span>
                    <span class="wa-fb-tb-info"><i class="fa fa-info-circle"></i> <t t-esc="state.nodes.length"/> nodes</span>
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
            nextId: 1,
        });

        this.dragData = {
            node: null,
            offset: { x: 0, y: 0 },
            connectingFrom: null,
        };

        onMounted(() => {
            this.loadData();
            window.addEventListener('mousemove', this.onMouseMove.bind(this));
            window.addEventListener('mouseup', this.onMouseUp.bind(this));
        });

        onWillUnmount(() => {
            window.removeEventListener('mousemove', this.onMouseMove.bind(this));
            window.removeEventListener('mouseup', this.onMouseUp.bind(this));
        });
    }

    loadData() {
        try {
            const raw = this.props.record.data[this.props.name] || '{}';
            const data = JSON.parse(raw);
            if (data.nodes) {
                this.state.nodes = data.nodes;
                this.state.connections = data.connections || [];
                this.state.nextId = data.nextId || 1;
            }
        } catch (e) {
            console.error("Failed to load flow data", e);
        }
    }

    saveData() {
        const data = JSON.stringify({
            nodes: this.state.nodes,
            connections: this.state.connections,
            nextId: this.state.nextId,
        });
        this.props.record.update({ [this.props.name]: data });
    }

    onDragStartPalette(ev, type) {
        ev.dataTransfer.setData('nodeType', type);
    }

    onDropCanvas(ev) {
        const type = ev.dataTransfer.getData('nodeType');
        if (!type) return;

        const rect = this.canvasWrap.el.getBoundingClientRect();
        const x = (ev.clientX - rect.left - this.state.offset.x) / this.state.zoom;
        const y = (ev.clientY - rect.top - this.state.offset.y) / this.state.zoom;

        const newNode = {
            id: 'node_' + (this.state.nextId++),
            type: type,
            x: x - 50,
            y: y - 20,
            label: NODE_TYPES[type].label,
            config: {}
        };
        this.state.nodes.push(newNode);
        this.saveData();
    }

    onMouseDownNode(ev, node) {
        this.state.selectedNode = node.id;
        this.dragData.node = node;
        const rect = ev.currentTarget.getBoundingClientRect();
        this.dragData.offset = {
            x: ev.clientX - rect.left,
            y: ev.clientY - rect.top
        };
    }

    startConnecting(ev, node) {
        this.dragData.connectingFrom = node.id;
        this.canvasWrap.el.classList.add('wa-fb-connecting');
    }

    onMouseMove(ev) {
        if (this.dragData.node) {
            const rect = this.canvasWrap.el.getBoundingClientRect();
            this.dragData.node.x = (ev.clientX - rect.left - this.dragData.offset.x - this.state.offset.x) / this.state.zoom;
            this.dragData.node.y = (ev.clientY - rect.top - this.dragData.offset.y - this.state.offset.y) / this.state.zoom;
        }
    }

    onMouseUp(ev) {
        if (this.dragData.connectingFrom) {
            const target = ev.target.closest('.wa-fb-node');
            if (target && target.dataset.id !== this.dragData.connectingFrom) {
                const toId = target.dataset.id;
                if (!this.state.connections.find(c => c.from === this.dragData.connectingFrom && c.to === toId)) {
                    this.state.connections.push({ from: this.dragData.connectingFrom, to: toId });
                    this.saveData();
                }
            }
            this.dragData.connectingFrom = null;
            this.canvasWrap.el.classList.remove('wa-fb-connecting');
        }
        if (this.dragData.node) {
            this.dragData.node = null;
            this.saveData();
        }
    }

    editNodeLabel(node) {
        const newLabel = prompt('Node label:', node.label);
        if (newLabel) {
            node.label = newLabel;
            this.saveData();
        }
    }

    deleteSelected() {
        if (!this.state.selectedNode) return;
        this.state.nodes = this.state.nodes.filter(n => n.id !== this.state.selectedNode);
        this.state.connections = this.state.connections.filter(c => c.from !== this.state.selectedNode && c.to !== this.state.selectedNode);
        this.state.selectedNode = null;
        this.saveData();
    }

    deleteConnection(conn) {
        this.state.connections = this.state.connections.filter(c => c !== conn);
        this.saveData();
    }

    adjustZoom(delta) {
        this.state.zoom = Math.max(0.3, Math.min(2, this.state.zoom + delta));
    }

    resetView() {
        this.state.zoom = 1;
        this.state.offset = { x: 0, y: 0 };
    }

    getConnPath(conn) {
        const from = this.state.nodes.find(n => n.id === conn.from);
        const to = this.state.nodes.find(n => n.id === conn.to);
        if (!from || !to) return { path: "" };

        const x1 = (from.x + 100) * this.state.zoom + this.state.offset.x;
        const y1 = (from.y + 30) * this.state.zoom + this.state.offset.y;
        const x2 = (to.x + 100) * this.state.zoom + this.state.offset.x;
        const y2 = (to.y + 30) * this.state.zoom + this.state.offset.y;

        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        return {
            path: `M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`,
            midX, midY
        };
    }
}

WhatsAppBotFlowBuilder.props = { ...standardFieldProps };
registry.category("fields").add("wa_flow_builder", {
    component: WhatsAppBotFlowBuilder,
});
