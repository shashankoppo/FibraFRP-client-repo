# -*- coding: utf-8 -*-
import requests

from odoo import fields, models, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    elsx_tally_enabled = fields.Boolean(
        string='Enable Tally Bridge',
        config_parameter='elsx_tally.enabled',
        default=False,
        help='Enable Tally XML export and direct gateway push buttons on invoices.',
    )
    elsx_tally_gateway_url = fields.Char(
        string='Tally Gateway URL',
        config_parameter='elsx_tally.gateway_url',
        default='http://host.docker.internal:9000',
        help='TallyPrime/Tally ERP HTTP XML gateway URL. From Docker, host.docker.internal usually points to the Windows host.',
    )
    elsx_tally_company_name = fields.Char(
        string='Tally Company Name',
        config_parameter='elsx_tally.company_name',
        help='Exact company name open in Tally. Leave empty to use the Odoo company name.',
    )
    elsx_tally_sales_ledger = fields.Char(
        string='Sales Ledger',
        config_parameter='elsx_tally.sales_ledger',
        default='Sales',
    )
    elsx_tally_purchase_ledger = fields.Char(
        string='Purchase Ledger',
        config_parameter='elsx_tally.purchase_ledger',
        default='Purchase',
    )
    elsx_tally_tax_ledger = fields.Char(
        string='Tax Ledger',
        config_parameter='elsx_tally.tax_ledger',
        default='GST Output',
        help='Fallback tax ledger used for the total tax amount. Split-tax ledgers can be added later if required.',
    )
    elsx_tally_timeout = fields.Integer(
        string='Gateway Timeout Seconds',
        config_parameter='elsx_tally.timeout',
        default=15,
    )
    elsx_tally_auto_push_on_post = fields.Boolean(
        string='Auto Push Posted Customer Invoices',
        config_parameter='elsx_tally.auto_push_on_post',
        default=False,
        help='Off by default. When enabled, posted customer invoices are pushed to Tally if the gateway is reachable.',
    )

    def action_test_tally_connection(self):
        self.ensure_one()
        url = (self.elsx_tally_gateway_url or '').strip()
        if not url:
            raise UserError(_('Please configure the Tally Gateway URL first.'))
        payload = (
            '<ENVELOPE>'
            '<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST>'
            '<TYPE>Function</TYPE><ID>$$Version</ID></HEADER>'
            '<BODY><DESC/></BODY>'
            '</ENVELOPE>'
        )
        try:
            response = requests.post(
                url,
                data=payload.encode('utf-8'),
                headers={'Content-Type': 'text/xml; charset=utf-8'},
                timeout=max(self.elsx_tally_timeout or 15, 1),
            )
            response.raise_for_status()
        except Exception as exc:
            self.env['elsx.tally.sync.log'].sudo().create({
                'name': 'Tally Connection Test',
                'operation': 'test',
                'state': 'failed',
                'gateway_url': url,
                'request_payload': payload,
                'error_message': str(exc),
            })
            raise UserError(_('Tally connection failed: %s') % exc)

        self.env['elsx.tally.sync.log'].sudo().create({
            'name': 'Tally Connection Test',
            'operation': 'test',
            'state': 'success',
            'gateway_url': url,
            'request_payload': payload,
            'response_payload': response.text[:5000],
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tally Connected'),
                'message': _('Tally gateway responded successfully.'),
                'type': 'success',
            },
        }
