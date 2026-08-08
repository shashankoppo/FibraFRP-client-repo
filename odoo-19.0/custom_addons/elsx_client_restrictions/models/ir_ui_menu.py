# -*- coding: utf-8 -*-
import logging

from odoo import api, models


_logger = logging.getLogger(__name__)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _elsx_clear_broken_action_pointers(self):
        """Remove stale menu action refs before the framework serializes menus."""
        if self.env.context.get("elsx_skip_menu_action_repair"):
            return 0
        removed = 0
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    """
                    WITH broken AS (
                        SELECT m.id
                          FROM ir_ui_menu m
                         WHERE m.action IS NOT NULL
                           AND m.action::text <> ''
                           AND split_part(m.action::text, ',', 2) ~ '^[0-9]+$'
                           AND (
                             (split_part(m.action::text, ',', 1) = 'ir.actions.server'
                              AND NOT EXISTS (SELECT 1 FROM ir_act_server a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
                             OR (split_part(m.action::text, ',', 1) = 'ir.actions.act_window'
                              AND NOT EXISTS (SELECT 1 FROM ir_act_window a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
                             OR (split_part(m.action::text, ',', 1) = 'ir.actions.act_url'
                              AND NOT EXISTS (SELECT 1 FROM ir_act_url a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
                             OR (split_part(m.action::text, ',', 1) = 'ir.actions.client'
                              AND NOT EXISTS (SELECT 1 FROM ir_act_client a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
                             OR (split_part(m.action::text, ',', 1) = 'ir.actions.report'
                              AND NOT EXISTS (SELECT 1 FROM ir_act_report_xml a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
                             OR split_part(m.action::text, ',', 1) NOT IN (
                                'ir.actions.server',
                                'ir.actions.act_window',
                                'ir.actions.act_url',
                                'ir.actions.client',
                                'ir.actions.report'
                             )
                           )
                    ), cleared AS (
                        UPDATE ir_ui_menu
                           SET action = NULL,
                               write_date = NOW()
                         WHERE id IN (SELECT id FROM broken)
                         RETURNING id
                    )
                    SELECT COUNT(*) FROM cleared
                    """
                )
                removed = self.env.cr.fetchone()[0]
        except Exception:
            _logger.exception("Could not repair stale ir.ui.menu action pointers.")
            return 0
        if removed:
            self.env.registry.clear_cache()
            _logger.warning("Cleared %s stale ir.ui.menu action pointer(s).", removed)
        return removed

    @api.model
    def load_menus_root(self):
        self.sudo()._elsx_clear_broken_action_pointers()
        return super().load_menus_root()

    @api.model
    def load_menus(self, debug):
        self.sudo()._elsx_clear_broken_action_pointers()
        return super().load_menus(debug)
