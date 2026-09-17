from odoo import api, models


class WhatsAppBus(models.Model):
    _inherit = 'bus.bus'

    @api.model
    def _sendone(self, target, notification_type, message):
        if not isinstance(target, str) or target != 'elsx_whatsapp_channel':
            return super()._sendone(target, notification_type, message)
        chat = self.env['whatsapp.chat'].sudo().browse(message.get('chat_id')).exists()
        if not chat:
            return
        account = chat.account_id
        manager = self.env.ref('elsx_whatsapp_marketing.group_whatsapp_manager')
        users = self.env['res.users'].sudo().search([
            ('active', '=', True), ('share', '=', False),
            ('company_ids', 'in', account.company_id.ids),
            '|', ('all_group_ids', 'in', manager.ids),
            ('id', 'in', account.team_member_ids.user_id.ids + chat.assigned_user_id.ids),
        ])
        for user in users:
            scoped_chat = chat.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)
            if scoped_chat.has_access('read'):
                super()._sendone(user.partner_id, notification_type, message)
