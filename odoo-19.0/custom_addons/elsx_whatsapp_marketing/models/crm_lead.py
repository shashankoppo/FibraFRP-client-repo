# -*- coding: utf-8 -*-
from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_set_won_rainbowman(self):
        res = super(CrmLead, self).action_set_won_rainbowman()
        self._send_whatsapp_congratulation()
        return res

    def _send_whatsapp_congratulation(self):
        for lead in self:
            if lead.partner_id and (lead.partner_id.mobile or lead.partner_id.phone):
                account = self.env['whatsapp.account'].search([('status', '=', 'connected')], limit=1)
                if account:
                    body = f"Congratulations {lead.partner_id.name}! 🚀 Your opportunity '{lead.name}' has been marked as Won. We are excited to work with you!"
                    account.send_message(
                        to_number=lead.partner_id.mobile or lead.partner_id.phone,
                        message_type='text',
                        body=body,
                        partner_id=lead.partner_id.id
                    )
