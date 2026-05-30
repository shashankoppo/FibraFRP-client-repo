/** @odoo-module **/

import { Component, xml, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { animateFlowBuilderIn, animateFlowNodeFocus } from "@elsx_whatsapp_marketing/js/elsx_ui_motion";

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
    ask_question: { label: "Ask Question", icon: "fa-question-circle", color: "#f97316" },
    condition: { label: "Condition", icon: "fa-code-fork", color: "#9c27b0" },
    assign_agent: { label: "Assign Agent", icon: "fa-user-plus", color: "#607d8b" },
    assign_team: { label: "Assign Team", icon: "fa-users", color: "#0f766e" },
    add_tag: { label: "Add Tag", icon: "fa-tag", color: "#795548" },
    create_lead: { label: "Create Lead", icon: "fa-address-card-o", color: "#7c3aed" },
    chat_status: { label: "Chat Status", icon: "fa-check-circle", color: "#14b8a6" },
    update_contact: { label: "Update Contact", icon: "fa-id-card", color: "#8b5cf6" },
    set_variable: { label: "Set Variable", icon: "fa-database", color: "#64748b" },
    send_cta_url: { label: "URL Button", icon: "fa-external-link", color: "#0ea5e9" },
    send_catalog: { label: "Catalog Product", icon: "fa-shopping-bag", color: "#16a34a" },
    send_form_link: { label: "Form Link", icon: "fa-wpforms", color: "#14b8a6" },
    send_payment_link: { label: "Payment Link", icon: "fa-credit-card", color: "#22c55e" },
    delay: { label: "Delay", icon: "fa-hourglass-half", color: "#ff5722" },
    api_call: { label: "API Call", icon: "fa-cloud", color: "#3f51b5" },
    end: { label: "End", icon: "fa-stop-circle", color: "#f44336" },
};

const PALETTE_TYPES = [
    "trigger",
    "send_text",
    "send_template",
    "send_buttons",
    "send_list",
    "send_media",
    "wait_reply",
    "ask_question",
    "condition",
    "assign_agent",
    "assign_team",
    "add_tag",
    "create_lead",
    "chat_status",
    "update_contact",
    "set_variable",
    "send_cta_url",
    "send_catalog",
    "send_form_link",
    "send_payment_link",
    "delay",
    "api_call",
    "end",
];

const CONFIG_HINTS = {
    message: "Legacy message node",
    action: "Legacy action node",
    send_text: "Configure text body",
    send_template: "Configure template id",
    send_buttons: "Configure text + branches",
    send_list: "Configure list text + branches",
    send_media: "Configure media id",
    condition: "Configure condition",
    wait_reply: "Configure response variable",
    ask_question: "Collect and validate an answer",
    assign_agent: "Configure user id",
    assign_team: "Configure team member ids",
    add_tag: "Configure tag id",
    create_lead: "Configure lead note",
    chat_status: "Set open/resolved/snoozed",
    update_contact: "Save contact attribute",
    set_variable: "Configure variable",
    send_cta_url: "Configure URL button",
    send_catalog: "Configure catalog/shop/product",
    send_form_link: "Send a tokenized customer form",
    send_payment_link: "Send a configured payment link",
    delay: "Configure delay seconds",
    api_call: "Configure method/url/payload",
    trigger: "Configure trigger settings",
    end: "Finish this path",
};

function recordId(value) {
    if (!value) return false;
    if (Array.isArray(value)) return value[0] || false;
    if (typeof value === "object") return value.id || value.resId || false;
    return value;
}

