# -*- coding: utf-8 -*-
from odoo import models, fields, api
import uuid


class ElsxSignRequest(models.Model):
    _name = 'elsx.sign.request'
    _description = 'eSignature Document Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Document Name", required=True)
    document_attachment_id = fields.Many2one('ir.attachment', string="PDF Document", required=True)
    partner_id = fields.Many2one('res.partner', string="Recipient to Sign", required=True)
    employee_id = fields.Many2one('hr.employee', string="Related Employee")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('signed', 'Fully Signed'),
        ('declined', 'Declined'),
    ], string="Status", default='draft', tracking=True)

    access_token = fields.Char(
        string="Security Token",
        default=lambda s: str(uuid.uuid4()),
        copy=False, readonly=True
    )
    signature_image = fields.Binary(string="Captured Signature", readonly=True)
    signed_date = fields.Datetime(string="Signed On", readonly=True)
    signer_ip = fields.Char(string="Signer IP Address", readonly=True)
    sign_url = fields.Char(string="Signing URL", compute='_compute_sign_url')

    @api.depends('id', 'access_token')
    def _compute_sign_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if rec.id and rec.access_token:
                rec.sign_url = f"{base_url}/sign/document/{rec.id}?token={rec.access_token}"
            else:
                rec.sign_url = ''

    def action_send_request(self):
        """
        Dispatches the actual email using the branded mail template.
        Falls back to a message_post if the template is not found.
        """
        for req in self:
            template = self.env.ref('elsx_sign.mail_template_elsx_sign_request', raise_if_not_found=False)
            if template:
                template.with_context(base_url=self.env['ir.config_parameter'].sudo().get_param('web.base.url')).send_mail(req.id, force_send=True)
            else:
                # Fallback if template was not loaded
                req.message_post(
                    body=f"Signature requested. Sign URL: <a href='{req.sign_url}'>{req.sign_url}</a>",
                    subject=f"Action Required: Please Sign - {req.name}",
                    partner_ids=[req.partner_id.id],
                    subtype_xmlid='mail.mt_comment'
                )
            req.state = 'sent'

    def action_mark_signed(self, signature_data, ip_address):
        """
        Called by the public controller when the user submits signature.
        """
        self.write({
            'signature_image': signature_data,
            'signer_ip': ip_address,
            'signed_date': fields.Datetime.now(),
            'state': 'signed'
        })
        self.message_post(
            body=f"✅ Document securely signed by {self.partner_id.name} from IP: {ip_address}",
            subtype_xmlid='mail.mt_note'
        )

    def action_decline(self):
        self.state = 'declined'
        self.message_post(body=f"❌ Signing request was declined by {self.partner_id.name}.")

    def action_reset_to_draft(self):
        self.write({'state': 'draft', 'signature_image': False, 'signed_date': False, 'signer_ip': False})
