# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from html import escape as html_escape
import logging

_logger = logging.getLogger(__name__)


class WhatsAppInvoiceSendWizard(models.TransientModel):
    _name = 'whatsapp.invoice.send.wizard'
    _description = 'Send Invoice via WhatsApp Wizard'

    invoice_id = fields.Many2one('account.move', required=True, string='Invoice', ondelete='cascade')
    account_id = fields.Many2one(
        'whatsapp.account', 
        string='WhatsApp Account', 
        required=True,
        default=lambda self: self.env['whatsapp.account']._get_default_account()
    )
    partner_id = fields.Many2one('res.partner', related='invoice_id.partner_id', string='Customer')
    
    phone_number = fields.Char('WhatsApp Number', required=True)
    
    send_mode = fields.Selection([
        ('template', 'WhatsApp Template'),
        ('custom_text', 'Custom Text Message')
    ], string='Send Mode', default='template', required=True)
    
    template_id = fields.Many2one(
        'whatsapp.template', 
        string='Template',
        domain=[('status', '=', 'approved'), ('category', 'in', ['utility', 'marketing'])]
    )
    
    message_body = fields.Text('Custom Message')
    attach_pdf = fields.Boolean('Attach Invoice PDF', default=True)
    
    template_preview_html = fields.Html('Preview', compute='_compute_template_preview_html')
    template_preview_text = fields.Text('Preview Text', compute='_compute_template_preview_html')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'invoice_id' in res:
            invoice = self.env['account.move'].browse(res['invoice_id'])
            if invoice.partner_id:
                res['phone_number'] = (
                    getattr(invoice.partner_id, 'mobile', False)
                    or getattr(invoice.partner_id, 'phone', False)
                )
                
                # Try to get default template from settings
                ICPSudo = self.env['ir.config_parameter'].sudo()
                tmpl_id = int(ICPSudo.get_param('whatsapp.invoice.default.template.id', default=0))
                if tmpl_id:
                    res['template_id'] = tmpl_id
                else:
                    # Look for any approved template containing 'invoice'
                    tmpl = self.env['whatsapp.template'].search([
                        ('status', '=', 'approved'),
                        ('name', 'ilike', 'invoice')
                    ], limit=1)
                    if tmpl:
                        res['template_id'] = tmpl.id
                        
                # Pre-fill custom message
                res['message_body'] = (
                    f"Hi {invoice.partner_id.name},\n\n"
                    f"Please find attached your invoice {invoice.name} for {invoice.currency_id.symbol}{invoice.amount_total}.\n"
                    f"Due Date: {invoice.invoice_date_due or 'N/A'}\n\n"
                    f"Best regards,\n{invoice.company_id.name}"
                )
        return res

    @api.onchange('template_id', 'invoice_id')
    def _compute_template_preview_html(self):
        for rec in self:
            if rec.send_mode == 'template' and rec.template_id:
                pdf_content = False
                pdf_name = False
                if rec.attach_pdf and rec.invoice_id and rec.template_id.header_type == 'document':
                    pdf_content = rec.invoice_id._get_invoice_report_pdf()
                    pdf_name = f"{rec.invoice_id.name.replace('/', '_')}.pdf"
                rec.template_preview_html = rec.template_id._render_customer_preview_html(
                    partner=rec.partner_id,
                    record=rec.invoice_id,
                    header_media_file=pdf_content,
                    header_media_filename=pdf_name,
                    shell=True,
                    compact=True,
                )
                rec.template_preview_text = rec.template_id._render_customer_preview_text(
                    partner=rec.partner_id,
                    record=rec.invoice_id,
                    header_media_file=pdf_content,
                    header_media_filename=pdf_name,
                )
            else:
                body = rec.message_body or 'Type a message...'
                rec.template_preview_html = self.env['whatsapp.template']._render_text_preview_html(
                    body,
                    partner=rec.partner_id,
                    shell=True,
                )
                rec.template_preview_text = body

    def action_send(self):
        self.ensure_one()
        if not self.phone_number:
            raise UserError(_("Please provide a valid WhatsApp number."))
            
        if self.send_mode == 'template' and not self.template_id:
            raise UserError(_("Please select a WhatsApp Template."))
            
        if self.send_mode == 'custom_text' and not self.message_body:
            raise UserError(_("Please provide a custom message body."))
            
        pdf_content = False
        pdf_name = False
        if self.attach_pdf:
            pdf_content = self.invoice_id._get_invoice_report_pdf()
            pdf_name = f"{self.invoice_id.name.replace('/', '_')}.pdf"
        template_uses_pdf_header = bool(
            self.send_mode == 'template'
            and self.template_id
            and self.template_id.header_type == 'document'
            and pdf_content
        )

        try:
            # 1. Send the PDF document first (if attached)
            if pdf_content and not template_uses_pdf_header:
                doc_msg = self.env['whatsapp.message'].create({
                    'account_id': self.account_id.id,
                    'partner_id': self.partner_id.id,
                    'phone_number': self.phone_number,
                    'message_type': 'document',
                    'media_file': pdf_content,
                    'media_filename': pdf_name,
                    'media_mime_type': 'application/pdf',
                    'caption': self.message_body if self.send_mode == 'custom_text' else False,
                    'direction': 'outbound',
                    'is_automated': False,
                    'trigger_event': 'Manual Invoice Send',
                })
                # We need to pass the file content directly or save as attachment.
                # Since send_message expects kwargs, we'll bypass and use account directly if we want to pass kwargs.
                self.account_id.send_message(
                    to_number=self.phone_number,
                    message_type='document',
                    existing_message=doc_msg,
                    partner_id=self.partner_id.id,
                    media_file=pdf_content,
                    media_filename=pdf_name,
                    caption=self.message_body if self.send_mode == 'custom_text' else False
                )
                
            # 2. Send the Template or Text (if not already handled by caption)
            if self.send_mode == 'template':
                tmpl_msg = self.env['whatsapp.message'].create({
                    'account_id': self.account_id.id,
                    'partner_id': self.partner_id.id,
                    'phone_number': self.phone_number,
                    'message_type': 'template',
                    'body': self.template_id.body,
                    'template_id': self.template_id.id,
                    'template_name': self.template_id._get_send_template_name(),
                    'template_language': self.template_id._get_send_language_code(),
                    'media_file': pdf_content if template_uses_pdf_header else False,
                    'media_filename': pdf_name if template_uses_pdf_header else False,
                    'media_mime_type': 'application/pdf' if template_uses_pdf_header else False,
                    'direction': 'outbound',
                    'is_automated': False,
                    'trigger_event': 'Manual Invoice Send',
                })
                # Critical: pass 'record' parameter so the variables are resolved against the invoice!
                payload = self.template_id._prepare_send_payload(
                    partner=self.partner_id,
                    record=self.invoice_id,
                    header_media_file=pdf_content if template_uses_pdf_header else False,
                    header_media_filename=pdf_name if template_uses_pdf_header else False,
                )
                self.account_id.send_message(
                    to_number=self.phone_number,
                    message_type='template',
                    existing_message=tmpl_msg,
                    partner_id=self.partner_id.id,
                    template=payload,
                    template_record=self.template_id,
                    header_media_file=pdf_content if template_uses_pdf_header else False,
                    header_media_filename=pdf_name if template_uses_pdf_header else False,
                )
            elif self.send_mode == 'custom_text' and not self.attach_pdf:
                # If we attached a PDF, the custom text was already sent as a caption.
                text_msg = self.env['whatsapp.message'].create({
                    'account_id': self.account_id.id,
                    'partner_id': self.partner_id.id,
                    'phone_number': self.phone_number,
                    'message_type': 'text',
                    'body': self.message_body,
                    'direction': 'outbound',
                    'is_automated': False,
                    'trigger_event': 'Manual Invoice Send',
                })
                self.account_id.send_message(
                    to_number=self.phone_number,
                    message_type='text',
                    existing_message=text_msg,
                    partner_id=self.partner_id.id,
                    body=self.message_body
                )
                
            # Update invoice tracking
            self.invoice_id.write({'elsx_wa_last_sent': fields.Datetime.now()})
            self.invoice_id.message_post(body=_("Invoice sent via WhatsApp to %s") % self.phone_number)
            
            return {'type': 'ir.actions.act_window_close'}
            
        except Exception as e:
            _logger.error("Failed to send WhatsApp Invoice: %s", e)
            raise UserError(_("Failed to send WhatsApp message: %s") % str(e))
