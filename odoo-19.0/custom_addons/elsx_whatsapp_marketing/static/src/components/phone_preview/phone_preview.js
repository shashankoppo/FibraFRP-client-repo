/** @odoo-module **/

import { Component } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';


export class WhatsAppPhonePreview extends Component {
    static template = 'elsx_whatsapp_marketing.WhatsAppPhonePreview';
    static props = {
        payload: { type: Object, optional: true },
    };
}


export class WhatsAppPhonePreviewField extends Component {
    static template = 'elsx_whatsapp_marketing.WhatsAppPhonePreviewField';
    static components = { WhatsAppPhonePreview };
    static props = { ...standardFieldProps };

    get payload() {
        const value = this.props.record.data[this.props.name];
        if (!value) {
            return {};
        }
        try {
            return typeof value === 'string' ? JSON.parse(value) : value;
        } catch {
            return {
                body: '',
                header: { type: 'none' },
                footer: '',
                buttons: [],
                carousel: [],
                warnings: [{
                    code: 'invalid_payload',
                    severity: 'error',
                    message: 'Preview data is unavailable.',
                }],
            };
        }
    }
}

registry.category('fields').add('whatsapp_phone_preview', {
    component: WhatsAppPhonePreviewField,
    supportedTypes: ['char', 'text'],
});
