# -*- coding: utf-8 -*-
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


AI_OCR_SETTINGS_ARCH = """
<data>
    <xpath expr="//form" position="inside">
        <app data-string="ELSX AI OCR" string="ELSX AI OCR" name="elsx_ai_ocr" groups="base.group_system">
            <block title="Vision Engine" id="elsx_ai_ocr_settings">
                <setting id="elsx_active_llm_engine_setting" help="Select the abstracted AI backend used for OCR and document extraction.">
                    <field name="elsx_active_llm_engine"/>
                </setting>
                <setting id="elsx_openai_api_key_setting" help="Optional API key for Vision extraction. Leave empty when using a non-OpenAI engine.">
                    <field name="elsx_openai_api_key" password="True"/>
                </setting>
            </block>
        </app>
    </xpath>
</data>
"""


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _elsx_ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    @api.model
    def _elsx_restore_core_admin_metadata(self):
        """Repair old access-helper metadata during normal container startup.

        Production deploys commonly use ``docker compose up -d --build`` without
        a module upgrade. Keep this repair tightly scoped to core Odoo technical
        metadata so a restart cannot touch client business data.
        """
        if self.env.context.get('elsx_skip_core_admin_metadata_repair'):
            return

        try:
            group_system = self._elsx_ref('base.group_system')
            module_action = self._elsx_ref('base.open_module_tree')
            menu_specs = (
                ('base.menu_administration', None),
                ('base.menu_management', None),
                ('base.menu_apps', module_action),
            )
            repaired = []
            for xmlid, action in menu_specs:
                menu = self._elsx_ref(xmlid)
                if not menu:
                    continue
                menu = menu.sudo()
                vals = {}
                if not menu.active:
                    vals['active'] = True
                if group_system and group_system not in menu.group_ids:
                    vals.setdefault('group_ids', []).append((4, group_system.id))
                if action and menu.action != action:
                    vals['action'] = 'ir.actions.act_window,%s' % action.id
                if vals:
                    menu.write(vals)
                    repaired.append(xmlid)
            if repaired:
                _logger.info('Repaired core admin menu metadata: %s', ', '.join(repaired))
        except Exception:
            _logger.exception('Could not repair core admin menu metadata.')

    @api.model
    def _elsx_repair_known_settings_views(self):
        """Repair stale Settings view xpaths left by older optional modules."""
        try:
            view = self._elsx_ref('elsx_ai_ocr.res_config_settings_view_form')
            base_view = self._elsx_ref('base.res_config_settings_view_form')
            if not view or not base_view:
                return
            arch = view.arch_db or ''
            needs_repair = "//div[hasclass('settings')]" in arch or '<h2>ELSX AI Engines</h2>' in arch
            if not needs_repair:
                return
            view.sudo().with_context(lang=None, no_save_prev=True).write({
                'inherit_id': base_view.id,
                'arch_db': AI_OCR_SETTINGS_ARCH,
                'arch_prev': False,
                'arch_updated': False,
                'active': True,
            })
            self.env.registry.clear_cache()
            _logger.info('Repaired stale ELSX AI OCR Settings view metadata.')
        except Exception:
            _logger.exception('Could not repair stale ELSX AI OCR Settings view metadata.')

    @api.model
    def _elsx_repair_startup_metadata(self):
        self._elsx_restore_core_admin_metadata()
        self._elsx_repair_known_settings_views()

    @api.model
    def load_menus(self, debug):
        """
        Compatibility hook from the old access-helper addon.

        The system no longer hides menus here. Standard Odoo access groups
        decide what each user can see. A tiny idempotent metadata repair keeps
        older production DBs compatible with plain docker compose rebuilds.
        """
        self._elsx_repair_startup_metadata()
        return super(IrUiMenu, self).load_menus(debug)
