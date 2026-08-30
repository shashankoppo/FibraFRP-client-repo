# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
import base64

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Existing Risk/Blockchain Fields
    elsx_payment_risk = fields.Selection([
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk')
    ], string='Payment Risk Score', readonly=True)
    elsx_blockchain_proof_url = fields.Char('Blockchain Proof URL', readonly=True)

    # WhatsApp Invoicing Fields
    elsx_wa_message_count = fields.Integer('WhatsApp Messages', compute='_compute_wa_message_count')
    elsx_wa_last_sent = fields.Datetime('Last WhatsApp Sent', readonly=True)
    elsx_wa_auto_reminder = fields.Boolean('Auto WhatsApp Reminder', default=True, help='Automatically send WhatsApp reminders when overdue')
    elsx_wa_reminder_count = fields.Integer('Reminders Sent', default=0, readonly=True)
    elsx_wa_next_reminder = fields.Datetime('Next Reminder', compute='_compute_wa_next_reminder', store=True)

    elsx_payment_status_display = fields.Selection([
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('due_soon', 'Due Soon'),
        ('overdue', 'Overdue'),
        ('not_due', 'Not Due')
    ], string='WhatsApp Payment Status', compute='_compute_payment_status_display')

    def _compute_wa_message_count(self):
        for move in self:
            if move.name and move.partner_id:
                count = self.env['whatsapp.message'].search_count([
                    ('partner_id', '=', move.partner_id.id),
                    ('body', 'ilike', move.name)
                ])
                move.elsx_wa_message_count = count
            else:
                move.elsx_wa_message_count = 0

    @api.depends('invoice_date_due', 'payment_state', 'elsx_wa_auto_reminder', 'elsx_wa_last_sent')
    def _compute_wa_next_reminder(self):
        ICPSudo = self.env['ir.config_parameter'].sudo()
        reminder_days = int(ICPSudo.get_param('whatsapp.invoice.reminder.days', default=3))
        for move in self:
            if move.payment_state in ('paid', 'in_payment') or not move.elsx_wa_auto_reminder or not move.invoice_date_due:
                move.elsx_wa_next_reminder = False
                continue

            last_sent = move.elsx_wa_last_sent or fields.Datetime.to_datetime(move.invoice_date_due)
            move.elsx_wa_next_reminder = last_sent + timedelta(days=reminder_days)

    @api.depends('payment_state', 'invoice_date_due')
    def _compute_payment_status_display(self):
        today = fields.Date.context_today(self)
        for move in self:
            if move.payment_state in ('paid', 'in_payment'):
                move.elsx_payment_status_display = 'paid'
            elif move.payment_state == 'partial':
                move.elsx_payment_status_display = 'partial'
            elif move.invoice_date_due:
                if move.invoice_date_due < today:
                    move.elsx_payment_status_display = 'overdue'
                elif move.invoice_date_due <= today + timedelta(days=3):
                    move.elsx_payment_status_display = 'due_soon'
                else:
                    move.elsx_payment_status_display = 'not_due'
            else:
                move.elsx_payment_status_display = 'not_due'

    def action_post(self):
        """Override post to send WhatsApp notification based on settings"""
        res = super(AccountMove, self).action_post()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        auto_send = ICPSudo.get_param('whatsapp.invoice.auto.send', default='False')
        if auto_send.lower() == 'true':
            for move in self:
                if move.move_type == 'out_invoice':
                    move._send_whatsapp_invoice_notification()
        return res

    def _send_whatsapp_invoice_notification(self):
        """Helper to send WhatsApp invoice notification (fallback for auto-send)"""
        account = self.env['whatsapp.account']._get_default_account()
        if not account:
            return

        partner = self.partner_id
        phone = getattr(partner, 'mobile', False) or partner.phone
        if not phone:
            return

        message_body = (
            f"Hi {partner.name}!\n\n"
            f"Your Invoice *{self.name}* is ready.\n"
            f"Amount Due: {self.currency_id.symbol}{self.amount_total}\n"
            f"Due Date: {self.invoice_date_due}\n\n"
            f"Best regards,\n"
            f"{self.company_id.name}"
        )

        try:
            message = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'partner_id': partner.id,
                'phone_number': phone,
                'message_type': 'text',
                'body': message_body,
                'direction': 'outbound',
                'is_automated': True,
                'trigger_event': 'Invoice Posted',
            })
            message.action_send()
            self.write({'elsx_wa_last_sent': fields.Datetime.now()})
            self.message_post(body="Auto-sent WhatsApp invoice notification.")
        except Exception as exc:
            if 'message' in locals():
                message.sudo().write({
                    'status': 'failed',
                    'error_message': str(exc),
                })
            _logger.exception("Failed to send WhatsApp invoice notification for %s", self.name)

    def action_send_whatsapp_invoice(self):
        """Open the wizard to send the invoice via WhatsApp"""
        self.ensure_one()
        return {
            'name': _('Send Invoice via WhatsApp'),
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.invoice.send.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }

    def action_open_whatsapp_link(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("This document has no customer/vendor set."))
        label = _('invoice') if self.is_invoice(include_receipts=True) else _('document')
        amount = self.currency_id.format(self.amount_total) if self.currency_id else self.amount_total
        message = _(
            "Hello %(customer)s,\n\n"
            "Regarding %(label)s %(document)s for %(amount)s.\n\n"
            "Thank you."
        ) % {
            'customer': self.partner_id.display_name,
            'label': label,
            'document': self.name or self.ref or _('your document'),
            'amount': amount,
        }
        return self.partner_id._elsx_open_whatsapp_link(message=message, title=_('Open WhatsApp'))

    def action_send_whatsapp_reminder(self):
        """Send a quick manual WhatsApp reminder for overdue invoice"""
        self.ensure_one()
        if self.payment_state in ('paid', 'in_payment'):
            raise UserError(_("This invoice is already paid."))

        account = self.env['whatsapp.account']._get_default_account()
        if not account:
            raise UserError(_("No active WhatsApp account found."))

        phone = getattr(self.partner_id, 'mobile', False) or self.partner_id.phone
        if not phone:
            raise UserError(_("Customer has no phone number set."))

        message_body = (
            f"Hi {self.partner_id.name},\n\n"
            f"Friendly reminder that your invoice *{self.name}* for {self.currency_id.symbol}{self.amount_total} "
            f"was due on {self.invoice_date_due}.\n\n"
            f"Please arrange payment at your earliest convenience. Thank you!"
        )

        try:
            message = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'partner_id': self.partner_id.id,
                'phone_number': phone,
                'message_type': 'text',
                'body': message_body,
                'direction': 'outbound',
                'is_automated': False,
            })
            message.action_send()
            self.write({
                'elsx_wa_last_sent': fields.Datetime.now(),
                'elsx_wa_reminder_count': self.elsx_wa_reminder_count + 1
            })
            self.message_post(body="Manual WhatsApp payment reminder sent.")
        except Exception as e:
            raise UserError(_("Failed to send WhatsApp reminder: %s") % str(e))

    def action_view_whatsapp_messages(self):
        self.ensure_one()
        return {
            'name': _('WhatsApp Messages'),
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.message',
            'view_mode': 'tree,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('partner_id', '=', self.partner_id.id), ('body', 'ilike', self.name)],
            'context': dict(self._context, create=False)
        }

    @api.model
    def _cron_send_overdue_reminders(self):
        """Cron job to automatically send WhatsApp reminders for overdue invoices"""
        ICPSudo = self.env['ir.config_parameter'].sudo()
        auto_remind = ICPSudo.get_param('whatsapp.invoice.auto.remind', default='False')
        if auto_remind.lower() != 'true':
            return

        today = fields.Date.context_today(self)
        now = fields.Datetime.now()

        invoices = self.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ('paid', 'in_payment')),
            ('elsx_wa_auto_reminder', '=', True),
            ('elsx_wa_next_reminder', '<=', now),
            ('invoice_date_due', '<', today)
        ])

        for inv in invoices:
            try:
                account = self.env['whatsapp.account']._get_default_account()
                if not account:
                    continue
                phone = getattr(inv.partner_id, 'mobile', False) or inv.partner_id.phone
                if not phone:
                    continue

                message_body = (
                    f"Hi {inv.partner_id.name},\n\n"
                    f"Automated reminder: Your invoice *{inv.name}* for {inv.currency_id.symbol}{inv.amount_total} "
                    f"is overdue since {inv.invoice_date_due}.\n\n"
                    f"Please arrange payment soon. Thank you!"
                )

                message = self.env['whatsapp.message'].create({
                    'account_id': account.id,
                    'partner_id': inv.partner_id.id,
                    'phone_number': phone,
                    'message_type': 'text',
                    'body': message_body,
                    'direction': 'outbound',
                    'is_automated': True,
                    'trigger_event': 'Overdue Reminder'
                })
                message.action_send()
                inv.write({
                    'elsx_wa_last_sent': fields.Datetime.now(),
                    'elsx_wa_reminder_count': inv.elsx_wa_reminder_count + 1
                })
                inv.message_post(body="Automated WhatsApp payment reminder sent.")
            except Exception as e:
                _logger.error("Failed to send automated reminder for invoice %s: %s", inv.name, e)

    def _get_invoice_report_pdf(self):
        """Helper to generate PDF for this invoice"""
        self.ensure_one()
        try:
            pdf_content, report_type = self.env['ir.actions.report']._render_qweb_pdf(
                'account.account_invoices',
                res_ids=self.ids,
            )
            return base64.b64encode(pdf_content)
        except Exception as e:
            _logger.error("Failed to generate PDF for invoice %s: %s", self.name, e)
            raise UserError(_("Failed to generate Invoice PDF: %s") % str(e))
