# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    def _elsx_get_whatsapp_partner(self):
        self.ensure_one()
        partner = self.partner_id
        order = getattr(self, 'order_id', False)
        if not partner and order:
            partner = order.partner_id
        if not partner:
            partner = self._mail_get_customer()
        return partner

    def action_open_whatsapp_link(self):
        self.ensure_one()
        partner = self._elsx_get_whatsapp_partner()
        if not partner:
            raise UserError(_("No customer is linked to this coupon or gift card."))
        message = _(
            "Hello %(customer)s,\n\n"
            "Your %(kind)s code is: %(code)s\n"
            "Balance: %(balance)s"
        ) % {
            'customer': partner.display_name,
            'kind': _('gift card') if self.program_type == 'gift_card' else _('coupon'),
            'code': self.code,
            'balance': self.points_display,
        }
        if self.expiration_date:
            message += _("\nValid until: %s") % self.expiration_date
        return partner._elsx_open_whatsapp_link(message=message, title=_('Open WhatsApp'))
