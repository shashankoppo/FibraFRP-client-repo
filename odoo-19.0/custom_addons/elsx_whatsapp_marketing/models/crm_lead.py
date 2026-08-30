# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_set_won_rainbowman(self):
        res = super().action_set_won_rainbowman()
        auto_send = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.crm.won.auto_send',
            default='False',
        )
        if str(auto_send).lower() != 'true':
            return res
        self._send_whatsapp_congratulation()
        return res

    def _send_whatsapp_congratulation(self):
        # Fetch the configured template parameter
        template_param = self.env['ir.config_parameter'].sudo().get_param('whatsapp.crm.won.template.id')
        template = False
        if template_param:
            try:
                template = self.env['whatsapp.template'].browse(int(template_param))
                if not template.exists():
                    template = False
            except Exception:
                template = False

        for lead in self:
            partner = lead.partner_id
            phone = getattr(partner, 'mobile', False) or partner.phone if partner else False
            if not phone:
                continue

            if template and template.account_id:
                account = template.account_id
            else:
                account = self.env['whatsapp.account']._get_default_account()
            if account and account.status != 'connected' and not template:
                connected_account = self.env['whatsapp.account'].search([('status', '=', 'connected')], limit=1)
                account = connected_account or account
            if not account:
                continue

            try:
                if template:
                    account.send_message(
                        to_number=phone,
                        message_type='template',
                        template_record=template,
                        partner_id=partner.id,
                        is_automated=True,
                    )
                else:
                    body = (
                        f"Congratulations {partner.name}! "
                        f"Your opportunity '{lead.name}' has been marked as Won. "
                        "We are excited to work with you!"
                    )
                    account.send_message(
                        to_number=phone,
                        message_type='text',
                        body=body,
                        partner_id=partner.id,
                        is_automated=True,
                    )
            except Exception:
                _logger.exception("Failed to send WhatsApp won-stage notification for lead %s", lead.id)

    def action_open_whatsapp_link(self):
        self.ensure_one()
        partner = self.partner_id
        phone = (getattr(partner, 'mobile', False) or partner.phone) if partner else self.phone
        if not phone:
            raise UserError(_("No phone number is set for this lead."))
        normalized = self.env['whatsapp.message']._normalize_phone(phone, strict=False)
        if not normalized:
            raise UserError(_("Could not prepare this lead's WhatsApp number."))
        customer_name = partner.display_name if partner else (self.contact_name or self.partner_name or _('there'))
        message = _(
            "Hello %(customer)s,\n\n"
            "Regarding %(lead)s.\n\n"
            "Thank you."
        ) % {
            'customer': customer_name,
            'lead': self.name,
        }
        return {
            'type': 'ir.actions.act_url',
            'name': _('Open WhatsApp'),
            'target': 'new',
            'url': 'https://wa.me/%s?text=%s' % (normalized, quote(message.strip())),
        }
