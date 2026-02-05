/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { onMounted } from "@odoo/owl";

patch(WebClient.prototype, {
    setup() {
        super.setup();
        onMounted(() => {
            // Remove Odoo Enterprise upgrade nags
            const upgradeButtons = document.querySelectorAll('.o_main_navbar .o_enterprise_label, .o_upgrade_button');
            upgradeButtons.forEach(btn => btn.style.display = 'none');

            // Log ELSX Activation
            console.log("%c ELSX ERP: System Fully Unlocked ", "background: #00DBDE; color: #000; font-weight: bold; font-size: 16px; padding: 5px;");
        });
    }
});
