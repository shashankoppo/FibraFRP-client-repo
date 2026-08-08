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
        key: "buttons",
        type: "message",
        subtype: "buttons",
        label: "Buttons",
        description: "Interactive Quick Reply buttons",
        icon: "fa-list-ul",
        color: "#ec4899",
        defaults: { message_mode: "buttons", message_text: "Please select an option", button_header_text: "", button_footer_text: "", options: [] },
    },
    {
        key: "list",
        type: "message",
        subtype: "list",
        label: "List",
        description: "Interactive list menu with more options",
        icon: "fa-bars",
        color: "#0891b2",
        defaults: { message_mode: "list", message_text: "Please select an option", list_button_text: "Choose", list_section_title: "Options", button_header_text: "", button_footer_text: "", options: [] },
    },
    {
        key: "media",
        type: "message",
        subtype: "media",
        label: "Media",
        description: "Send an image, document or video",
        icon: "fa-file-image-o",
        color: "#06b6d4",
        defaults: { message_mode: "media", media_id: false, message_text: "" },
    },
    {
        key: "condition",
        type: "condition",
        subtype: "if_else",
        label: "Condition",
        description: "Route by keyword or saved response",
        icon: "fa-code-fork",
        color: "#a855f7",
        defaults: { condition_type: "keyword_match", condition_source: "last_reply", condition_operator: "contains", condition_value: "", condition_branches: [] },
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
        key: "assign_team",
        type: "action",
        subtype: "assign_team",
        label: "Assign Team",
        description: "Route to the least busy available team member",
        icon: "fa-users",
        color: "#0d9488",
        defaults: { action_kind: "assign_team", assign_team_member_ids: [] },
    },
    {
        key: "ask_question",
        type: "action",
        subtype: "ask_question",
        label: "Ask Question",
        description: "Collect and validate a customer answer",
        icon: "fa-question-circle",
        color: "#f59e0b",
        defaults: {
            action_kind: "ask_question",
            message_text: "Please share your requirement.",
            input_validation_type: "text",
            response_variable: "customer_answer",
            max_attempts: 2,
            timeout_minutes: 0,
            invalid_message: "Please send a valid answer so we can continue.",
        },
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
        key: "create_lead",
        type: "action",
        subtype: "create_lead",
        label: "Create Lead",
        description: "Create a CRM lead from the chat",
        icon: "fa-address-card-o",
        color: "#7c3aed",
        defaults: { action_kind: "create_lead", message_text: "" },
    },
    {
        key: "set_variable",
        type: "action",
        subtype: "set_variable",
        label: "Set Variable",
        description: "Store a value for later steps",
        icon: "fa-database",
        color: "#64748b",
        defaults: { action_kind: "set_variable", variable_name: "", variable_value: "" },
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
        key: "delay",
        type: "action",
        subtype: "delay",
        label: "Delay",
        description: "Wait a few seconds before next step",
        icon: "fa-hourglass-start",
        color: "#84cc16",
        defaults: { action_kind: "delay", delay_seconds: 5 },
    },
    {
        key: "api_call",
        type: "action",
        subtype: "api_call",
        label: "API Call",
        description: "Trigger an external Webhook",
        icon: "fa-exchange",
        color: "#3b82f6",
        defaults: { action_kind: "api_call", http_method: "POST", http_url: "", http_payload: "", http_headers: "", http_query_params: "", http_auth_type: "none", http_auth_token: "", http_username: "", http_password: "", response_variable: "", http_response_path: "" },
    },
    {
        key: "chat_status",
        type: "action",
        subtype: "chat_status",
        label: "Chat Status",
        description: "Resolve, snooze, reopen or archive the chat",
        icon: "fa-check-circle",
        color: "#16a34a",
        defaults: { action_kind: "chat_status", chat_status: "open" },
    },
    {
        key: "update_contact",
        type: "action",
        subtype: "update_contact",
        label: "Update Contact",
        description: "Save a value into contact attributes",
        icon: "fa-id-card",
        color: "#9333ea",
        defaults: { action_kind: "update_contact", contact_attribute_name: "", contact_attribute_value: "" },
    },
    {
        key: "send_cta_url",
        type: "action",
        subtype: "send_cta_url",
        label: "URL Button",
        description: "Send a WhatsApp one-tap URL button",
        icon: "fa-external-link",
        color: "#0ea5e9",
        defaults: {
            action_kind: "send_cta_url",
            message_text: "Open our catalogue here.",
            cta_button_text: "Open Catalogue",
            cta_button_url: "",
            button_header_text: "",
            button_footer_text: "",
        },
    },
    {
        key: "send_catalog",
        type: "action",
        subtype: "send_catalog",
        label: "Catalog / Product",
        description: "Send a WhatsApp shop, product card, or product list",
        icon: "fa-shopping-bag",
        color: "#ea580c",
        defaults: {
            action_kind: "send_catalog",
            catalog_message_type: "single_product",
            catalog_id: "",
            product_retailer_id: "",
            product_retailer_ids: "",
            thumbnail_product_retailer_id: "",
            catalog_section_title: "Products",
            button_header_text: "Products",
            button_footer_text: "",
            message_text: "Please review this product.",
        },
    },
    {
        key: "send_form_link",
        type: "action",
        subtype: "send_form_link",
        label: "Form Link",
        description: "Send a tokenized WhatsApp lead/support form",
        icon: "fa-wpforms",
        color: "#14b8a6",
        defaults: {
            action_kind: "send_form_link",
            form_id: false,
            message_text: "Please fill this short form so our team can help you faster: {{form_url}}",
        },
    },
    {
        key: "send_payment_link",
        type: "action",
        subtype: "send_payment_link",
        label: "Payment Link",
        description: "Send manual or ERP invoice payment link",
        icon: "fa-credit-card",
        color: "#22c55e",
        defaults: {
            action_kind: "send_payment_link",
            message_text: "Here is your payment link: {{payment_url}}",
        },
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

function recordId(value) {
    if (!value) return false;
    if (Array.isArray(value)) return value[0] || false;
    if (typeof value === "object") return value.id || value.resId || false;
    return value;
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
                            <t t-if="validationIssues.length">
                                <span class="wa-flow-issue-chip">
                                    <i class="fa fa-exclamation-triangle"/>
                                    <t t-esc="validationIssues.length"/> warnings
                                </span>
                            </t>
                        </p>
                    </div>
                    <div class="wa-flow-topbar-actions">
                        <button type="button" class="btn btn-light" t-on-click="resetView" title="Reset view">
                            <i class="fa fa-compress me-1"/> Reset
                        </button>
                        <button type="button" class="btn btn-light" t-on-click="autoLayout" title="Arrange nodes">
                            <i class="fa fa-sitemap me-1"/> Layout
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

                            <t t-if="selectedNodeIssues.length">
                                <div class="wa-flow-issue-panel">
                                    <div class="wa-flow-issue-title"><i class="fa fa-exclamation-circle"/> Needs attention</div>
                                    <t t-foreach="selectedNodeIssues" t-as="issue" t-key="issue">
                                        <div class="wa-flow-issue-line" t-esc="issue"/>
                                    </t>
                                </div>
                            </t>

                            <label class="wa-flow-field">
                                <span>Label <i class="fa fa-question-circle wa-flow-help" title="Canvas name for this step. This is also used as the generated ERP step name."></i></span>
                                <input type="text" t-att-value="selectedNode.label" t-on-input="(ev) => this.updateNode('label', ev.target.value)"/>
                            </label>

                            <t t-if="selectedNode.type === 'trigger'">
                                <label class="wa-flow-field">
                                    <span>Trigger Type <i class="fa fa-question-circle wa-flow-help" title="Controls when this flow starts: inbound keyword, first message, manual run, scheduled job, or webhook event."></i></span>
                                    <select t-att-value="selectedNode.config.trigger_type || 'keyword'" t-on-change="(ev) => this.updateConfig('trigger_type', ev.target.value)">
                                        <option value="keyword">Keyword Match</option>
                                        <option value="first_message">First Message</option>
                                        <option value="manual">Manual Trigger</option>
                                        <option value="schedule">Scheduled</option>
                                        <option value="webhook">Webhook Event</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.trigger_type || 'keyword') === 'keyword'">
                                    <span>Keywords <i class="fa fa-question-circle wa-flow-help" title="Comma-separated words or phrases that start the flow from a customer message."></i></span>
                                    <input type="text" placeholder="hello, support, quote" t-att-value="selectedNode.config.keywords || ''" t-on-input="(ev) => this.updateConfig('keywords', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="selectedNode.config.trigger_type === 'webhook'">
                                    <span>Webhook Event <i class="fa fa-question-circle wa-flow-help" title="Internal event name used by a custom integration to start this flow."></i></span>
                                    <input type="text" placeholder="order.created" t-att-value="selectedNode.config.webhook_event || ''" t-on-input="(ev) => this.updateConfig('webhook_event', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field" t-if="selectedNode.config.trigger_type === 'schedule'">
                                    <span>Cron Schedule Pattern <i class="fa fa-question-circle wa-flow-help" title="Cron-style expression for scheduled execution."></i></span>
                                    <input type="text" placeholder="*/5 * * * *" t-att-value="selectedNode.config.schedule_pattern || ''" t-on-input="(ev) => this.updateConfig('schedule_pattern', ev.target.value)"/>
                                </label>
                            </t>

                            <t t-if="selectedNode.type === 'message'">
                                <label class="wa-flow-field">
                                    <span>Message Type <i class="fa fa-question-circle wa-flow-help" title="Choose whether this step sends text, an approved template, quick replies, a list menu, or media."></i></span>
                                    <select t-att-value="selectedNode.config.message_mode || selectedNode.subtype || 'text'" t-on-change="(ev) => this.updateMessageMode(ev.target.value)">
                                        <option value="text">Text</option>
                                        <option value="template">Template</option>
                                        <option value="buttons">Buttons</option>
                                        <option value="list">List Menu</option>
                                        <option value="media">Media</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype || 'text') !== 'template'">
                                    <span>Message Text <i class="fa fa-question-circle wa-flow-help" title="Text sent to the customer. For button messages this is the prompt before the buttons."></i></span>
                                    <textarea rows="7" t-att-value="selectedNode.config.message_text || selectedNode.config.text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                </label>
                                <div class="wa-flow-hint" t-if="(selectedNode.config.message_mode || selectedNode.subtype || 'text') !== 'template'">
                                    Placeholders: &#123;&#123;name&#125;&#125;, &#123;&#123;phone&#125;&#125;, &#123;&#123;email&#125;&#125;, &#123;&#123;company&#125;&#125;, &#123;&#123;last_reply&#125;&#125;. Wait Reply and Set Variable steps add more named placeholders.
                                </div>
                                <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'template'">
                                    <span>Template <i class="fa fa-question-circle wa-flow-help" title="Approved WhatsApp template to send from this step."></i></span>
                                    <select t-att-value="selectedNode.config.template_id || ''" t-on-change="(ev) => this.updateConfig('template_id', ev.target.value)">
                                        <option value="">Select a template...</option>
                                        <t t-foreach="state.templates" t-as="tpl" t-key="tpl.id">
                                            <option t-att-value="tpl.id" t-esc="tpl.name"/>
                                        </t>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'media'">
                                    <span>Media File <i class="fa fa-question-circle wa-flow-help" title="Media Library item sent by this step. Add captions in Message Text."></i></span>
                                    <select t-att-value="selectedNode.config.media_id || ''" t-on-change="(ev) => this.updateConfig('media_id', ev.target.value)">
                                        <option value="">Select a media file...</option>
                                        <t t-foreach="state.media" t-as="m" t-key="m.id">
                                            <option t-att-value="m.id" t-esc="m.name"/>
                                        </t>
                                    </select>
                                </label>
                                <t t-if="['buttons', 'list'].includes(selectedNode.config.message_mode || selectedNode.subtype || 'text')">
                                    <label class="wa-flow-field">
                                        <span>Header Text <i class="fa fa-question-circle wa-flow-help" title="Optional short header shown above the interactive message."></i></span>
                                        <input type="text" t-att-value="selectedNode.config.button_header_text || ''" t-on-input="(ev) => this.updateConfig('button_header_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Footer Text <i class="fa fa-question-circle wa-flow-help" title="Optional footer shown below the interactive message."></i></span>
                                        <input type="text" t-att-value="selectedNode.config.button_footer_text || ''" t-on-input="(ev) => this.updateConfig('button_footer_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'list'">
                                        <span>List Button Text <i class="fa fa-question-circle wa-flow-help" title="Text on the button that opens the list rows."></i></span>
                                        <input type="text" placeholder="Choose" t-att-value="selectedNode.config.list_button_text || 'Choose'" t-on-input="(ev) => this.updateConfig('list_button_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'list'">
                                        <span>Section Title <i class="fa fa-question-circle wa-flow-help" title="Title that groups the list rows."></i></span>
                                        <input type="text" placeholder="Options" t-att-value="selectedNode.config.list_section_title || 'Options'" t-on-input="(ev) => this.updateConfig('list_section_title', ev.target.value)"/>
                                    </label>
                                    <div class="wa-flow-hint">Configure options here or connect this node to next steps. Quick Replies allow 3 options; List Menus allow 10 rows.</div>
                                    <div class="wa-flow-palette-title mt-3">Options</div>
                                    <t t-foreach="interactiveOptions(selectedNode)" t-as="opt" t-key="opt._key">
                                        <div class="wa-flow-option-editor">
                                            <label class="wa-flow-field">
                                                <span>Text</span>
                                                <input type="text" t-att-value="opt.title || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'title', ev.target.value)"/>
                                            </label>
                                            <label class="wa-flow-field">
                                                <span>Payload ID</span>
                                                <input type="text" t-att-value="opt.id || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'id', ev.target.value)"/>
                                            </label>
                                            <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'list'">
                                                <span>Description</span>
                                                <input type="text" t-att-value="opt.description || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'description', ev.target.value)"/>
                                            </label>
                                            <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'buttons'">
                                                <span>Button Action <i class="fa fa-question-circle wa-flow-help" title="Reply waits for a customer tap. URL/Product sends one special WhatsApp interactive message and then follows the selected route."></i></span>
                                                <select t-att-value="opt.button_action || 'reply'" t-on-change="(ev) => this.updateInteractiveOption(opt._index, 'button_action', ev.target.value)">
                                                    <option value="reply">Reply / Route</option>
                                                    <option value="url">Open URL</option>
                                                    <option value="catalog_product">Send Product Card</option>
                                                </select>
                                            </label>
                                            <label class="wa-flow-field" t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'buttons' &amp;&amp; opt.button_action === 'url'">
                                                <span>URL</span>
                                                <input type="url" placeholder="https://..." t-att-value="opt.url || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'url', ev.target.value)"/>
                                            </label>
                                            <div t-if="(selectedNode.config.message_mode || selectedNode.subtype) === 'buttons' &amp;&amp; opt.button_action === 'catalog_product'">
                                                <label class="wa-flow-field">
                                                    <span>Catalog ID</span>
                                                    <input type="text" placeholder="Optional if account default exists" t-att-value="opt.catalog_id || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'catalog_id', ev.target.value)"/>
                                                </label>
                                                <label class="wa-flow-field">
                                                    <span>Product Retailer ID</span>
                                                    <input type="text" placeholder="SKU/content ID from Meta catalog" t-att-value="opt.product_retailer_id || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'product_retailer_id', ev.target.value)"/>
                                                </label>
                                            </div>
                                            <label class="wa-flow-field">
                                                <span>Go To Step</span>
                                                <select t-att-value="opt.next_node_id || ''" t-on-change="(ev) => this.updateInteractiveOption(opt._index, 'next_node_id', ev.target.value)">
                                                    <option value="">No route</option>
                                                    <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                        <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                                    </t>
                                                </select>
                                            </label>
                                            <button type="button" class="btn btn-outline-danger btn-sm w-100" t-on-click="() => this.removeInteractiveOption(opt._index)">
                                                <i class="fa fa-trash me-1"/> Remove Option
                                            </button>
                                        </div>
                                    </t>
                                    <button type="button" class="btn btn-outline-secondary btn-sm w-100" t-on-click="addInteractiveOption">
                                        <i class="fa fa-plus me-1"/> Add Option
                                    </button>
                                    <label class="wa-flow-field mt-3">
                                        <span>Fallback Route <i class="fa fa-question-circle wa-flow-help" title="Where the flow should go if an unmatched button/list payload arrives."></i></span>
                                        <select t-att-value="selectedNode.config.fallback_node_id || ''" t-on-change="(ev) => this.updateConfig('fallback_node_id', ev.target.value)">
                                            <option value="">No fallback route</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                </t>
                            </t>

                            <t t-if="selectedNode.type === 'condition'">
                                <label class="wa-flow-field">
                                    <span>Condition Type <i class="fa fa-question-circle wa-flow-help" title="How to evaluate the latest reply or saved value before routing."></i></span>
                                    <select t-att-value="selectedNode.config.condition_type || 'keyword_match'" t-on-change="(ev) => this.updateConfig('condition_type', ev.target.value)">
                                        <option value="keyword_match">Keyword Match</option>
                                        <option value="response_contains">Response Contains</option>
                                        <option value="json_path">Saved Variable Exists</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field">
                                    <span>Source</span>
                                    <select t-att-value="selectedNode.config.condition_source || 'last_reply'" t-on-change="(ev) => this.updateConfig('condition_source', ev.target.value)">
                                        <option value="incoming_text">Current Incoming Text</option>
                                        <option value="last_reply">Last Reply</option>
                                        <option value="variable">Saved Variable</option>
                                        <option value="button_payload">Button/List Payload</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="selectedNode.config.condition_source === 'variable'">
                                    <span>Variable Name</span>
                                    <input type="text" t-att-value="selectedNode.config.condition_variable || ''" t-on-input="(ev) => this.updateConfig('condition_variable', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field">
                                    <span>Operator</span>
                                    <select t-att-value="selectedNode.config.condition_operator || 'contains'" t-on-change="(ev) => this.updateConfig('condition_operator', ev.target.value)">
                                        <option value="contains">Contains</option>
                                        <option value="equals">Equals</option>
                                        <option value="not_equals">Does Not Equal</option>
                                        <option value="starts_with">Starts With</option>
                                        <option value="ends_with">Ends With</option>
                                        <option value="regex">Regex Match</option>
                                        <option value="greater_than">Greater Than</option>
                                        <option value="less_than">Less Than</option>
                                        <option value="blank">Is Blank</option>
                                        <option value="not_blank">Is Not Blank</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field">
                                    <span>Match Value <i class="fa fa-question-circle wa-flow-help" title="Text or variable value that decides the true/false path."></i></span>
                                    <input type="text" t-att-value="selectedNode.config.condition_value || ''" t-on-input="(ev) => this.updateConfig('condition_value', ev.target.value)"/>
                                </label>
                                <label class="wa-flow-field">
                                    <span>Go To If True</span>
                                    <select t-att-value="selectedNode.config.condition_true_node_id || ''" t-on-change="(ev) => this.updateConfig('condition_true_node_id', ev.target.value)">
                                        <option value="">First outgoing route</option>
                                        <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                            <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                        </t>
                                    </select>
                                </label>
                                <label class="wa-flow-field">
                                    <span>Go To If False</span>
                                    <select t-att-value="selectedNode.config.condition_false_node_id || ''" t-on-change="(ev) => this.updateConfig('condition_false_node_id', ev.target.value)">
                                        <option value="">Second outgoing route</option>
                                        <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                            <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                        </t>
                                    </select>
                                </label>
                                <div class="wa-flow-palette-title mt-3">Multi-branch Routes</div>
                                <t t-foreach="conditionBranches(selectedNode)" t-as="branch" t-key="branch._key">
                                    <div class="wa-flow-option-editor">
                                        <label class="wa-flow-field">
                                            <span>Label</span>
                                            <input type="text" t-att-value="branch.name || ''" t-on-input="(ev) => this.updateConditionBranch(branch._index, 'name', ev.target.value)"/>
                                        </label>
                                        <label class="wa-flow-field">
                                            <span>Operator</span>
                                            <select t-att-value="branch.operator || 'contains'" t-on-change="(ev) => this.updateConditionBranch(branch._index, 'operator', ev.target.value)">
                                                <option value="contains">Contains</option>
                                                <option value="equals">Equals</option>
                                                <option value="not_equals">Does Not Equal</option>
                                                <option value="starts_with">Starts With</option>
                                                <option value="ends_with">Ends With</option>
                                                <option value="regex">Regex Match</option>
                                                <option value="greater_than">Greater Than</option>
                                                <option value="less_than">Less Than</option>
                                                <option value="blank">Is Blank</option>
                                                <option value="not_blank">Is Not Blank</option>
                                            </select>
                                        </label>
                                        <label class="wa-flow-field">
                                            <span>Value</span>
                                            <input type="text" t-att-value="branch.value || ''" t-on-input="(ev) => this.updateConditionBranch(branch._index, 'value', ev.target.value)"/>
                                        </label>
                                        <label class="wa-flow-field">
                                            <span>Go To Step</span>
                                            <select t-att-value="branch.next_node_id || ''" t-on-change="(ev) => this.updateConditionBranch(branch._index, 'next_node_id', ev.target.value)">
                                                <option value="">No route</option>
                                                <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                    <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                                </t>
                                            </select>
                                        </label>
                                        <button type="button" class="btn btn-outline-danger btn-sm w-100" t-on-click="() => this.removeConditionBranch(branch._index)">
                                            <i class="fa fa-trash me-1"/> Remove Branch
                                        </button>
                                    </div>
                                </t>
                                <button type="button" class="btn btn-outline-secondary btn-sm w-100" t-on-click="addConditionBranch">
                                    <i class="fa fa-plus me-1"/> Add Branch
                                </button>
                            </t>

                            <t t-if="selectedNode.type === 'action'">
                                <label class="wa-flow-field">
                                    <span>Action <i class="fa fa-question-circle wa-flow-help" title="Operational step that changes assignment, creates CRM data, pauses, calls an API, stores a variable, or ends the path."></i></span>
                                    <select t-att-value="selectedNode.config.action_kind || selectedNode.subtype || 'assign_agent'" t-on-change="(ev) => this.updateActionKind(ev.target.value)">
                                        <option value="assign_agent">Assign Agent</option>
                                        <option value="assign_team">Assign Team</option>
                                        <option value="add_label">Add Label/Tag</option>
                                        <option value="create_lead">Create Lead</option>
                                        <option value="ask_question">Ask Question</option>
                                        <option value="set_variable">Set Variable</option>
                                        <option value="wait_reply">Wait Reply</option>
                                        <option value="api_call">API Call</option>
                                        <option value="chat_status">Chat Status</option>
                                        <option value="update_contact">Update Contact</option>
                                        <option value="send_cta_url">URL Button</option>
                                        <option value="send_catalog">Catalog / Product</option>
                                        <option value="send_form_link">Form Link</option>
                                        <option value="send_payment_link">Payment Link</option>
                                        <option value="delay">Delay</option>
                                        <option value="end">End Flow</option>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'assign_agent'">
                                    <span>Agent (User) <i class="fa fa-question-circle wa-flow-help" title="User who will own the chat after this step runs."></i></span>
                                    <select t-att-value="selectedNode.config.assign_user_id || ''" t-on-change="(ev) => this.updateConfig('assign_user_id', ev.target.value)">
                                        <option value="">Select an agent...</option>
                                        <t t-foreach="state.users" t-as="u" t-key="u.id">
                                            <option t-att-value="u.id" t-esc="u.name"/>
                                        </t>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'assign_team'">
                                    <span>Team Members <i class="fa fa-question-circle wa-flow-help" title="Leave empty to use all available team members for this account."></i></span>
                                    <select multiple="true" t-att-value="selectedNode.config.assign_team_member_ids || []" t-on-change="(ev) => this.updateConfig('assign_team_member_ids', Array.from(ev.target.selectedOptions).map((option) => Number(option.value)))">
                                        <t t-foreach="state.teamMembers" t-as="member" t-key="member.id">
                                            <option t-att-value="member.id" t-esc="member.name"/>
                                        </t>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'add_label'">
                                    <span>Tag (Partner Category) <i class="fa fa-question-circle wa-flow-help" title="Contact tag applied to the customer for segmentation and later filtering."></i></span>
                                    <select t-att-value="selectedNode.config.assign_tag_id || ''" t-on-change="(ev) => this.updateConfig('assign_tag_id', ev.target.value)">
                                        <option value="">Select a tag...</option>
                                        <t t-foreach="state.tags" t-as="t" t-key="t.id">
                                            <option t-att-value="t.id" t-esc="t.name"/>
                                        </t>
                                    </select>
                                </label>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'wait_reply'">
                                    <span>Response Variable <i class="fa fa-question-circle wa-flow-help" title="Name used to store the customer's next reply for conditions or later API payloads."></i></span>
                                    <input type="text" t-att-value="selectedNode.config.response_variable || selectedNode.config.variable_name || 'last_reply'" t-on-input="(ev) => this.updateConfig('response_variable', ev.target.value)"/>
                                </label>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'ask_question'">
                                    <label class="wa-flow-field">
                                        <span>Question Text</span>
                                        <textarea rows="4" t-att-value="selectedNode.config.message_text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Answer Type</span>
                                        <select t-att-value="selectedNode.config.input_validation_type || 'text'" t-on-change="(ev) => this.updateConfig('input_validation_type', ev.target.value)">
                                            <option value="text">Text</option>
                                            <option value="number">Number</option>
                                            <option value="email">Email</option>
                                            <option value="phone">Phone</option>
                                            <option value="city">City / Location Text</option>
                                            <option value="media">File or Media</option>
                                            <option value="location">WhatsApp Location</option>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Save As Variable</span>
                                        <input type="text" t-att-value="selectedNode.config.response_variable || 'customer_answer'" t-on-input="(ev) => this.updateConfig('response_variable', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Max Attempts</span>
                                        <input type="number" min="1" t-att-value="selectedNode.config.max_attempts || 2" t-on-input="(ev) => this.updateConfig('max_attempts', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>No Reply Timeout (minutes)</span>
                                        <input type="number" min="0" t-att-value="selectedNode.config.timeout_minutes || 0" t-on-input="(ev) => this.updateConfig('timeout_minutes', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Invalid Answer Message</span>
                                        <textarea rows="3" t-att-value="selectedNode.config.invalid_message || ''" t-on-input="(ev) => this.updateConfig('invalid_message', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Go To On Invalid</span>
                                        <select t-att-value="selectedNode.config.invalid_node_id || ''" t-on-change="(ev) => this.updateConfig('invalid_node_id', ev.target.value)">
                                            <option value="">Repeat question</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Go To On No Reply</span>
                                        <select t-att-value="selectedNode.config.timeout_node_id || ''" t-on-change="(ev) => this.updateConfig('timeout_node_id', ev.target.value)">
                                            <option value="">No no-reply route</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Fallback Route</span>
                                        <select t-att-value="selectedNode.config.fallback_node_id || ''" t-on-change="(ev) => this.updateConfig('fallback_node_id', ev.target.value)">
                                            <option value="">No fallback route</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                </t>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'create_lead'">
                                    <span>Lead Note <i class="fa fa-question-circle wa-flow-help" title="Optional note copied to the CRM lead created from this chat."></i></span>
                                    <textarea rows="4" placeholder="Optional note saved on the CRM lead" t-att-value="selectedNode.config.message_text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                </label>
                                <div class="wa-flow-hint" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'create_lead'">
                                    Lead notes support the same placeholders as messages, such as &#123;&#123;name&#125;&#125; and &#123;&#123;last_message&#125;&#125;.
                                </div>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'set_variable'">
                                    <label class="wa-flow-field">
                                        <span>Variable Name <i class="fa fa-question-circle wa-flow-help" title="Key used to store a value during this flow run."></i></span>
                                        <input type="text" placeholder="lead_source" t-att-value="selectedNode.config.variable_name || ''" t-on-input="(ev) => this.updateConfig('variable_name', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Variable Value <i class="fa fa-question-circle wa-flow-help" title="Value saved under the variable name."></i></span>
                                        <input type="text" placeholder="WhatsApp" t-att-value="selectedNode.config.variable_value || ''" t-on-input="(ev) => this.updateConfig('variable_value', ev.target.value)"/>
                                    </label>
                                    <div class="wa-flow-hint">Variable values can include placeholders, for example &#123;&#123;last_reply&#125;&#125;.</div>
                                </t>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'delay'">
                                    <span>Delay Seconds <i class="fa fa-question-circle wa-flow-help" title="Seconds to pause before moving to the next step."></i></span>
                                    <input type="number" t-att-value="selectedNode.config.delay_seconds || 0" t-on-input="(ev) => this.updateConfig('delay_seconds', ev.target.value)"/>
                                </label>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'api_call'">
                                    <label class="wa-flow-field">
                                        <span>HTTP Method <i class="fa fa-question-circle wa-flow-help" title="Request method for the external webhook."></i></span>
                                        <select t-att-value="selectedNode.config.http_method || 'POST'" t-on-change="(ev) => this.updateConfig('http_method', ev.target.value)">
                                            <option value="GET">GET</option>
                                            <option value="POST">POST</option>
                                            <option value="PUT">PUT</option>
                                            <option value="PATCH">PATCH</option>
                                            <option value="DELETE">DELETE</option>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Webhook URL <i class="fa fa-question-circle wa-flow-help" title="External URL called by this step."></i></span>
                                        <input type="url" placeholder="https://api.example.com/endpoint" t-att-value="selectedNode.config.http_url || ''" t-on-input="(ev) => this.updateConfig('http_url', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Auth Type</span>
                                        <select t-att-value="selectedNode.config.http_auth_type || 'none'" t-on-change="(ev) => this.updateConfig('http_auth_type', ev.target.value)">
                                            <option value="none">None</option>
                                            <option value="bearer">Bearer Token</option>
                                            <option value="basic">Basic Auth</option>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field" t-if="(selectedNode.config.http_auth_type || 'none') === 'bearer'">
                                        <span>Bearer Token</span>
                                        <input type="password" t-att-value="selectedNode.config.http_auth_token || ''" t-on-input="(ev) => this.updateConfig('http_auth_token', ev.target.value)"/>
                                    </label>
                                    <t t-if="selectedNode.config.http_auth_type === 'basic'">
                                        <label class="wa-flow-field">
                                            <span>Username</span>
                                            <input type="text" t-att-value="selectedNode.config.http_username || ''" t-on-input="(ev) => this.updateConfig('http_username', ev.target.value)"/>
                                        </label>
                                        <label class="wa-flow-field">
                                            <span>Password</span>
                                            <input type="password" t-att-value="selectedNode.config.http_password || ''" t-on-input="(ev) => this.updateConfig('http_password', ev.target.value)"/>
                                        </label>
                                    </t>
                                    <label class="wa-flow-field">
                                        <span>Payload (JSON) <i class="fa fa-question-circle wa-flow-help" title="Optional JSON body for POST/PUT requests."></i></span>
                                        <textarea rows="4" placeholder='{"key": "value"}' t-att-value="selectedNode.config.http_payload || ''" t-on-input="(ev) => this.updateConfig('http_payload', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Headers (JSON)</span>
                                        <textarea rows="3" placeholder='{"X-API-Key": "secret"}' t-att-value="selectedNode.config.http_headers || ''" t-on-input="(ev) => this.updateConfig('http_headers', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Query Params (JSON)</span>
                                        <textarea rows="3" placeholder='{"phone": "{{phone}}"}' t-att-value="selectedNode.config.http_query_params || ''" t-on-input="(ev) => this.updateConfig('http_query_params', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Response Variable</span>
                                        <input type="text" placeholder="api_result" t-att-value="selectedNode.config.response_variable || ''" t-on-input="(ev) => this.updateConfig('response_variable', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Response JSON Path</span>
                                        <input type="text" placeholder="data.status" t-att-value="selectedNode.config.http_response_path || ''" t-on-input="(ev) => this.updateConfig('http_response_path', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Go To On Success</span>
                                        <select t-att-value="selectedNode.config.http_success_node_id || ''" t-on-change="(ev) => this.updateConfig('http_success_node_id', ev.target.value)">
                                            <option value="">Default next step</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Go To On Failure</span>
                                        <select t-att-value="selectedNode.config.http_failure_node_id || ''" t-on-change="(ev) => this.updateConfig('http_failure_node_id', ev.target.value)">
                                            <option value="">Raise failure</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                    <div class="wa-flow-hint">Payload JSON supports placeholders, for example {"phone": "&#123;&#123;phone&#125;&#125;", "name": "&#123;&#123;name&#125;&#125;"}.</div>
                                </t>
                                <label class="wa-flow-field" t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'chat_status'">
                                    <span>Status</span>
                                    <select t-att-value="selectedNode.config.chat_status || 'open'" t-on-change="(ev) => this.updateConfig('chat_status', ev.target.value)">
                                        <option value="open">Open / Reopen</option>
                                        <option value="snoozed">Snoozed</option>
                                        <option value="resolved">Resolved</option>
                                        <option value="archived">Archived</option>
                                    </select>
                                </label>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'update_contact'">
                                    <label class="wa-flow-field">
                                        <span>Attribute Name</span>
                                        <input type="text" placeholder="requirement" t-att-value="selectedNode.config.contact_attribute_name || ''" t-on-input="(ev) => this.updateConfig('contact_attribute_name', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Attribute Value</span>
                                        <input type="text" placeholder="{{last_reply}}" t-att-value="selectedNode.config.contact_attribute_value || ''" t-on-input="(ev) => this.updateConfig('contact_attribute_value', ev.target.value)"/>
                                    </label>
                                </t>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'send_cta_url'">
                                    <label class="wa-flow-field">
                                        <span>Message Text</span>
                                        <textarea rows="4" t-att-value="selectedNode.config.message_text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Button Text</span>
                                        <input type="text" placeholder="Open Catalogue" t-att-value="selectedNode.config.cta_button_text || ''" t-on-input="(ev) => this.updateConfig('cta_button_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>URL</span>
                                        <input type="url" placeholder="https://..." t-att-value="selectedNode.config.cta_button_url || ''" t-on-input="(ev) => this.updateConfig('cta_button_url', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Header Text</span>
                                        <input type="text" t-att-value="selectedNode.config.button_header_text || ''" t-on-input="(ev) => this.updateConfig('button_header_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Footer Text</span>
                                        <input type="text" t-att-value="selectedNode.config.button_footer_text || ''" t-on-input="(ev) => this.updateConfig('button_footer_text', ev.target.value)"/>
                                    </label>
                                    <div class="wa-flow-hint">Use this only while the WhatsApp service window is open. For closed sessions, use an approved CTA template.</div>
                                </t>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'send_catalog'">
                                    <label class="wa-flow-field">
                                        <span>Catalog Message Type</span>
                                        <select t-att-value="selectedNode.config.catalog_message_type || 'single_product'" t-on-change="(ev) => this.updateConfig('catalog_message_type', ev.target.value)">
                                            <option value="single_product">Single Product Card</option>
                                            <option value="multi_product">Multi-Product List</option>
                                            <option value="catalog_message">Full Catalog / Shop</option>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Catalog ID</span>
                                        <input type="text" placeholder="Optional if account default exists" t-att-value="selectedNode.config.catalog_id || ''" t-on-input="(ev) => this.updateConfig('catalog_id', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="(selectedNode.config.catalog_message_type || 'single_product') === 'single_product'">
                                        <span>Product Retailer ID</span>
                                        <input type="text" placeholder="SKU/content ID from Meta catalog" t-att-value="selectedNode.config.product_retailer_id || ''" t-on-input="(ev) => this.updateConfig('product_retailer_id', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="selectedNode.config.catalog_message_type === 'multi_product'">
                                        <span>Product Retailer IDs</span>
                                        <textarea rows="3" placeholder="One SKU/content ID per line" t-att-value="selectedNode.config.product_retailer_ids || ''" t-on-input="(ev) => this.updateConfig('product_retailer_ids', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="selectedNode.config.catalog_message_type === 'catalog_message'">
                                        <span>Thumbnail Product ID</span>
                                        <input type="text" placeholder="Optional product to highlight" t-att-value="selectedNode.config.thumbnail_product_retailer_id || ''" t-on-input="(ev) => this.updateConfig('thumbnail_product_retailer_id', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="selectedNode.config.catalog_message_type === 'multi_product'">
                                        <span>Section Title</span>
                                        <input type="text" placeholder="Products" t-att-value="selectedNode.config.catalog_section_title || 'Products'" t-on-input="(ev) => this.updateConfig('catalog_section_title', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field" t-if="selectedNode.config.catalog_message_type === 'multi_product'">
                                        <span>Header Text</span>
                                        <input type="text" t-att-value="selectedNode.config.button_header_text || ''" t-on-input="(ev) => this.updateConfig('button_header_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Message Text</span>
                                        <textarea rows="3" t-att-value="selectedNode.config.message_text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Footer Text</span>
                                        <input type="text" t-att-value="selectedNode.config.button_footer_text || ''" t-on-input="(ev) => this.updateConfig('button_footer_text', ev.target.value)"/>
                                    </label>
                                    <div class="wa-flow-hint">Catalog ID can come from the WhatsApp Account. Product Retailer ID is the Meta catalog content ID/SKU, not an ERP product database ID.</div>
                                </t>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'send_form_link'">
                                    <label class="wa-flow-field">
                                        <span>Message Text</span>
                                        <textarea rows="4" t-att-value="selectedNode.config.message_text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Form</span>
                                        <select t-att-value="selectedNode.config.form_id || ''" t-on-change="(ev) => this.updateConfig('form_id', ev.target.value)">
                                            <option value="">Use account default form</option>
                                            <t t-foreach="state.forms" t-as="form" t-key="form.id">
                                                <option t-att-value="form.id" t-esc="form.name"/>
                                            </t>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Fallback Route</span>
                                        <select t-att-value="selectedNode.config.fallback_node_id || ''" t-on-change="(ev) => this.updateConfig('fallback_node_id', ev.target.value)">
                                            <option value="">Stop with clear error if form is missing</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                    <div class="wa-flow-hint">Use {{form_url}} in the message. If no form is selected, the WhatsApp account default form is used.</div>
                                </t>
                                <t t-if="(selectedNode.config.action_kind || selectedNode.subtype) === 'send_payment_link'">
                                    <label class="wa-flow-field">
                                        <span>Message Text</span>
                                        <textarea rows="4" t-att-value="selectedNode.config.message_text || ''" t-on-input="(ev) => this.updateConfig('message_text', ev.target.value)"/>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Payment Source</span>
                                        <select t-att-value="selectedNode.config.payment_mode || 'account_default'" t-on-change="(ev) => this.updateConfig('payment_mode', ev.target.value)">
                                            <option value="account_default">Account Default</option>
                                            <option value="latest_invoice">Latest Unpaid Invoice</option>
                                            <option value="latest_quote">Latest Quotation / Order</option>
                                            <option value="manual_url">Manual URL From Account</option>
                                        </select>
                                    </label>
                                    <label class="wa-flow-field">
                                        <span>Fallback Route</span>
                                        <select t-att-value="selectedNode.config.fallback_node_id || ''" t-on-change="(ev) => this.updateConfig('fallback_node_id', ev.target.value)">
                                            <option value="">Stop with clear error if payment link is unavailable</option>
                                            <t t-foreach="state.nodes.filter((n) => n.id !== selectedNode.id &amp;&amp; n.type !== 'trigger')" t-as="routeNode" t-key="routeNode.id">
                                                <option t-att-value="routeNode.id" t-esc="routeNode.label"/>
                                            </t>
                                        </select>
                                    </label>
                                    <div class="wa-flow-hint">Use {{payment_url}} in the message. Payment links can use a selected source or the WhatsApp Account default.</div>
                                </t>
                            </t>

                            <t t-set="outEdges" t-value="selectedNodeEdges"/>
                            <t t-if="outEdges.length > 0">
                                <div class="wa-flow-palette-title mt-3">Outgoing Connections</div>
                                <t t-foreach="outEdges" t-as="edge" t-key="edge.id">
                                    <label class="wa-flow-field">
                                        <span>Route to: <t t-esc="getNodeLabel(edge.to)"/> <i class="fa fa-question-circle wa-flow-help" title="For button nodes this becomes the button label. For condition nodes use true or false."></i></span>
                                        <input type="text" placeholder="e.g. Button Label, true/false" t-att-value="edge.label || ''" t-on-input="(ev) => this.updateEdgeLabel(edge.id, ev.target.value)"/>
                                    </label>
                                </t>
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
            templates: [],
            media: [],
            users: [],
            tags: [],
            teamMembers: [],
            forms: [],
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

    get selectedNodeEdges() {
        if (!this.state.selectedNodeId) return [];
        return this.state.edges.filter((edge) => edge.from === this.state.selectedNodeId);
    }

    get validationIssues() {
        const issues = this.state.nodes.flatMap((node) => this.nodeIssues(node).map((message) => ({ node, message })));
        for (const edge of this.state.edges) {
            if (edge.from && edge.to && edge.from === edge.to) {
                issues.push({
                    node: this.state.nodes.find((node) => node.id === edge.from) || null,
                    message: "Remove the self-loop connection before saving.",
                });
            }
        }
        return issues;
    }

    get selectedNodeIssues() {
        return this.selectedNode ? this.nodeIssues(this.selectedNode) : [];
    }

    nodeIssues(node) {
        const issues = [];
        const config = node.config || {};
        const outgoingCount = this.state.edges.filter((edge) => edge.from === node.id).length;

        if (node.type === "trigger" && (config.trigger_type || "keyword") === "keyword" && !String(config.keywords || "").trim()) {
            issues.push("Add at least one keyword so this flow can start automatically.");
        }
        if (node.type === "message") {
            const mode = config.message_mode || node.subtype || "text";
            if (mode === "template" && !config.template_id) {
                issues.push("Select an approved template.");
            } else if (mode === "media" && !config.media_id) {
                issues.push("Select a media file.");
            } else if (mode === "buttons" || mode === "list") {
                if (!String(config.message_text || config.text || "").trim()) {
                    issues.push("Add the option prompt text.");
                }
                const hasInlineOptions = Array.isArray(config.options) && config.options.some((opt) => String(opt.title || "").trim());
                if (!outgoingCount && !hasInlineOptions) {
                    issues.push("Add at least one option or connect this node to next steps.");
                }
                if (hasInlineOptions && config.options.some((opt) => String(opt.title || "").trim() && (opt.button_action || "reply") === "reply" && !opt.next_node_id)) {
                    issues.push("Route every reply option to a next step, or remove unused options.");
                }
                if (mode === "buttons" && Array.isArray(config.options)) {
                    const specialOptions = config.options.filter((opt) => ["url", "catalog_product"].includes(opt.button_action || "reply"));
                    if (specialOptions.length && config.options.length > 1) {
                        issues.push("URL/product button messages can only have one button. Split extra options into another step.");
                    }
                    if (specialOptions.some((opt) => opt.button_action === "url" && !/^https?:\/\//i.test(String(opt.url || "")))) {
                        issues.push("Add an http(s) URL for the URL button.");
                    }
                    if (specialOptions.some((opt) => opt.button_action === "catalog_product" && !String(opt.product_retailer_id || "").trim())) {
                        issues.push("Add a Product Retailer ID for the product button.");
                    }
                }
            } else if (!String(config.message_text || config.text || "").trim()) {
                issues.push("Add message text.");
            }
        }
        if (node.type === "condition") {
            const operator = config.condition_operator || "contains";
            if (!["blank", "not_blank"].includes(operator) && !String(config.condition_value || "").trim()) {
                issues.push("Add the condition match value.");
            }
            const hasConfiguredRoute = config.condition_true_node_id || config.condition_false_node_id ||
                (Array.isArray(config.condition_branches) && config.condition_branches.some((branch) => branch.next_node_id));
            if (!outgoingCount && !hasConfiguredRoute) {
                issues.push("Configure at least one true, false, or branch route.");
            }
            if (Array.isArray(config.condition_branches) && config.condition_branches.some((branch) => !branch.next_node_id)) {
                issues.push("Route every condition branch to a next step, or remove unused branches.");
            }
        }
        if (node.type === "action") {
            const kind = config.action_kind || node.subtype || "assign_agent";
            if (kind === "assign_agent" && !config.assign_user_id) {
                issues.push("Select an agent.");
            } else if (kind === "ask_question" && !String(config.response_variable || "").trim()) {
                issues.push("Set where to save the answer.");
            } else if (kind === "ask_question" && !String(config.message_text || "").trim()) {
                issues.push("Add the question text.");
            } else if (kind === "add_label" && !config.assign_tag_id) {
                issues.push("Select a tag.");
            } else if (kind === "api_call" && !String(config.http_url || "").trim()) {
                issues.push("Add the webhook URL.");
            } else if (kind === "set_variable" && !String(config.variable_name || "").trim()) {
                issues.push("Add the variable name.");
            } else if (kind === "update_contact" && !String(config.contact_attribute_name || "").trim()) {
                issues.push("Add the contact attribute name.");
            } else if (kind === "send_cta_url" && !String(config.cta_button_text || "").trim()) {
                issues.push("Add the URL button text.");
            } else if (kind === "send_cta_url" && !/^https?:\/\//i.test(String(config.cta_button_url || ""))) {
                issues.push("Add an http(s) URL for the URL button, or configure the account shop URL before saving in form view.");
            } else if (kind === "send_catalog") {
                const mode = config.catalog_message_type || "single_product";
                if (mode === "single_product" && !String(config.product_retailer_id || "").trim()) {
                    issues.push("Add the Product Retailer ID for the single product card.");
                } else if (mode === "multi_product" && !String(config.product_retailer_ids || "").trim()) {
                    issues.push("Add one or more Product Retailer IDs for the product list.");
                }
            } else if (kind === "send_form_link" && !String(config.message_text || "").trim()) {
                issues.push("Add the form-link message text.");
            } else if (kind === "send_payment_link" && !String(config.message_text || "").trim()) {
                issues.push("Add the payment-link message text.");
            }
        }
        return issues;
    }

    getNodeLabel(nodeId) {
        const node = this.state.nodes.find((n) => n.id === nodeId);
        return node ? node.label : nodeId;
    }

    updateEdgeLabel(edgeId, label) {
        const edge = this.state.edges.find((e) => e.id === edgeId);
        if (edge) {
            edge.label = label;
        }
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
            const accountId = recordId(graph.flow?.account_id);
            await this.loadRelationalData(accountId);
        } catch (error) {
            console.error("[WA Flow Builder] Load failed", error);
            this.notification.add("Could not load the visual flow graph.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async loadRelationalData(accountId) {
        try {
            accountId = recordId(accountId);
            const templatesDomain = [["status", "=", "approved"]];
            if (accountId) {
                templatesDomain.push(["account_id", "in", [accountId, false]]);
            }
            const templates = await this.orm.searchRead(
                "whatsapp.template",
                templatesDomain,
                ["id", "name"]
            );
            const mediaDomain = accountId
                ? [["account_id", "=", accountId], ["active", "=", true]]
                : [["active", "=", true]];
            const media = await this.orm.searchRead(
                "whatsapp.media.library",
                mediaDomain,
                ["id", "name"]
            );
            const users = await this.orm.searchRead(
                "res.users",
                [["active", "=", true]],
                ["id", "name"]
            );
            const tags = await this.orm.searchRead(
                "res.partner.category",
                [],
                ["id", "name"]
            );
            const teamMembers = await this.orm.searchRead(
                "whatsapp.team.member",
                accountId ? [["account_id", "=", accountId], ["user_id", "!=", false]] : [["user_id", "!=", false]],
                ["id", "user_id", "role"]
            );
            const forms = await this.orm.searchRead(
                "whatsapp.form",
                [["active", "=", true]],
                ["id", "name"]
            );
            this.state.templates = templates || [];
            this.state.media = media || [];
            this.state.users = users || [];
            this.state.tags = tags || [];
            this.state.forms = forms || [];
            this.state.teamMembers = (teamMembers || []).map((member) => ({
                id: member.id,
                name: Array.isArray(member.user_id) ? member.user_id[1] : `Member #${member.id}`,
                role: member.role,
            }));
        } catch (error) {
            console.error("[WA Flow Builder] Relational data fetch failed", error);
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
        if (this.state.edges.some((edge) => edge.from && edge.to && edge.from === edge.to)) {
            this.notification.add("Remove self-loop connections before saving the flow.", { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            const graph = await this.orm.call("whatsapp.bot.flow", "save_visual_graph", [[this.flowId], this.serializeGraph()]);
            this.applyGraph(graph || {});
            const issueCount = this.validationIssues.length;
            this.notification.add(
                issueCount
                    ? `Flow saved with ${issueCount} configuration warning${issueCount === 1 ? "" : "s"}.`
                    : "Flow saved and synchronized with bot steps.",
                { type: issueCount ? "warning" : "success" }
            );
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

    interactiveOptions(node) {
        const options = Array.isArray(node?.config?.options) ? node.config.options : [];
        return options.map((option, index) => ({
            ...option,
            _index: index,
            _key: `${node.id}_option_${index}`,
        }));
    }

    addInteractiveOption() {
        if (!this.selectedNode) return;
        const mode = this.selectedNode.config?.message_mode || this.selectedNode.subtype || "buttons";
        const limit = mode === "list" ? 10 : 3;
        const options = Array.isArray(this.selectedNode.config?.options)
            ? [...this.selectedNode.config.options]
            : [];
        if (options.length >= limit) {
            this.notification.add(mode === "list" ? "List menus support up to 10 rows." : "Quick replies support up to 3 buttons.", { type: "warning" });
            return;
        }
        const number = options.length + 1;
        options.push({
            title: `Option ${number}`,
            id: `${this.selectedNode.id}_option_${number}`,
            description: "",
            button_action: "reply",
            url: "",
            catalog_id: "",
            product_retailer_id: "",
            next_node_id: "",
        });
        this.updateConfig("options", options);
    }

    updateInteractiveOption(index, field, value) {
        if (!this.selectedNode) return;
        const options = Array.isArray(this.selectedNode.config?.options)
            ? [...this.selectedNode.config.options]
            : [];
        options[index] = { ...(options[index] || {}), [field]: value };
        this.updateConfig("options", options);
    }

    removeInteractiveOption(index) {
        if (!this.selectedNode) return;
        const options = Array.isArray(this.selectedNode.config?.options)
            ? [...this.selectedNode.config.options]
            : [];
        options.splice(index, 1);
        this.updateConfig("options", options);
    }

    conditionBranches(node) {
        const branches = Array.isArray(node?.config?.condition_branches) ? node.config.condition_branches : [];
        return branches.map((branch, index) => ({
            ...branch,
            _index: index,
            _key: `${node.id}_branch_${index}`,
        }));
    }

    addConditionBranch() {
        if (!this.selectedNode) return;
        const branches = Array.isArray(this.selectedNode.config?.condition_branches)
            ? [...this.selectedNode.config.condition_branches]
            : [];
        const number = branches.length + 1;
        branches.push({
            name: `Branch ${number}`,
            operator: "contains",
            value: "",
            next_node_id: "",
        });
        this.updateConfig("condition_branches", branches);
    }

    updateConditionBranch(index, field, value) {
        if (!this.selectedNode) return;
        const branches = Array.isArray(this.selectedNode.config?.condition_branches)
            ? [...this.selectedNode.config.condition_branches]
            : [];
        branches[index] = { ...(branches[index] || {}), [field]: value };
        this.updateConfig("condition_branches", branches);
    }

    removeConditionBranch(index) {
        if (!this.selectedNode) return;
        const branches = Array.isArray(this.selectedNode.config?.condition_branches)
            ? [...this.selectedNode.config.condition_branches]
            : [];
        branches.splice(index, 1);
        this.updateConfig("condition_branches", branches);
    }

    updateMessageMode(mode) {
        if (!this.selectedNode) return;
        this.selectedNode.subtype = mode;
        const extraDefaults = mode === "list"
            ? { list_button_text: "Choose", list_section_title: "Options", button_header_text: "", button_footer_text: "", options: [] }
            : mode === "buttons"
                ? { button_header_text: "", button_footer_text: "", options: [] }
                : {};
        this.selectedNode.config = {
            ...(this.selectedNode.config || {}),
            ...extraDefaults,
            message_mode: mode,
        };
    }

    updateActionKind(kind) {
        if (!this.selectedNode) return;
        const defaults = PALETTE_ITEMS.find((item) => item.type === "action" && item.subtype === kind)?.defaults || {};
        this.selectedNode.subtype = kind;
        this.selectedNode.config = {
            ...(this.selectedNode.config || {}),
            ...defaults,
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

    autoLayout() {
        if (!this.state.nodes.length) return;

        const nodeIds = new Set(this.state.nodes.map((node) => node.id));
        const incoming = new Map(this.state.nodes.map((node) => [node.id, 0]));
        const outgoing = new Map(this.state.nodes.map((node) => [node.id, []]));
        for (const edge of this.state.edges) {
            if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) continue;
            incoming.set(edge.to, (incoming.get(edge.to) || 0) + 1);
            outgoing.get(edge.from).push(edge.to);
        }

        const roots = this.state.nodes
            .filter((node) => node.type === "trigger" || !incoming.get(node.id))
            .map((node) => node.id);
        if (!roots.length) roots.push(this.state.nodes[0].id);

        const levels = new Map();
        const queue = roots.map((id) => ({ id, level: 0 }));
        while (queue.length) {
            const current = queue.shift();
            if (levels.has(current.id) && levels.get(current.id) <= current.level) continue;
            levels.set(current.id, current.level);
            for (const target of outgoing.get(current.id) || []) {
                queue.push({ id: target, level: current.level + 1 });
            }
        }

        let fallbackLevel = Math.max(0, ...levels.values()) + 1;
        for (const node of this.state.nodes) {
            if (!levels.has(node.id)) {
                levels.set(node.id, fallbackLevel++);
            }
        }

        const grouped = new Map();
        for (const node of this.state.nodes) {
            const level = levels.get(node.id) || 0;
            if (!grouped.has(level)) grouped.set(level, []);
            grouped.get(level).push(node);
        }

        for (const level of [...grouped.keys()].sort((a, b) => a - b)) {
            grouped.get(level)
                .sort((a, b) => (a.y - b.y) || (a.x - b.x) || a.id.localeCompare(b.id))
                .forEach((node, index) => {
                    node.x = 80 + level * 320;
                    node.y = 120 + index * 150;
                });
        }
        this.resetView();
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
            const mode = node.config?.message_mode || node.subtype || "text";
            if (mode === "template") {
                if (node.config?.template_id) {
                    const t = this.state.templates.find(item => item.id === Number(node.config.template_id));
                    return t ? `Template: ${t.name}` : `Template #${node.config.template_id}`;
                }
                return "Select template";
            }
            if (mode === "media") {
                if (node.config?.media_id) {
                    const m = this.state.media.find(item => item.id === Number(node.config.media_id));
                    return m ? `Media: ${m.name}` : `Media #${node.config.media_id}`;
                }
                return "Select media file";
            }
            if (mode === "list") {
                return node.config?.message_text || "Configure list prompt";
            }
            return node.config?.message_text || node.config?.text || "Write a message";
        }
        if (node.type === "condition") {
            return `${node.config?.condition_type || "keyword_match"}: ${node.config?.condition_value || "set value"}`;
        }
        if (node.type === "action") {
            const kind = node.config?.action_kind || node.subtype || "assign_agent";
            if (kind === "assign_agent") {
                if (node.config?.assign_user_id) {
                    const u = this.state.users.find(item => item.id === Number(node.config.assign_user_id));
                    return u ? `Assign to: ${u.name}` : `Assign User #${node.config.assign_user_id}`;
                }
                return "Select agent";
            }
            if (kind === "assign_team") {
                const ids = node.config?.assign_team_member_ids || [];
                return ids.length ? `Assign team: ${ids.length} member(s)` : "Assign any available team member";
            }
            if (kind === "add_label") {
                if (node.config?.assign_tag_id) {
                    const t = this.state.tags.find(item => item.id === Number(node.config.assign_tag_id));
                    return t ? `Add tag: ${t.name}` : `Add Tag #${node.config.assign_tag_id}`;
                }
                return "Select tag";
            }
            if (kind === "create_lead") {
                return node.config?.message_text || "Create CRM lead";
            }
            if (kind === "set_variable") {
                return node.config?.variable_name
                    ? `${node.config.variable_name} = ${node.config?.variable_value || ""}`
                    : "Set variable";
            }
            if (kind === "wait_reply") {
                return `Save reply as: ${node.config?.response_variable || node.config?.variable_name || "last_reply"}`;
            }
            if (kind === "ask_question") {
                return `Ask: ${node.config?.response_variable || "customer_answer"} (${node.config?.input_validation_type || "text"})`;
            }
            if (kind === "delay") {
                return `Delay: ${node.config?.delay_seconds || 0}s`;
            }
            if (kind === "api_call") {
                return `${node.config?.http_method || "POST"}: ${node.config?.http_url || "webhook URL"}`;
            }
            if (kind === "chat_status") {
                return `Set chat: ${node.config?.chat_status || "open"}`;
            }
            if (kind === "update_contact") {
                return node.config?.contact_attribute_name ? `Set ${node.config.contact_attribute_name}` : "Update contact attribute";
            }
            if (kind === "send_cta_url") {
                return node.config?.cta_button_url ? `Open: ${node.config.cta_button_url}` : "Configure URL button";
            }
            if (kind === "send_catalog") {
                const mode = node.config?.catalog_message_type || "single_product";
                if (mode === "catalog_message") {
                    return node.config?.thumbnail_product_retailer_id
                        ? `Open catalog: ${node.config.thumbnail_product_retailer_id}`
                        : "Open full catalog/shop";
                }
                if (mode === "multi_product") {
                    return node.config?.product_retailer_ids || "Configure product list";
                }
                return node.config?.product_retailer_id ? `Product: ${node.config.product_retailer_id}` : "Configure product card";
            }
            if (kind === "send_form_link") {
                if (node.config?.form_id) {
                    const form = this.state.forms.find(item => item.id === Number(node.config.form_id));
                    return form ? `Form: ${form.name}` : `Form #${node.config.form_id}`;
                }
                return "Send account default form";
            }
            if (kind === "send_payment_link") {
                return "Send account payment link";
            }
            if (kind === "end") {
                return "End flow";
            }
            return kind;
        }
        return "";
    }
}

registry.category("actions").add("elsx_whatsapp_flow_builder", WhatsAppBotFlowAction);
