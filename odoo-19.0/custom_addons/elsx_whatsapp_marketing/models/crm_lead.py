# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_set_won_rainbowman(self):
        res = super().action_set_won_rainbowman()
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

            account = self.env['whatsapp.account'].search([('status', '=', 'connected')], limit=1)
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
