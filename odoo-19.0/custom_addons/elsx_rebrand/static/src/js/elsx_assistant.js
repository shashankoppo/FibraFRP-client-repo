/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ELSXAssistant extends Component {
    setup() {
        this.state = useState({
            isOpen: false,
            messages: [{ role: 'assistant', content: 'Welcome to ELSX ERP. How can I assist your evolution today?' }],
            userInput: '',
        });
        this.action = useService("action");
    }

    toggle() {
        this.state.isOpen = !this.state.isOpen;
    }

    async sendMessage() {
        if (!this.state.userInput) return;

        const userMsg = this.state.userInput;
        this.state.messages.push({ role: 'user', content: userMsg });
        this.state.userInput = '';

        // Simulate AI Response
        setTimeout(() => {
            this.state.messages.push({
                role: 'assistant',
                content: `Analyzing "${userMsg}"... Based on current global tech trends, I recommend optimizing your CRM pipeline with ELSX Smart Scoring.`
            });
        }, 1000);
    }
}
ELSXAssistant.template = "elsx_rebrand.ELSXAssistant";

// Add to the top bar
const systrayItem = {
    Component: ELSXAssistant,
};
registry.category("systray").add("ELSXAssistant", systrayItem, { sequence: 1 });