const DEFAULT_CONFIG = {
    trigger: { trigger_type: "keyword", keywords: "" },
    send_text: { message_mode: "text", message_text: "" },
    send_template: { message_mode: "template", template_id: false },
    send_buttons: { message_mode: "buttons", message_text: "Please choose an option" },
    send_list: { message_mode: "list", message_text: "Please choose an option", list_button_text: "Choose", list_section_title: "Options", button_header_text: "", button_footer_text: "", options: [] },
    send_media: { message_mode: "media", media_id: false, message_text: "" },
    wait_reply: { action_kind: "wait_reply", save_response: true, response_variable: "last_reply" },
    ask_question: { action_kind: "ask_question", message_text: "Please share your answer.", response_variable: "customer_answer", input_validation_type: "text", max_attempts: 2, timeout_minutes: 0 },
    condition: { condition_type: "keyword_match", condition_source: "last_reply", condition_operator: "contains", condition_value: "", condition_branches: [] },
    assign_agent: { action_kind: "assign_agent", assign_user_id: false },
    assign_team: { action_kind: "assign_team", assign_team_member_ids: [] },
    add_tag: { action_kind: "add_label", assign_tag_id: false },
    create_lead: { action_kind: "create_lead", message_text: "" },
    chat_status: { action_kind: "chat_status", chat_status: "open" },
    update_contact: { action_kind: "update_contact", contact_attribute_name: "", contact_attribute_value: "" },
    set_variable: { action_kind: "set_variable", variable_name: "", variable_value: "" },
    send_cta_url: { action_kind: "send_cta_url", message_text: "Open our catalogue here.", cta_button_text: "Open Catalogue", cta_button_url: "", button_header_text: "", button_footer_text: "" },
    send_catalog: { action_kind: "send_catalog", catalog_message_type: "single_product", catalog_id: "", product_retailer_id: "", product_retailer_ids: "", thumbnail_product_retailer_id: "", catalog_section_title: "Products", message_text: "Please review this product.", button_header_text: "Products", button_footer_text: "" },
    send_form_link: { action_kind: "send_form_link", form_id: false, message_text: "Please fill this short form so our team can help you faster: {{form_url}}" },
    send_payment_link: { action_kind: "send_payment_link", payment_mode: "account_default", message_text: "Here is your payment link: {{payment_url}}" },
    delay: { action_kind: "delay", delay_seconds: 5 },
    api_call: { action_kind: "api_call", http_method: "POST", http_url: "", http_payload: "", http_headers: "", http_query_params: "", http_auth_type: "none", http_auth_token: "", http_username: "", http_password: "", response_variable: "", http_response_path: "" },
    end: { action_kind: "end" },
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
                    <t t-foreach="paletteTypes" t-as="type" t-key="type">
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
                    <i t-attf-class="fa {{nodeTypes[state.editingNode.type] ? nodeTypes[state.editingNode.type].icon : 'fa-cube'}}"></i>
                    <span t-esc="state.editingNode.label"/>
                    <button type="button" class="btn-close" t-on-click="closeDrawer"></button>
                </div>
                <div class="wa-fb-drawer-body">
                    <div class="mb-3">
                        <label class="form-label wa-fb-label">Step Label <i class="fa fa-question-circle wa-fb-help" title="Name shown on the canvas and in the generated step list."></i></label>
                        <input type="text" class="form-control" t-model="state.editingNode.label" t-on-input="saveData"/>
                    </div>
                    
                    <hr/>

                    <t t-if="state.editingNode.type === 'send_text'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Message Text <i class="fa fa-question-circle wa-fb-help" title="Plain WhatsApp text sent to the customer. You can use contact placeholders supported by the send engine."></i></label>
                            <textarea class="form-control" rows="5" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                            <small class="text-muted">Placeholders: &#123;&#123;name&#125;&#125;, &#123;&#123;phone&#125;&#125;, &#123;&#123;email&#125;&#125;, &#123;&#123;company&#125;&#125;, &#123;&#123;last_reply&#125;&#125;.</small>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'send_template'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Template <i class="fa fa-question-circle wa-fb-help" title="Approved WhatsApp template to send from this step."></i></label>
                            <select class="form-select" t-att-value="state.editingNode.config.template_id || ''" t-on-change="(ev) => this.setEditingConfig('template_id', ev.target.value ? Number(ev.target.value) : false)">
                                <option value="">Select a template...</option>
                                <t t-foreach="state.templates" t-as="tpl" t-key="tpl.id">
                                    <option t-att-value="tpl.id" t-esc="tpl.name"/>
                                </t>
                            </select>
                        </div>
                    </t>

                    <t t-if="['send_buttons', 'send_list'].includes(state.editingNode.type)">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Prompt Text <i class="fa fa-question-circle wa-fb-help" title="Question or prompt shown before the options."></i></label>
                            <textarea class="form-control" rows="4" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                            <small class="text-muted">Placeholders are supported. Configure options below or connect this node to next steps.</small>
                        </div>
                        <div class="row">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Header Text</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.button_header_text" t-on-input="saveData"/>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Footer Text</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.button_footer_text" t-on-input="saveData"/>
                            </div>
                        </div>
                        <t t-if="state.editingNode.type === 'send_list'">
                            <div class="row">
                                <div class="col-6 mb-3">
                                    <label class="form-label wa-fb-label">List Button Text</label>
                                    <input type="text" class="form-control" t-model="state.editingNode.config.list_button_text" t-on-input="saveData" placeholder="Choose"/>
                                </div>
                                <div class="col-6 mb-3">
                                    <label class="form-label wa-fb-label">Section Title</label>
                                    <input type="text" class="form-control" t-model="state.editingNode.config.list_section_title" t-on-input="saveData" placeholder="Options"/>
                                </div>
                            </div>
                        </t>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Fallback Route <i class="fa fa-question-circle wa-fb-help" title="Where the flow should go if WhatsApp sends an unmatched button/list payload."></i></label>
                            <select class="form-select" t-att-value="state.editingNode.config.fallback_node_id || ''" t-on-change="(ev) => this.setEditingConfig('fallback_node_id', ev.target.value || '')">
                                <option value="">No fallback route</option>
                                <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                    <option t-att-value="node.id" t-esc="node.label"/>
                                </t>
                            </select>
                        </div>
                        <div class="wa-fb-section-title">Options</div>
                        <t t-foreach="interactiveOptions(state.editingNode)" t-as="opt" t-key="opt._key">
                            <div class="wa-fb-option-row">
                                <div class="row">
                                    <div class="col-6 mb-2">
                                        <label class="form-label wa-fb-label">Text</label>
                                        <input type="text" class="form-control" t-att-value="opt.title || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'title', ev.target.value)"/>
                                    </div>
                                    <div class="col-6 mb-2">
                                        <label class="form-label wa-fb-label">Payload ID</label>
                                        <input type="text" class="form-control" t-att-value="opt.id || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'id', ev.target.value)"/>
                                    </div>
                                </div>
                                <div class="mb-2" t-if="state.editingNode.type === 'send_list'">
                                    <label class="form-label wa-fb-label">Description</label>
                                    <input type="text" class="form-control" t-att-value="opt.description || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'description', ev.target.value)"/>
                                </div>
                                <div class="mb-2" t-if="state.editingNode.type === 'send_buttons'">
                                    <label class="form-label wa-fb-label">Button Action <i class="fa fa-question-circle wa-fb-help" title="Reply waits for a tap. URL/Product sends one special interactive message and continues to the configured route."></i></label>
                                    <select class="form-select" t-att-value="opt.button_action || 'reply'" t-on-change="(ev) => this.updateInteractiveOption(opt._index, 'button_action', ev.target.value)">
                                        <option value="reply">Reply / Route</option>
                                        <option value="url">Open URL</option>
                                        <option value="catalog_product">Send Product Card</option>
                                    </select>
                                </div>
                                <div class="mb-2" t-if="state.editingNode.type === 'send_buttons' &amp;&amp; opt.button_action === 'url'">
                                    <label class="form-label wa-fb-label">URL</label>
                                    <input type="url" class="form-control" t-att-value="opt.url || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'url', ev.target.value)" placeholder="https://..."/>
                                </div>
                                <div class="row" t-if="state.editingNode.type === 'send_buttons' &amp;&amp; opt.button_action === 'catalog_product'">
                                    <div class="col-6 mb-2">
                                        <label class="form-label wa-fb-label">Catalog ID</label>
                                        <input type="text" class="form-control" t-att-value="opt.catalog_id || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'catalog_id', ev.target.value)" placeholder="Account default if empty"/>
                                    </div>
                                    <div class="col-6 mb-2">
                                        <label class="form-label wa-fb-label">Product ID</label>
                                        <input type="text" class="form-control" t-att-value="opt.product_retailer_id || ''" t-on-input="(ev) => this.updateInteractiveOption(opt._index, 'product_retailer_id', ev.target.value)"/>
                                    </div>
                                </div>
                                <div class="mb-2">
                                    <label class="form-label wa-fb-label">Go To Step</label>
                                    <select class="form-select" t-att-value="opt.next_node_id || ''" t-on-change="(ev) => this.updateInteractiveOption(opt._index, 'next_node_id', ev.target.value || '')">
                                        <option value="">No route</option>
                                        <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                            <option t-att-value="node.id" t-esc="node.label"/>
                                        </t>
                                    </select>
                                </div>
                                <button type="button" class="btn btn-outline-danger btn-sm" t-on-click="() => this.removeInteractiveOption(opt._index)">
                                    <i class="fa fa-trash me-1"></i> Remove Option
                                </button>
                            </div>
                        </t>
                        <button type="button" class="btn btn-outline-secondary btn-sm w-100" t-on-click="addInteractiveOption">
                            <i class="fa fa-plus me-1"></i> Add Option
                        </button>
                        <small class="text-muted d-block mt-2">
                            Quick replies support 3 options. List menus support 10 rows.
                        </small>
                    </t>

                    <t t-if="state.editingNode.type === 'send_media'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Media File <i class="fa fa-question-circle wa-fb-help" title="Media Library item sent by this step."></i></label>
                            <select class="form-select" t-att-value="state.editingNode.config.media_id || ''" t-on-change="(ev) => this.setEditingConfig('media_id', ev.target.value ? Number(ev.target.value) : false)">
                                <option value="">Select a media file...</option>
                                <t t-foreach="state.media" t-as="media" t-key="media.id">
                                    <option t-att-value="media.id" t-esc="media.name"/>
                                </t>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Caption <i class="fa fa-question-circle wa-fb-help" title="Optional text caption sent with supported media types."></i></label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'condition'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Condition Type <i class="fa fa-question-circle wa-fb-help" title="How the flow should evaluate the last reply or saved value before routing."></i></label>
                            <select class="form-select" t-model="state.editingNode.config.condition_type" t-on-change="saveData">
                                <option value="keyword_match">Keyword Match</option>
                                <option value="response_contains">Response Contains</option>
                                <option value="json_path">JSON Path</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Source</label>
                            <select class="form-select" t-model="state.editingNode.config.condition_source" t-on-change="saveData">
                                <option value="incoming_text">Current Incoming Text</option>
                                <option value="last_reply">Last Reply</option>
                                <option value="variable">Saved Variable</option>
                                <option value="button_payload">Button/List Payload</option>
                            </select>
                        </div>
                        <div class="mb-3" t-if="state.editingNode.config.condition_source === 'variable'">
                            <label class="form-label wa-fb-label">Variable Name</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.condition_variable" t-on-input="saveData"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Operator</label>
                            <select class="form-select" t-model="state.editingNode.config.condition_operator" t-on-change="saveData">
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
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Match Value <i class="fa fa-question-circle wa-fb-help" title="Value to match. For conditions, label outgoing routes true and false when possible."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.condition_value" t-on-input="saveData"/>
                        </div>
                        <div class="row">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Go To If True</label>
                                <select class="form-select" t-att-value="state.editingNode.config.condition_true_node_id || ''" t-on-change="(ev) => this.setEditingConfig('condition_true_node_id', ev.target.value || '')">
                                    <option value="">First outgoing route</option>
                                    <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                        <option t-att-value="node.id" t-esc="node.label"/>
                                    </t>
                                </select>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Go To If False</label>
                                <select class="form-select" t-att-value="state.editingNode.config.condition_false_node_id || ''" t-on-change="(ev) => this.setEditingConfig('condition_false_node_id', ev.target.value || '')">
                                    <option value="">Second outgoing route</option>
                                    <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                        <option t-att-value="node.id" t-esc="node.label"/>
                                    </t>
                                </select>
                            </div>
                        </div>
                        <div class="wa-fb-section-title">Multi-branch Routes</div>
                        <t t-foreach="conditionBranches(state.editingNode)" t-as="branch" t-key="branch._key">
                            <div class="wa-fb-option-row">
                                <div class="row">
                                    <div class="col-6 mb-2">
                                        <label class="form-label wa-fb-label">Label</label>
                                        <input type="text" class="form-control" t-att-value="branch.name || ''" t-on-input="(ev) => this.updateConditionBranch(branch._index, 'name', ev.target.value)"/>
                                    </div>
                                    <div class="col-6 mb-2">
                                        <label class="form-label wa-fb-label">Operator</label>
                                        <select class="form-select" t-att-value="branch.operator || 'contains'" t-on-change="(ev) => this.updateConditionBranch(branch._index, 'operator', ev.target.value)">
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
                                    </div>
                                </div>
                                <div class="mb-2">
                                    <label class="form-label wa-fb-label">Value</label>
                                    <input type="text" class="form-control" t-att-value="branch.value || ''" t-on-input="(ev) => this.updateConditionBranch(branch._index, 'value', ev.target.value)"/>
                                </div>
                                <div class="mb-2">
                                    <label class="form-label wa-fb-label">Go To Step</label>
                                    <select class="form-select" t-att-value="branch.next_node_id || ''" t-on-change="(ev) => this.updateConditionBranch(branch._index, 'next_node_id', ev.target.value || '')">
                                        <option value="">No route</option>
                                        <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                            <option t-att-value="node.id" t-esc="node.label"/>
                                        </t>
                                    </select>
                                </div>
                                <button type="button" class="btn btn-outline-danger btn-sm" t-on-click="() => this.removeConditionBranch(branch._index)">
                                    <i class="fa fa-trash me-1"></i> Remove Branch
                                </button>
                            </div>
                        </t>
                        <button type="button" class="btn btn-outline-secondary btn-sm w-100" t-on-click="addConditionBranch">
                            <i class="fa fa-plus me-1"></i> Add Branch
                        </button>
                    </t>

                    <t t-if="state.editingNode.type === 'wait_reply'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Response Variable <i class="fa fa-question-circle wa-fb-help" title="Variable name used to store the customer's next reply. Conditions and API payloads can use it later."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.response_variable" t-on-input="saveData" placeholder="e.g. user_choice"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Save Reply <i class="fa fa-question-circle wa-fb-help" title="Keep this on when the next customer reply should be available to later steps."></i></label>
                            <input type="checkbox" class="form-check-input" t-att-checked="state.editingNode.config.save_response !== false" t-on-change="(ev) => this.setEditingConfig('save_response', ev.target.checked)"/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'ask_question'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Question Text</label>
                            <textarea class="form-control" rows="4" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Answer Variable</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.response_variable" t-on-input="saveData" placeholder="customer_requirement"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Answer Type</label>
                            <select class="form-select" t-model="state.editingNode.config.input_validation_type" t-on-change="saveData">
                                <option value="text">Text</option>
                                <option value="number">Number</option>
                                <option value="email">Email</option>
                                <option value="phone">Phone</option>
                                <option value="city">City</option>
                                <option value="media">File / Media</option>
                                <option value="location">Location</option>
                            </select>
                        </div>
                        <div class="row">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Max Attempts</label>
                                <input type="number" class="form-control" t-model="state.editingNode.config.max_attempts" t-on-input="saveData"/>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">No-reply Timeout</label>
                                <input type="number" class="form-control" t-model="state.editingNode.config.timeout_minutes" t-on-input="saveData"/>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Invalid Answer Message</label>
                            <textarea class="form-control" rows="2" t-model="state.editingNode.config.invalid_message" t-on-input="saveData"></textarea>
                        </div>
                        <div class="row">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Go To On Invalid</label>
                                <select class="form-select" t-att-value="state.editingNode.config.invalid_node_id || ''" t-on-change="(ev) => this.setEditingConfig('invalid_node_id', ev.target.value || '')">
                                    <option value="">Repeat question</option>
                                    <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                        <option t-att-value="node.id" t-esc="node.label"/>
                                    </t>
                                </select>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Go To On No Reply</label>
                                <select class="form-select" t-att-value="state.editingNode.config.timeout_node_id || ''" t-on-change="(ev) => this.setEditingConfig('timeout_node_id', ev.target.value || '')">
                                    <option value="">No no-reply route</option>
                                    <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                        <option t-att-value="node.id" t-esc="node.label"/>
                                    </t>
                                </select>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Fallback Route</label>
                            <select class="form-select" t-att-value="state.editingNode.config.fallback_node_id || ''" t-on-change="(ev) => this.setEditingConfig('fallback_node_id', ev.target.value || '')">
                                <option value="">No fallback route</option>
                                <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                    <option t-att-value="node.id" t-esc="node.label"/>
                                </t>
                            </select>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'trigger'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Trigger Mode <i class="fa fa-question-circle wa-fb-help" title="Defines when this flow should start. Keyword is the normal inbound-chat trigger."></i></label>
                            <select class="form-select" t-model="state.editingNode.config.trigger_type" t-on-change="saveData">
                                <option value="keyword">Keyword Match</option>
                                <option value="first_message">First Message</option>
                                <option value="manual">Manual Trigger</option>
                                <option value="schedule">Scheduled</option>
                                <option value="webhook">Webhook Event</option>
                            </select>
                        </div>
                        <t t-if="state.editingNode.config.trigger_type === 'keyword'">
                            <div class="mb-3">
                                <label class="form-label wa-fb-label">Keywords <i class="fa fa-question-circle wa-fb-help" title="Comma-separated words or phrases that start the flow from inbound messages."></i></label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.keywords" t-on-input="saveData" placeholder="hello, hi, start"/>
                            </div>
                        </t>
                        <t t-if="state.editingNode.config.trigger_type === 'webhook'">
                            <div class="mb-3">
                                <label class="form-label wa-fb-label">Webhook Event <i class="fa fa-question-circle wa-fb-help" title="Internal event name used by custom integrations to start this flow."></i></label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.webhook_event" t-on-input="saveData" placeholder="order.created"/>
                            </div>
                        </t>
                        <t t-if="state.editingNode.config.trigger_type === 'schedule'">
                            <div class="mb-3">
                                <label class="form-label wa-fb-label">Schedule Pattern <i class="fa fa-question-circle wa-fb-help" title="Cron-style schedule expression for planned execution."></i></label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.schedule_pattern" t-on-input="saveData" placeholder="0 9 * * *"/>
                            </div>
                        </t>
                    </t>

                    <t t-if="state.editingNode.type === 'assign_agent'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Agent <i class="fa fa-question-circle wa-fb-help" title="User who will own the chat after this step runs."></i></label>
                            <select class="form-select" t-att-value="state.editingNode.config.assign_user_id || ''" t-on-change="(ev) => this.setEditingConfig('assign_user_id', ev.target.value ? Number(ev.target.value) : false)">
                                <option value="">Select an agent...</option>
                                <t t-foreach="state.users" t-as="user" t-key="user.id">
                                    <option t-att-value="user.id" t-esc="user.name"/>
                                </t>
                            </select>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'assign_team'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Team Members</label>
                            <select class="form-select" multiple="true" t-att-value="state.editingNode.config.assign_team_member_ids || []" t-on-change="(ev) => this.setEditingConfig('assign_team_member_ids', Array.from(ev.target.selectedOptions).map((option) => Number(option.value)))">
                                <t t-foreach="state.teamMembers" t-as="member" t-key="member.id">
                                    <option t-att-value="member.id" t-esc="member.name"/>
                                </t>
                            </select>
                            <small class="text-muted">The backend picks the least busy available user from these members.</small>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'add_tag'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Tag <i class="fa fa-question-circle wa-fb-help" title="Contact tag applied for segmentation and later filtering."></i></label>
                            <select class="form-select" t-att-value="state.editingNode.config.assign_tag_id || ''" t-on-change="(ev) => this.setEditingConfig('assign_tag_id', ev.target.value ? Number(ev.target.value) : false)">
                                <option value="">Select a tag...</option>
                                <t t-foreach="state.tags" t-as="tag" t-key="tag.id">
                                    <option t-att-value="tag.id" t-esc="tag.name"/>
                                </t>
                            </select>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'create_lead'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Lead Note <i class="fa fa-question-circle wa-fb-help" title="Optional note copied into the CRM lead created from this chat."></i></label>
                            <textarea class="form-control" rows="4" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                            <small class="text-muted">Supports placeholders such as &#123;&#123;name&#125;&#125; and &#123;&#123;last_message&#125;&#125;.</small>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'chat_status'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Chat Status</label>
                            <select class="form-select" t-model="state.editingNode.config.chat_status" t-on-change="saveData">
                                <option value="open">Open / Reopen</option>
                                <option value="snoozed">Snoozed</option>
                                <option value="resolved">Resolved</option>
                                <option value="archived">Archived</option>
                            </select>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'update_contact'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Attribute Name</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.contact_attribute_name" t-on-input="saveData" placeholder="city"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Attribute Value</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.contact_attribute_value" t-on-input="saveData" placeholder="{{last_reply}}"/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'set_variable'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Variable Name <i class="fa fa-question-circle wa-fb-help" title="Name used to store a value for later steps, conditions, or API payloads."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.variable_name" t-on-input="saveData" placeholder="lead_source"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Variable Value <i class="fa fa-question-circle wa-fb-help" title="Value saved under this variable name."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.variable_value" t-on-input="saveData" placeholder="WhatsApp"/>
                            <small class="text-muted">Can include placeholders, for example &#123;&#123;last_reply&#125;&#125;.</small>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'send_cta_url'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Message</label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                        </div>
                        <div class="row">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Header Text</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.button_header_text" t-on-input="saveData"/>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Footer Text</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.button_footer_text" t-on-input="saveData"/>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Button Text</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.cta_button_text" t-on-input="saveData" placeholder="Open Catalogue"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Button URL <i class="fa fa-question-circle wa-fb-help" title="Leave blank to use the account Shop / Catalogue URL."></i></label>
                            <input type="url" class="form-control" t-model="state.editingNode.config.cta_button_url" t-on-input="saveData" placeholder="https://..."/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'send_catalog'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Catalog Message Type</label>
                            <select class="form-select" t-model="state.editingNode.config.catalog_message_type" t-on-change="saveData">
                                <option value="catalog_message">Open Full Catalog / Shop</option>
                                <option value="single_product">Single Product Card</option>
                                <option value="multi_product">Multi-Product List</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Catalog ID <i class="fa fa-question-circle wa-fb-help" title="Leave blank to use the account default Meta Catalog ID."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.catalog_id" t-on-input="saveData"/>
                        </div>
                        <div class="mb-3" t-if="(state.editingNode.config.catalog_message_type || 'single_product') !== 'multi_product'">
                            <label class="form-label wa-fb-label">Product Retailer ID</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.product_retailer_id" t-on-input="saveData"/>
                        </div>
                        <div class="mb-3" t-if="state.editingNode.config.catalog_message_type === 'multi_product'">
                            <label class="form-label wa-fb-label">Product Retailer IDs</label>
                            <textarea class="form-control" rows="4" t-model="state.editingNode.config.product_retailer_ids" t-on-input="saveData" placeholder="One product/content ID per line"></textarea>
                        </div>
                        <div class="mb-3" t-if="state.editingNode.config.catalog_message_type === 'catalog_message'">
                            <label class="form-label wa-fb-label">Thumbnail Product ID</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.thumbnail_product_retailer_id" t-on-input="saveData"/>
                        </div>
                        <div class="mb-3" t-if="state.editingNode.config.catalog_message_type === 'multi_product'">
                            <label class="form-label wa-fb-label">Section Title</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.catalog_section_title" t-on-input="saveData" placeholder="Products"/>
                        </div>
                        <div class="row" t-if="state.editingNode.config.catalog_message_type === 'multi_product'">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Header Text</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.button_header_text" t-on-input="saveData"/>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Footer Text</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.button_footer_text" t-on-input="saveData"/>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Message</label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.message_text" t-on-input="saveData"></textarea>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'send_form_link'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Message</label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.message_text" t-on-input="saveData" placeholder="Please fill this short form: {{form_url}}"></textarea>
                            <small class="text-muted">Use <code>{{form_url}}</code>. If no form is selected, the account default form is used.</small>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Form</label>
                            <select class="form-select" t-att-value="state.editingNode.config.form_id || ''" t-on-change="(ev) => this.setEditingConfig('form_id', ev.target.value || false)">
                                <option value="">Use Account Default Form</option>
                                <t t-foreach="state.forms" t-as="form" t-key="form.id">
                                    <option t-att-value="form.id" t-esc="form.name"/>
                                </t>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Fallback Route</label>
                            <select class="form-select" t-att-value="state.editingNode.config.fallback_node_id || ''" t-on-change="(ev) => this.setEditingConfig('fallback_node_id', ev.target.value || '')">
                                <option value="">Stop with clear error if form is missing</option>
                                <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                    <option t-att-value="node.id" t-esc="node.label"/>
                                </t>
                            </select>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'send_payment_link'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Message</label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.message_text" t-on-input="saveData" placeholder="Here is your payment link: {{payment_url}}"></textarea>
                            <small class="text-muted">Use <code>{{payment_url}}</code>. Payment behavior comes from the WhatsApp Account payment-link mode.</small>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Payment Source</label>
                            <select class="form-select" t-model="state.editingNode.config.payment_mode" t-on-change="saveData">
                                <option value="account_default">Account Default</option>
                                <option value="latest_invoice">Latest Unpaid Invoice</option>
                                <option value="latest_quote">Latest Quotation</option>
                                <option value="manual_url">Manual URL From Account</option>
                            </select>
                            <small class="text-muted">Flows resolve the actual invoice/quote from the current chat customer.</small>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Fallback Route</label>
                            <select class="form-select" t-att-value="state.editingNode.config.fallback_node_id || ''" t-on-change="(ev) => this.setEditingConfig('fallback_node_id', ev.target.value || '')">
                                <option value="">Stop with clear error if payment link is unavailable</option>
                                <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                    <option t-att-value="node.id" t-esc="node.label"/>
                                </t>
                            </select>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'delay'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Delay Seconds <i class="fa fa-question-circle wa-fb-help" title="Number of seconds to pause before continuing. Maximum backend-supported delay is 86400 seconds."></i></label>
                            <input type="number" class="form-control" t-model="state.editingNode.config.delay_seconds" t-on-input="saveData"/>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'api_call'">
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Method <i class="fa fa-question-circle wa-fb-help" title="HTTP method used for the external webhook request."></i></label>
                            <select class="form-select" t-model="state.editingNode.config.http_method" t-on-change="saveData">
                                <option value="GET">GET</option>
                                <option value="POST">POST</option>
                                <option value="PUT">PUT</option>
                                <option value="PATCH">PATCH</option>
                                <option value="DELETE">DELETE</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">URL <i class="fa fa-question-circle wa-fb-help" title="External webhook URL called when this step runs."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.http_url" t-on-input="saveData"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Auth Type</label>
                            <select class="form-select" t-model="state.editingNode.config.http_auth_type" t-on-change="saveData">
                                <option value="none">None</option>
                                <option value="bearer">Bearer Token</option>
                                <option value="basic">Basic Auth</option>
                            </select>
                        </div>
                        <div class="mb-3" t-if="state.editingNode.config.http_auth_type === 'bearer'">
                            <label class="form-label wa-fb-label">Bearer Token</label>
                            <input type="password" class="form-control" t-model="state.editingNode.config.http_auth_token" t-on-input="saveData"/>
                        </div>
                        <div class="row" t-if="state.editingNode.config.http_auth_type === 'basic'">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Username</label>
                                <input type="text" class="form-control" t-model="state.editingNode.config.http_username" t-on-input="saveData"/>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Password</label>
                                <input type="password" class="form-control" t-model="state.editingNode.config.http_password" t-on-input="saveData"/>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Payload JSON <i class="fa fa-question-circle wa-fb-help" title="Optional JSON body for POST/PUT requests."></i></label>
                            <textarea class="form-control" rows="4" t-model="state.editingNode.config.http_payload" t-on-input="saveData"></textarea>
                            <small class="text-muted">Supports placeholders, for example phone/name values from the current chat.</small>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Headers JSON</label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.http_headers" t-on-input="saveData"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Query Params JSON</label>
                            <textarea class="form-control" rows="3" t-model="state.editingNode.config.http_query_params" t-on-input="saveData"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Response Variable <i class="fa fa-question-circle wa-fb-help" title="Optional variable name where the API response should be stored."></i></label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.response_variable" t-on-input="saveData"/>
                        </div>
                        <div class="mb-3">
                            <label class="form-label wa-fb-label">Response JSON Path</label>
                            <input type="text" class="form-control" t-model="state.editingNode.config.http_response_path" t-on-input="saveData" placeholder="data.status"/>
                        </div>
                        <div class="row">
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Go To On Success</label>
                                <select class="form-select" t-att-value="state.editingNode.config.http_success_node_id || ''" t-on-change="(ev) => this.setEditingConfig('http_success_node_id', ev.target.value || '')">
                                    <option value="">Default next step</option>
                                    <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                        <option t-att-value="node.id" t-esc="node.label"/>
                                    </t>
                                </select>
                            </div>
                            <div class="col-6 mb-3">
                                <label class="form-label wa-fb-label">Go To On Failure</label>
                                <select class="form-select" t-att-value="state.editingNode.config.http_failure_node_id || ''" t-on-change="(ev) => this.setEditingConfig('http_failure_node_id', ev.target.value || '')">
                                    <option value="">Raise failure</option>
                                    <t t-foreach="routeableNodes(state.editingNode)" t-as="node" t-key="node.id">
                                        <option t-att-value="node.id" t-esc="node.label"/>
                                    </t>
                                </select>
                            </div>
                        </div>
                    </t>

                    <t t-if="state.editingNode.type === 'end'">
                        <div class="alert alert-light border">
                            <i class="fa fa-info-circle me-1"></i>
                            End Flow marks this path complete and does not require extra settings.
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
        this.orm = useService("orm");
        this.nodeTypes = NODE_TYPES;
        this.paletteTypes = PALETTE_TYPES;
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
            templates: [],
            media: [],
            users: [],
            tags: [],
            teamMembers: [],
            forms: [],
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
            this.loadRelationalData();
            window.addEventListener("mousemove", this._boundMouseMove);
            window.addEventListener("mouseup", this._boundMouseUp);
            setTimeout(() => animateFlowBuilderIn(this.canvasWrap.el, { level: "subtle" }), 0);
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
                this.state.nodes = data.nodes.map((node) => {
                    const type = this.normalizeNodeType(node);
                    return {
                        id: node.id,
                        type,
                        label: node.label || "Step",
                        x: Number(node.x || 0),
                        y: Number(node.y || 0),
                        config: this.normalizeNodeConfig(type, node.config),
                    };
                });
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

    getAccountId() {
        return recordId(this.props.record.data.account_id);
    }

    async loadRelationalData() {
        try {
            const accountId = this.getAccountId();
            const templatesDomain = [["status", "=", "approved"]];
            if (accountId) {
                templatesDomain.push(["account_id", "in", [accountId, false]]);
            }
            const mediaDomain = accountId
                ? [["account_id", "=", accountId], ["active", "=", true]]
                : [["active", "=", true]];
            const teamDomain = accountId
                ? [["account_id", "=", accountId], ["user_id", "!=", false]]
                : [["user_id", "!=", false]];
            const formsDomain = accountId
                ? [["active", "=", true], "|", ["account_id", "=", accountId], ["account_id", "=", false]]
                : [["active", "=", true]];
            const [templates, media, users, tags, teamMembers, forms] = await Promise.all([
                this.orm.searchRead("whatsapp.template", templatesDomain, ["id", "name"]),
                this.orm.searchRead("whatsapp.media.library", mediaDomain, ["id", "name"]),
                this.orm.searchRead("res.users", [["active", "=", true]], ["id", "name"]),
                this.orm.searchRead("res.partner.category", [], ["id", "name"]),
                this.orm.searchRead("whatsapp.team.member", teamDomain, ["id", "user_id", "role"]),
                this.orm.searchRead("whatsapp.form", formsDomain, ["id", "name"]),
            ]);
            this.state.templates = templates || [];
            this.state.media = media || [];
            this.state.users = users || [];
            this.state.tags = tags || [];
            this.state.teamMembers = (teamMembers || []).map((member) => ({
                id: member.id,
                name: Array.isArray(member.user_id) ? member.user_id[1] : `Member #${member.id}`,
                role: member.role,
            }));
            this.state.forms = forms || [];
        } catch (error) {
            console.warn("[WA Flow Builder] Could not load dropdown options.", error);
        }
    }

    saveData() {
        const nodes = this.state.nodes.map((node) => this.nodeForSave(node));
        const connections = this.state.connections
            .filter((conn) => conn && conn.from && conn.to && conn.from !== conn.to)
            .map((conn) => ({
                from: conn.from,
                to: conn.to,
                label: conn.label || "",
            }));
        const payload = JSON.stringify({
            nodes,
            edges: connections.map((conn, index) => ({
                id: `edge_${conn.from}_${conn.to}_${index + 1}`,
                ...conn,
                config: {},
            })),
            connections,
            nextId: this.state.nextId,
        });
        this.props.record.update({ [this.props.name]: payload });
    }

    nodeForSave(node) {
        const type = this.normalizeNodeType(node);
        const config = this.normalizeNodeConfig(type, node.config);
        const subtypeByType = {
            send_text: "text",
            send_template: "template",
            send_buttons: "buttons",
            send_list: "list",
            send_media: "media",
            wait_reply: "wait_reply",
            ask_question: "ask_question",
            assign_agent: "assign_agent",
            assign_team: "assign_team",
            add_tag: "add_label",
            create_lead: "create_lead",
            chat_status: "chat_status",
            update_contact: "update_contact",
            set_variable: "set_variable",
            send_cta_url: "send_cta_url",
            send_catalog: "send_catalog",
            send_form_link: "send_form_link",
            send_payment_link: "send_payment_link",
            delay: "delay",
            api_call: "api_call",
            end: "end",
        };
        const messageTypes = new Set(["send_text", "send_template", "send_buttons", "send_list", "send_media"]);
        const category = type === "trigger" ? "trigger" : type === "condition" ? "condition" : messageTypes.has(type) ? "message" : "action";
        const subtype = subtypeByType[type] || type;
        return {
            id: node.id,
            type: category,
            subtype,
            legacy_type: type,
            label: node.label || "Step",
            x: Number(node.x || 0),
            y: Number(node.y || 0),
            config,
        };
    }

    normalizeNodeType(node) {
        const config = typeof node.config === "object" && node.config ? node.config : {};
        const type = node.type || "send_text";
        if (type === "message") {
            const mode = config.message_mode || config.subtype || node.subtype || "text";
            return {
                text: "send_text",
                template: "send_template",
                buttons: "send_buttons",
                list: "send_list",
                media: "send_media",
            }[mode] || "send_text";
        }
        if (type === "action") {
            const kind = config.action_kind || config.action_type || config.subtype || node.subtype || "assign_agent";
            return {
                assign_agent: "assign_agent",
                transfer: "assign_agent",
                add_label: "add_tag",
                add_tag: "add_tag",
                assign_tag: "add_tag",
                create_lead: "create_lead",
                set_variable: "set_variable",
                wait_reply: "wait_reply",
                wait_response: "wait_reply",
                ask_question: "ask_question",
                api_call: "api_call",
                http_request: "api_call",
                assign_team: "assign_team",
                chat_status: "chat_status",
                update_contact: "update_contact",
                send_cta_url: "send_cta_url",
                send_catalog: "send_catalog",
                send_form_link: "send_form_link",
                send_payment_link: "send_payment_link",
                delay: "delay",
                end: "end",
            }[kind] || "assign_agent";
        }
        if (type === "wait_response") return "wait_reply";
        if (type === "ask_question") return "ask_question";
        if (type === "transfer") return "assign_agent";
        if (type === "assign_tag") return "add_tag";
        if (type === "http_request") return "api_call";
        return NODE_TYPES[type] ? type : "send_text";
    }

    normalizeNodeConfig(type, config) {
        const normalized = {
            ...(DEFAULT_CONFIG[type] || {}),
            ...(typeof config === "object" && config ? config : {}),
        };
        if (normalized.text && !normalized.message_text) {
            normalized.message_text = normalized.text;
        }
        if (normalized.variable_name && type === "wait_reply" && !normalized.response_variable) {
            normalized.response_variable = normalized.variable_name;
        }
        if (type === "send_list") {
            normalized.message_mode = "list";
            normalized.options = Array.isArray(normalized.options) ? normalized.options : [];
        }
        if (type === "send_buttons") {
            normalized.message_mode = "buttons";
            normalized.options = Array.isArray(normalized.options) ? normalized.options : [];
        }
        if (type === "add_tag" && normalized.action_kind === "add_tag") {
            normalized.action_kind = "add_label";
        }
        if (type === "send_form_link") {
            normalized.action_kind = "send_form_link";
            normalized.form_id = recordId(normalized.form_id);
        }
        if (type === "send_payment_link") {
            normalized.action_kind = "send_payment_link";
            normalized.payment_mode = normalized.payment_mode || "account_default";
        }
        return normalized;
    }

    getNodePreview(node) {
        if (node.type === "message") return node.config.message_text || node.config.text || node.config.message_mode || "Message node";
        if (node.type === "action") return node.config.action_kind || node.config.action_type || "Action node";
        if (node.type === "send_text") return node.config.message_text || node.config.text || "Empty message...";
        if (node.type === "send_template") return node.config.template_id || "No template...";
        if (node.type === "send_buttons" || node.type === "send_list") return node.config.message_text || "Button prompt...";
        if (node.type === "send_media") return node.config.media_id ? `Media #${node.config.media_id}` : "No media...";
        if (node.type === "condition") return `${node.config.condition_type || "No condition"}: ${node.config.condition_value || ""}`;
        if (node.type === "trigger") return node.config.trigger_type || "keyword";
        if (node.type === "wait_reply") return `Save as ${node.config.response_variable || node.config.variable_name || "last_reply"}`;
        if (node.type === "ask_question") return `Ask: ${node.config.response_variable || "customer_answer"} (${node.config.input_validation_type || "text"})`;
        if (node.type === "assign_agent") return node.config.assign_user_id ? `User #${node.config.assign_user_id}` : "No agent...";
        if (node.type === "assign_team") return "Least busy team member";
        if (node.type === "add_tag") return node.config.assign_tag_id ? `Tag #${node.config.assign_tag_id}` : "No tag...";
        if (node.type === "create_lead") return node.config.message_text || "Create CRM lead";
        if (node.type === "chat_status") return `Set ${node.config.chat_status || "open"}`;
        if (node.type === "update_contact") return node.config.contact_attribute_name || "No attribute...";
        if (node.type === "set_variable") return node.config.variable_name ? `${node.config.variable_name} = ${node.config.variable_value || ""}` : "No variable...";
        if (node.type === "send_cta_url") return node.config.cta_button_url || "No URL...";
        if (node.type === "send_catalog") {
            const mode = node.config.catalog_message_type || "single_product";
            if (mode === "catalog_message") return "Open full catalog/shop";
            if (mode === "multi_product") return node.config.product_retailer_ids || "No products...";
            return node.config.product_retailer_id || "No product...";
        }
        if (node.type === "send_form_link") {
            if (node.config.form_id) {
                const form = this.state.forms.find((item) => item.id === Number(node.config.form_id));
                return form ? `Form: ${form.name}` : `Form #${node.config.form_id}`;
            }
            return "Use account default form";
        }
        if (node.type === "send_payment_link") return "Send account payment link";
        if (node.type === "delay") return `${node.config.delay_seconds || 0} seconds`;
        if (node.type === "api_call") return `${node.config.http_method || "POST"} ${node.config.http_url || ""}`.trim() || "No URL...";
        if (node.type === "end") return "Finish path";
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
            config: this.normalizeNodeConfig(type, {}),
        };
        this.state.nodes.push(node);
        this.state.selectedNode = node.id;
        this.saveData();
        setTimeout(() => animateFlowNodeFocus(this.canvasWrap.el, { level: "subtle" }), 0);
    }

    onMouseDownNode(ev, node) {
        this.state.selectedNode = node.id;
        setTimeout(() => animateFlowNodeFocus(this.canvasWrap.el, { level: "subtle" }), 0);
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
        node.type = this.normalizeNodeType(node);
        node.config = this.normalizeNodeConfig(node.type, node.config);
        
        // Slight delay to trigger CSS transition
        setTimeout(() => {
            this.state.drawerOpen = true;
            animateFlowNodeFocus(this.canvasWrap.el, { level: "subtle" });
        }, 10);
    }

    setEditingConfig(field, value) {
        if (!this.state.editingNode) {
            return;
        }
        this.state.editingNode.config[field] = value;
        this.saveData();
    }

    routeableNodes(currentNode) {
        return this.state.nodes.filter((node) => node.id !== currentNode?.id && node.type !== "trigger");
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
        if (!this.state.editingNode) return;
        const mode = this.state.editingNode.type === "send_list" ? "list" : "buttons";
        const limit = mode === "list" ? 10 : 3;
        const options = Array.isArray(this.state.editingNode.config.options)
            ? [...this.state.editingNode.config.options]
            : [];
        if (options.length >= limit) {
            return;
        }
        const number = options.length + 1;
        options.push({
            title: `Option ${number}`,
            id: `${this.state.editingNode.id}_option_${number}`,
            description: "",
            button_action: "reply",
            url: "",
            catalog_id: "",
            product_retailer_id: "",
            next_node_id: "",
        });
        this.state.editingNode.config.options = options;
        this.saveData();
    }

    updateInteractiveOption(index, field, value) {
        if (!this.state.editingNode) return;
        const options = Array.isArray(this.state.editingNode.config.options)
            ? [...this.state.editingNode.config.options]
            : [];
        options[index] = { ...(options[index] || {}), [field]: value };
        this.state.editingNode.config.options = options;
        this.saveData();
    }

    removeInteractiveOption(index) {
        if (!this.state.editingNode) return;
        const options = Array.isArray(this.state.editingNode.config.options)
            ? [...this.state.editingNode.config.options]
            : [];
        options.splice(index, 1);
        this.state.editingNode.config.options = options;
        this.saveData();
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
        if (!this.state.editingNode) return;
        const branches = Array.isArray(this.state.editingNode.config.condition_branches)
            ? [...this.state.editingNode.config.condition_branches]
            : [];
        const number = branches.length + 1;
        branches.push({
            name: `Branch ${number}`,
            operator: "contains",
            value: "",
            next_node_id: "",
        });
        this.state.editingNode.config.condition_branches = branches;
        this.saveData();
    }

    updateConditionBranch(index, field, value) {
        if (!this.state.editingNode) return;
        const branches = Array.isArray(this.state.editingNode.config.condition_branches)
            ? [...this.state.editingNode.config.condition_branches]
            : [];
        branches[index] = { ...(branches[index] || {}), [field]: value };
        this.state.editingNode.config.condition_branches = branches;
        this.saveData();
    }

    removeConditionBranch(index) {
        if (!this.state.editingNode) return;
        const branches = Array.isArray(this.state.editingNode.config.condition_branches)
            ? [...this.state.editingNode.config.condition_branches]
            : [];
        branches.splice(index, 1);
        this.state.editingNode.config.condition_branches = branches;
        this.saveData();
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
