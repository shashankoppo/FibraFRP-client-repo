# -*- coding: utf-8 -*-
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)

ASSET_REPAIR_MARKER = 'apps-settings-saas-assets-2026-07-16-v2'


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
    def _elsx_get_apps_password_action(self):
        """Return/create the Apps password gate action.

        The record is created at runtime so production deployments that only
        pull code and rebuild containers do not need an immediate module update.
        """
        action = self._elsx_ref('elsx_client_restrictions.action_apps_password_gate')
        if action and action._name == 'ir.actions.act_url':
            return action.sudo()

        action_model = self.env['ir.actions.act_url'].sudo()
        action = action_model.search([('url', '=', '/elsx/apps/unlock')], limit=1)
        if not action:
            action = action_model.create({
                'name': 'Apps Password Gate',
                'url': '/elsx/apps/unlock',
                'target': 'self',
            })

        imd = self.env['ir.model.data'].sudo()
        if not imd.search([
            ('module', '=', 'elsx_client_restrictions'),
            ('name', '=', 'action_apps_password_gate'),
            ('model', '=', 'ir.actions.act_url'),
        ], limit=1):
            imd.create({
                'module': 'elsx_client_restrictions',
                'name': 'action_apps_password_gate',
                'model': 'ir.actions.act_url',
                'res_id': action.id,
                'noupdate': True,
            })
        return action

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
            apps_gate_action = self._elsx_get_apps_password_action() or module_action
            settings_action = self._elsx_ref('base_setup.action_general_configuration')
            menu_specs = (
                ('base.menu_administration', settings_action),
                ('base.menu_management', apps_gate_action),
                ('base.menu_apps', apps_gate_action),
                ('base.menu_module_tree', apps_gate_action),
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
                    vals['action'] = '%s,%s' % (action._name, action.id)
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
    def _elsx_deactivate_saas_metadata(self):
        """Hide the removed SaaS feature during normal container rebuilds.

        Existing production databases may still have ``elsx_saas`` installed,
        and deploys often only rebuild containers without running ``-u`` or an
        uninstall. This cleanup is deliberately limited to SaaS technical
        metadata so customer operational records remain intact.
        """
        try:
            module = self.env['ir.module.module'].sudo().search([('name', '=', 'elsx_saas')], limit=1)
            if not module:
                return

            params = self.env['ir.config_parameter'].sudo()
            if params.get_param('elsx_saas.enabled') != '0':
                params.set_param('elsx_saas.enabled', '0')

            saas_groups = self.env['res.groups'].sudo()
            for xmlid in (
                'elsx_saas.group_elsx_saas_app_user',
                'elsx_saas.group_elsx_saas_user',
                'elsx_saas.group_elsx_saas_admin',
            ):
                group = self._elsx_ref(xmlid)
                if group:
                    saas_groups |= group.sudo()

            base_user = self._elsx_ref('base.group_user')
            base_system = self._elsx_ref('base.group_system')
            base_apps_menu = self._elsx_ref('base.menu_management')
            changed_group_count = 0
            for group in saas_groups:
                changed = False
                if base_user and group.id in base_user.sudo().implied_ids.ids:
                    base_user.sudo().write({'implied_ids': [(3, group.id)]})
                    changed = True
                if base_system and group.id in base_system.sudo().implied_ids.ids:
                    base_system.sudo().write({'implied_ids': [(3, group.id)]})
                    changed = True
                if base_apps_menu and group.id in base_apps_menu.sudo().group_ids.ids:
                    base_apps_menu.sudo().write({'group_ids': [(3, group.id)]})
                    changed = True
                if group.users:
                    # Remove only SaaS-specific group memberships so old user
                    # assignments cannot keep the removed SaaS app visible.
                    group.write({'users': [(5, 0, 0)]})
                    changed = True
                if changed:
                    changed_group_count += 1

            imd = self.env['ir.model.data'].sudo()
            menu_ids = imd.search([
                ('module', '=', 'elsx_saas'),
                ('model', '=', 'ir.ui.menu'),
            ]).mapped('res_id')
            menus = self.env['ir.ui.menu'].sudo().with_context(active_test=False).browse(menu_ids).exists()
            root_menu = self._elsx_ref('elsx_saas.menu_elsx_saas_root')
            if root_menu:
                menus |= self.env['ir.ui.menu'].sudo().with_context(active_test=False).search([
                    ('id', 'child_of', root_menu.id),
                ])
            active_menus = menus.filtered('active')
            if active_menus:
                active_menus.write({'active': False})

            view_ids = imd.search([
                ('module', '=', 'elsx_saas'),
                ('model', '=', 'ir.ui.view'),
            ]).mapped('res_id')
            views = self.env['ir.ui.view'].sudo().with_context(active_test=False).browse(view_ids).exists()
            active_views = views.filtered('active')
            if active_views:
                active_views.write({'active': False})

            cron_ids = imd.search([
                ('module', '=', 'elsx_saas'),
                ('model', '=', 'ir.cron'),
            ]).mapped('res_id')
            crons = self.env['ir.cron'].sudo().with_context(active_test=False).browse(cron_ids).exists()
            active_crons = crons.filtered('active')
            if active_crons:
                active_crons.write({'active': False})

            if active_menus or changed_group_count or active_views or active_crons:
                self.env.registry.clear_cache()
                _logger.info(
                    'Deactivated SaaS metadata during startup repair: %s menus, %s groups, %s views, %s crons.',
                    len(active_menus), changed_group_count, len(active_views), len(active_crons),
                )
        except Exception:
            _logger.exception('Could not deactivate SaaS metadata during startup repair.')

    @api.model
    def _elsx_refresh_backend_assets_once(self):
        """Drop stale generated backend assets once after this repair ships."""
        try:
            params = self.env['ir.config_parameter'].sudo()
            if params.get_param('elsx_client_restrictions.asset_repair_marker') == ASSET_REPAIR_MARKER:
                return

            assets = self.env['ir.attachment'].sudo().search([
                ('url', '=like', '/web/assets/%'),
            ])
            count = len(assets)
            if assets:
                assets.unlink()

            params.set_param('elsx_client_restrictions.asset_repair_marker', ASSET_REPAIR_MARKER)
            self.env.registry.clear_cache('assets')
            self.env.registry.clear_cache('templates')
            if count:
                _logger.info('Cleared %s generated web asset attachment(s) after Apps/Settings repair.', count)
        except Exception:
            _logger.exception('Could not clear generated web asset attachments after Apps/Settings repair.')

    @api.model
    def _elsx_repair_startup_metadata(self):
        self._elsx_restore_core_admin_metadata()
        self._elsx_repair_known_settings_views()
        self._elsx_deactivate_saas_metadata()
        self._elsx_refresh_backend_assets_once()

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
