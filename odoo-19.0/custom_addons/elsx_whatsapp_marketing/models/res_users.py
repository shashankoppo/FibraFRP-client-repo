# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def get_whatsapp_workspace_role(self):
        """Compatibility role used by older WhatsApp menu server actions.

        Production databases can keep server actions created by newer builds after
        a source rollback. Keep this method lightweight and data-preserving so
        those actions can route users without requiring any schema migration.
        """
        self.ensure_one()
        user = self.sudo()
        if user.has_group('base.group_system') or user.has_group('elsx_whatsapp_marketing.group_whatsapp_manager'):
            return 'manager'

        TeamMember = self.env['whatsapp.team.member'].sudo()
        member = TeamMember.search([
            ('user_id', '=', user.id),
            ('is_available', '=', True),
        ], limit=1)
        if not member:
            member = TeamMember.search([('user_id', '=', user.id)], limit=1)

        if member.role in ('admin', 'manager'):
            return 'manager'
        if member.can_send_campaigns or member.can_manage_templates:
            return 'marketer'
        return 'agent'

    def get_whatsapp_ui_version(self):
        """Return the installed WhatsApp UI generation for legacy actions."""
        self.ensure_one()
        return 'legacy'