/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, xml, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ElsxBarcodeApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            lastScanned: "",
            scans: [],
            status: "Ready",
            barcodeBuffer: "",
            lastKeyTime: Date.now()
        });

        this.handleKeyDown = this.handleKeyDown.bind(this);
        
        onMounted(() => {
            // Hardware barcode scanners act as extremely fast keyboards.
            // We listen globally on the document to catch scans without needing an active text input.
            document.addEventListener('keydown', this.handleKeyDown);
            console.log("ELSX Enterprise Hardware Scanner Ready");
        });

        onWillUnmount(() => {
            document.removeEventListener('keydown', this.handleKeyDown);
        });
    }

    handleKeyDown(ev) {
        const currentTime = Date.now();
        // If more than 50ms since last key, it's likely human typing, reset buffer
        if (currentTime - this.state.lastKeyTime > 50) {
            this.state.barcodeBuffer = "";
        }
        
        this.state.lastKeyTime = currentTime;

        // Enter key signifies the end of a hardware barcode scan
        if (ev.key === 'Enter') {
            if (this.state.barcodeBuffer.length > 3) {
                this.processBarcode(this.state.barcodeBuffer);
                ev.preventDefault();
                this.state.barcodeBuffer = "";
            }
        } else if (ev.key.length === 1) { // Ignore shift, ctrl, etc.
            this.state.barcodeBuffer += ev.key;
        }
    }

    async processBarcode(barcode) {
        this.state.status = "Searching...";
        this.state.lastScanned = barcode;
        
        try {
            // Check if the barcode matches a product
            const products = await this.orm.searchRead('product.product', [['barcode', '=', barcode]], ['name', 'default_code']);
            
            if (products.length > 0) {
                const product = products[0];
                this.state.status = `Matched: ${product.name}`;
                this.notification.add(`Scanned ${product.name}`, { type: 'success' });
                this.state.scans.unshift(product);
                
                // Further logic to update stock.picking or stock.move.line would go here
            } else {
                this.state.status = "User/Product Not Found";
                this.notification.add(`Unknown Barcode: ${barcode}`, { type: 'danger' });
            }
        } catch (e) {
            console.error("Barcode RPC Error:", e);
            this.state.status = "Network Error";
        }
    }
}

ElsxBarcodeApp.template = xml`
    <div class="elsx_barcode_app bg-dark text-white p-4" style="min-height: 100vh;">
        <div class="text-center mb-5">
            <h1 class="display-4"><i class="fa fa-barcode"></i> ELSX Warehouse Scanner</h1>
            <h2 t-attf-class="mt-3 {{ state.status.includes('Matched') ? 'text-success' : 'text-warning' }}">
                <t t-esc="state.status"/>
            </h2>
            <h4 class="text-muted">Last Data: <t t-esc="state.lastScanned"/></h4>
        </div>

        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <ul class="list-group text-dark">
                        <t t-foreach="state.scans" t-as="scan" t-key="scan.id">
                            <li class="list-group-item d-flex justify-content-between align-items-center mb-2 rounded shadow-sm fs-4">
                                <span><i class="fa fa-box me-3"></i><t t-esc="scan.name"/></span>
                                <span class="badge bg-primary rounded-pill"><i class="fa fa-check"></i> Added</span>
                            </li>
                        </t>
                    </ul>
                </div>
            </div>
        </div>
    </div>
`;

registry.category("actions").add("elsx_barcode_client_action", ElsxBarcodeApp);
