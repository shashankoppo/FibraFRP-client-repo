# -*- coding: utf-8 -*-
import base64
import html
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    elsx_tally_state = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('xml_generated', 'XML Generated'),
        ('pushed', 'Pushed to Tally'),
        ('failed', 'Failed'),
    ], string='Tally Status', default='not_synced', copy=False, readonly=True)
    elsx_tally_synced_at = fields.Datetime('Tally Synced At', copy=False, readonly=True)
    elsx_tally_last_error = fields.Text('Last Tally Error', copy=False, readonly=True)
    elsx_tally_log_count = fields.Integer('Tally Logs', compute='_compute_elsx_tally_log_count')

    def _compute_elsx_tally_log_count(self):
        grouped = self.env['elsx.tally.sync.log']._read_group(
            domain=[('move_id', 'in', self.ids)],
            groupby=['move_id'],
            aggregates=['__count'],
        )
        counts = {move.id: count for move, count in grouped}
        for move in self:
            move.elsx_tally_log_count = counts.get(move.id, 0)

    def action_post(self):
        res = super().action_post()
        if self.env['ir.config_parameter'].sudo().get_param('elsx_tally.auto_push_on_post', 'False').lower() == 'true':
            for move in self.filtered(lambda rec: rec.move_type in ('out_invoice', 'out_receipt') and rec.state == 'posted'):
                try:
                    move.action_push_to_tally()
                except Exception as exc:
                    _logger.exception('Tally auto-push failed for invoice %s', move.name)
                    move.message_post(body=_('Tally auto-push failed: %s') % exc)
        return res

    def _tally_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'enabled': ICP.get_param('elsx_tally.enabled', 'False').lower() == 'true',
            'gateway_url': (ICP.get_param('elsx_tally.gateway_url') or '').strip(),
            'company_name': (ICP.get_param('elsx_tally.company_name') or '').strip(),
            'sales_ledger': (ICP.get_param('elsx_tally.sales_ledger') or 'Sales').strip(),
            'purchase_ledger': (ICP.get_param('elsx_tally.purchase_ledger') or 'Purchase').strip(),
            'tax_ledger': (ICP.get_param('elsx_tally.tax_ledger') or 'GST Output').strip(),
            'timeout': int(ICP.get_param('elsx_tally.timeout', default='15') or 15),
        }

    def _tally_check_invoice_ready(self):
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('Only posted invoices/bills can be exported to Tally.'))
        if self.move_type not in ('out_invoice', 'out_refund', 'out_receipt', 'in_invoice', 'in_refund', 'in_receipt'):
            raise UserError(_('Only customer/vendor invoices, receipts, and credit/debit notes can be exported to Tally.'))
        if not self.partner_id:
            raise UserError(_('Please set a customer/vendor before exporting to Tally.'))
        if not self.invoice_line_ids:
            raise UserError(_('This invoice has no invoice lines to export.'))

    def _tally_escape(self, value):
        return html.escape(str(value or ''), quote=False)

    def _tally_amount(self, value):
        return f'{float(value or 0.0):.2f}'

    def _tally_date(self):
        self.ensure_one()
        return fields.Date.to_date(self.invoice_date or self.date or fields.Date.context_today(self)).strftime('%Y%m%d')

    def _tally_voucher_type(self):
        self.ensure_one()
        return {
            'out_invoice': 'Sales',
            'out_receipt': 'Receipt',
            'out_refund': 'Credit Note',
            'in_invoice': 'Purchase',
            'in_receipt': 'Payment',
            'in_refund': 'Debit Note',
        }.get(self.move_type, 'Sales')

    def _tally_ledger_entries_xml(self, config):
        self.ensure_one()
        amount_total = abs(self.amount_total)
        amount_untaxed = abs(self.amount_untaxed)
        amount_tax = abs(self.amount_tax)
        is_reversal = self.move_type in ('out_refund', 'in_refund')
        is_sales = self.move_type in ('out_invoice', 'out_receipt', 'out_refund')
        main_ledger = config['sales_ledger'] if is_sales else config['purchase_ledger']

        if is_sales:
            party_amount = amount_total if is_reversal else -amount_total
            main_amount = -amount_untaxed if is_reversal else amount_untaxed
            tax_amount = -amount_tax if is_reversal else amount_tax
            party_positive = 'Yes' if party_amount < 0 else 'No'
            main_positive = 'Yes' if main_amount < 0 else 'No'
        else:
            party_amount = -amount_total if is_reversal else amount_total
            main_amount = amount_untaxed if is_reversal else -amount_untaxed
            tax_amount = amount_tax if is_reversal else -amount_tax
            party_positive = 'Yes' if party_amount < 0 else 'No'
            main_positive = 'Yes' if main_amount < 0 else 'No'

        entries = [
            self._tally_ledger_entry_xml(self.partner_id.commercial_partner_id.name, party_amount, party_positive, is_party=True),
            self._tally_ledger_entry_xml(main_ledger, main_amount, main_positive),
        ]
        if amount_tax:
            entries.append(self._tally_ledger_entry_xml(config['tax_ledger'], tax_amount, 'Yes' if tax_amount < 0 else 'No'))
        return ''.join(entries)

    def _tally_ledger_entry_xml(self, ledger_name, amount, is_deemed_positive, is_party=False):
        return (
            '<LEDGERENTRIES.LIST>'
            f'<LEDGERNAME>{self._tally_escape(ledger_name)}</LEDGERNAME>'
            f'<ISDEEMEDPOSITIVE>{is_deemed_positive}</ISDEEMEDPOSITIVE>'
            f'<ISPARTYLEDGER>{"Yes" if is_party else "No"}</ISPARTYLEDGER>'
            f'<AMOUNT>{self._tally_amount(amount)}</AMOUNT>'
            '</LEDGERENTRIES.LIST>'
        )

    def _generate_tally_xml(self):
        self.ensure_one()
        self._tally_check_invoice_ready()
        config = self._tally_config()
        company_name = config['company_name'] or self.company_id.name
        voucher_type = self._tally_voucher_type()
        remote_id = f'ODOO-{self.company_id.id}-{self._name}-{self.id}'
        narration = _('Odoo %s exported from invoice %s') % (voucher_type, self.name)
        return (
            '<ENVELOPE>'
            '<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>'
            '<BODY><IMPORTDATA>'
            '<REQUESTDESC>'
            '<REPORTNAME>Vouchers</REPORTNAME>'
            '<STATICVARIABLES>'
            f'<SVCURRENTCOMPANY>{self._tally_escape(company_name)}</SVCURRENTCOMPANY>'
            '</STATICVARIABLES>'
            '</REQUESTDESC>'
            '<REQUESTDATA>'
            '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<VOUCHER REMOTEID="{self._tally_escape(remote_id)}" VCHTYPE="{self._tally_escape(voucher_type)}" ACTION="Create" OBJVIEW="Accounting Voucher View">'
            f'<DATE>{self._tally_date()}</DATE>'
            f'<VOUCHERTYPENAME>{self._tally_escape(voucher_type)}</VOUCHERTYPENAME>'
            f'<VOUCHERNUMBER>{self._tally_escape(self.name)}</VOUCHERNUMBER>'
            f'<REFERENCE>{self._tally_escape(self.payment_reference or self.ref or self.name)}</REFERENCE>'
            f'<PARTYLEDGERNAME>{self._tally_escape(self.partner_id.commercial_partner_id.name)}</PARTYLEDGERNAME>'
            '<PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>'
            f'<NARRATION>{self._tally_escape(narration)}</NARRATION>'
            f'{self._tally_ledger_entries_xml(config)}'
            '</VOUCHER>'
            '</TALLYMESSAGE>'
            '</REQUESTDATA>'
            '</IMPORTDATA></BODY>'
            '</ENVELOPE>'
        )

    def _create_tally_log(self, operation, state, request_payload=False, response_payload=False, error_message=False, gateway_url=False):
        self.ensure_one()
        return self.env['elsx.tally.sync.log'].sudo().create({
            'name': f'{self.name or "Invoice"} - {dict(self.env["elsx.tally.sync.log"]._fields["operation"].selection).get(operation, operation)}',
            'move_id': self.id,
            'operation': operation,
            'state': state,
            'gateway_url': gateway_url,
            'request_payload': request_payload,
            'response_payload': (response_payload or '')[:20000],
            'error_message': error_message,
        })

    def action_export_tally_xml(self):
        self.ensure_one()
        xml_payload = self._generate_tally_xml()
        filename = f'Tally-{(self.name or "invoice").replace("/", "-")}.xml'
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/xml',
            'datas': base64.b64encode(xml_payload.encode('utf-8')),
        })
        self.write({
            'elsx_tally_state': 'xml_generated',
            'elsx_tally_synced_at': fields.Datetime.now(),
            'elsx_tally_last_error': False,
        })
        self._create_tally_log('xml_export', 'success', request_payload=xml_payload)
        self.message_post(body=_('Tally XML generated: %s') % filename, attachment_ids=[attachment.id])
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_push_to_tally(self):
        self.ensure_one()
        config = self._tally_config()
        if not config['enabled']:
            raise UserError(_('Enable Tally Bridge in Invoicing settings before pushing invoices.'))
        if not config['gateway_url']:
            raise UserError(_('Please configure the Tally Gateway URL in Invoicing settings.'))

        xml_payload = self._generate_tally_xml()
        try:
            response = requests.post(
                config['gateway_url'],
                data=xml_payload.encode('utf-8'),
                headers={'Content-Type': 'text/xml; charset=utf-8'},
                timeout=max(config['timeout'], 1),
            )
            response.raise_for_status()
            response_text = response.text or ''
            if '<LINEERROR>' in response_text.upper() or '<CREATED>0</CREATED>' in response_text.upper():
                raise UserError(_('Tally rejected the invoice. Response: %s') % response_text[:1000])
        except Exception as exc:
            self.write({
                'elsx_tally_state': 'failed',
                'elsx_tally_last_error': str(exc),
            })
            self._create_tally_log(
                'push',
                'failed',
                request_payload=xml_payload,
                error_message=str(exc),
                gateway_url=config['gateway_url'],
            )
            raise UserError(_('Could not push invoice to Tally: %s') % exc)

        self.write({
            'elsx_tally_state': 'pushed',
            'elsx_tally_synced_at': fields.Datetime.now(),
            'elsx_tally_last_error': False,
        })
        self._create_tally_log(
            'push',
            'success',
            request_payload=xml_payload,
            response_payload=response_text,
            gateway_url=config['gateway_url'],
        )
        self.message_post(body=_('Invoice pushed to Tally successfully.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pushed to Tally'),
                'message': _('Invoice was sent to the configured Tally gateway.'),
                'type': 'success',
            },
        }

    def action_reset_tally_status(self):
        for move in self:
            move.write({
                'elsx_tally_state': 'not_synced',
                'elsx_tally_synced_at': False,
                'elsx_tally_last_error': False,
            })
            move.message_post(body=_('Tally sync status reset.'))
        return True

    def action_view_tally_logs(self):
        self.ensure_one()
        return {
            'name': _('Tally Sync Logs'),
            'type': 'ir.actions.act_window',
            'res_model': 'elsx.tally.sync.log',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }
