/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, xml, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ElsxBankReconciliationApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            linesToReconcile: [],
            loading: true,
        });

        this.loadInitialData();
    }

    async loadInitialData() {
        // Example: Call the Python backend to fetch lines that need reconciliation
        // This integrates with the fuzzy matching ML logic we built in Python
        // const lines = await this.orm.call("account.bank.statement.line", "search_read", [[['is_reconciled', '=', false]]]);
        
        // Mock data to show the UI structure
        this.state.linesToReconcile = [
            { id: 1, date: '2026-04-07', label: 'AWS HOSTING INC', amount: -149.00, suggested_partner: 'Amazon Web Services' },
            { id: 2, date: '2026-04-08', label: 'CLIENT DEPOSIT', amount: 5000.00, suggested_partner: 'Acme Corp' }
        ];
        this.state.loading = false;
    }

    async triggerAutoReconcile(lineId) {
        // Trigger the Python hook
        console.log("Triggering Python AI auto-reconcile for line:", lineId);
        // await this.orm.call("account.bank.statement.line", "action_elsx_auto_reconcile", [lineId]);
    }
}

ElsxBankReconciliationApp.template = xml`
    <div class="elsx_reconciliation_dashboard o_action_manager">
        <div class="o_control_panel">
            <div class="o_cp_top">
                <div class="o_cp_top_left">
                    <ol class="breadcrumb" role="navigation">
                        <li class="breadcrumb-item active">AI Bank Reconciliation</li>
                    </ol>
                </div>
            </div>
        </div>
        <div class="o_content p-4">
            <div t-if="state.loading" class="text-center">
                <i class="fa fa-circle-o-notch fa-spin fa-2x"></i>
                <p>Loading AI Suggestions...</p>
            </div>
            <div t-else="">
                <div class="alert alert-info">
                    <i class="fa fa-magic"></i> ELSX Bank AI is analyzing <t t-esc="state.linesToReconcile.length"/> unreconciled lines.
                </div>
                
                <t t-foreach="state.linesToReconcile" t-as="line" t-key="line.id">
                    <div class="card mb-3 shadow-sm border-0">
                        <div class="card-body d-flex justify-content-between align-items-center">
                            <div>
                                <h5 class="card-title text-primary"><t t-esc="line.label"/></h5>
                                <h6 class="card-subtitle mb-2 text-muted"><t t-esc="line.date"/> • <strong><t t-esc="line.amount"/></strong></h6>
                            </div>
                            <div class="text-end">
                                <span class="badge bg-success mb-2">AI Suggestion: <t t-esc="line.suggested_partner"/></span>
                                <br/>
                                <button class="btn btn-primary" t-on-click="() => this.triggerAutoReconcile(line.id)">
                                    <i class="fa fa-check"></i> Validate
                                </button>
                            </div>
                        </div>
                    </div>
                </t>
            </div>
        </div>
    </div>
`;

// Link this component to the precise action tag defined in the XML
registry.category("actions").add("elsx_bank_reconciliation_client_action", ElsxBankReconciliationApp);
