/** @odoo-module **/

import { Component, onWillStart, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';


export class WhatsAppOverviewV2 extends Component {
    static template = 'elsx_whatsapp_marketing.WhatsAppOverviewV2';

    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.state = useState({
            loading: true,
            error: false,
            data: { metrics: {}, exceptions: [] },
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.state.data = await this.orm.call(
                'whatsapp.analytics',
                'get_overview_v2',
                [],
            );
        } catch {
            this.state.error = true;
        } finally {
            this.state.loading = false;
        }
    }

    open(actionXmlId) {
        if (actionXmlId) {
            return this.action.doAction(actionXmlId);
        }
    }
}

registry.category('actions').add(
    'elsx_whatsapp_overview_v2',
    WhatsAppOverviewV2,
);
