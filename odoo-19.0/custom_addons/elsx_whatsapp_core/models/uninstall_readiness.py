# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from ..hooks import _target_module_for_data, sync_legacy_ownership


AUTHORIZATION_TTL_MINUTES = 15
BACKUP_MAX_AGE_HOURS = 24
EXPECTED_CONFIRMATION = 'UNINSTALL ELSX WHATSAPP MARKETING'


class ElsxWhatsAppUninstallReadiness(models.Model):
    _name = 'elsx.whatsapp.uninstall.readiness'
    _description = 'ELSX WhatsApp Uninstall Readiness Audit'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, readonly=True)
    database_name = fields.Char(required=True, readonly=True, index=True)
    requested_by_id = fields.Many2one(
        'res.users',
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('blocked', 'Blocked'),
        ('ready', 'Ready'),
        ('authorized', 'Authorized'),
        ('consumed', 'Consumed'),
        ('expired', 'Expired'),
    ], required=True, default='draft', readonly=True, index=True)
    checked_at = fields.Datetime(readonly=True)
    authorization_expires_at = fields.Datetime(readonly=True, index=True)
    authorized_at = fields.Datetime(readonly=True)
    consumed_at = fields.Datetime(readonly=True)
    backup_reference = fields.Char(readonly=True)
    backup_confirmed = fields.Boolean(readonly=True)
    confirmation_matched = fields.Boolean(readonly=True)
    blocker_count = fields.Integer(readonly=True)
    report_json = fields.Text(readonly=True)
    report_text = fields.Text(readonly=True)
    authorization_token_hash = fields.Char(readonly=True, groups='base.group_system')

    @api.model
    def expected_confirmation(self):
        return EXPECTED_CONFIRMATION

    @api.model
    def _assert_apps_password(self):
        module_model = self.env['ir.module.module']
        checker = getattr(module_model, '_elsx_check_apps_password_unlocked', None)
        if not checker:
            raise UserError(_(
                'The Apps password guard is not installed. WhatsApp uninstall authorization is unavailable.'
            ))
        checker()

    @api.model
    def _installed_module(self, name):
        return self.env['ir.module.module'].sudo().search([
            ('name', '=', name),
            ('state', 'in', ('installed', 'to upgrade')),
        ], limit=1)

    @api.model
    def _server_wide_modules(self):
        configured = tools.config.get('server_wide_modules') or []
        if isinstance(configured, str):
            configured = configured.split(',')
        return {name.strip() for name in configured if name and name.strip()}

    @api.model
    def _backup_check(self, reference, confirmed):
        params = self.env['ir.config_parameter'].sudo()
        marker_reference = params.get_param(
            'elsx.whatsapp.last_verified_backup.reference',
            default='',
        )
        marker_database = params.get_param(
            'elsx.whatsapp.last_verified_backup.database',
            default='',
        )
        marker_checksum = params.get_param(
            'elsx.whatsapp.last_verified_backup.sha256',
            default='',
        )
        marker_time = params.get_param(
            'elsx.whatsapp.last_verified_backup.verified_at',
            default='',
        )
        verified_at = fields.Datetime.to_datetime(marker_time) if marker_time else False
        fresh = bool(
            verified_at
            and verified_at >= fields.Datetime.now() - timedelta(hours=BACKUP_MAX_AGE_HOURS)
        )
        ok = bool(
            confirmed
            and reference
            and reference == marker_reference
            and marker_database == self.env.cr.dbname
            and marker_checksum
            and fresh
        )
        detail = _(
            'Backup marker must match this database, include a SHA-256 checksum, and be no older than 24 hours.'
        )
        if ok:
            detail = _('Verified encrypted backup marker: %s') % marker_reference
        return ok, detail

    @api.model
    def _ownership_gaps(self):
        sync_legacy_ownership(self.env)
        Data = self.env['ir.model.data'].sudo()
        xml_id_gaps = 0
        for legacy in Data.search([('module', '=', 'elsx_whatsapp_marketing')]):
            target_module = _target_module_for_data(self.env, legacy)
            if not target_module:
                continue
            if not Data.search_count([
                ('module', '=', target_module),
                ('model', '=', legacy.model),
                ('res_id', '=', legacy.res_id),
            ]):
                xml_id_gaps += 1
        self.env.cr.execute(
            '''
            SELECT count(*)
              FROM ir_model_relation AS legacy_relation
              JOIN ir_module_module AS legacy_module
                ON legacy_module.id = legacy_relation.module
             WHERE legacy_module.name = 'elsx_whatsapp_marketing'
               AND NOT EXISTS (
                   SELECT 1
                     FROM ir_model_relation AS core_relation
                     JOIN ir_module_module AS core_module
                       ON core_module.id = core_relation.module
                    WHERE core_relation.name = legacy_relation.name
                      AND core_module.name = 'elsx_whatsapp_core'
               )
            '''
        )
        relation_gaps = self.env.cr.fetchone()[0]
        return xml_id_gaps, relation_gaps

    @api.model
    def _collect_checks(self, backup_reference, backup_confirmed, confirmation):
        checks = []

        def add(code, label, ok, detail):
            checks.append({
                'code': code,
                'label': label,
                'ok': bool(ok),
                'detail': detail,
            })

        core = self._installed_module('elsx_whatsapp_core')
        gateway = self._installed_module('elsx_whatsapp_gateway')
        marketing = self._installed_module('elsx_whatsapp_marketing')
        add('core', _('WhatsApp Core'), core, _('Installed') if core else _('Not installed'))
        add('gateway', _('WhatsApp Gateway'), gateway, _('Installed') if gateway else _('Not installed'))
        add('shell', _('WhatsApp application shell'), marketing, _('Installed') if marketing else _('Not installed'))

        server_wide = self._server_wide_modules()
        gateway_wide = 'elsx_whatsapp_gateway' in server_wide
        shell_wide = 'elsx_whatsapp_marketing' in server_wide
        add(
            'server_wide',
            _('Server-wide module handoff'),
            gateway_wide and not shell_wide,
            _('Gateway is server-wide and the removable shell is not.')
            if gateway_wide and not shell_wide
            else _('Update server_wide_modules to use only elsx_whatsapp_gateway.'),
        )

        dependents = marketing.downstream_dependencies() if marketing else self.env['ir.module.module']
        dependents -= marketing
        add(
            'dependents',
            _('Installed dependent modules'),
            not dependents,
            _('None') if not dependents else ', '.join(sorted(dependents.mapped('name'))),
        )

        queue_checks = [
            ('campaigns', 'whatsapp.campaign', [('state', 'in', ('scheduled', 'running'))]),
            ('queued_messages', 'whatsapp.message', [('status', '=', 'queued')]),
            ('scheduled_messages', 'whatsapp.scheduled.message', [('status', 'in', ('scheduled', 'running'))]),
            ('scheduled_campaigns', 'whatsapp.scheduled.campaign', [('status', 'in', ('scheduled', 'running'))]),
            ('active_flows', 'whatsapp.bot.flow.log', [('status', 'in', ('pending', 'running'))]),
        ]
        for code, model_name, domain in queue_checks:
            count = self.env[model_name].sudo().search_count(domain) if model_name in self.env else -1
            add(
                code,
                code.replace('_', ' ').title(),
                count == 0,
                _('Count: %s') % count,
            )

        xml_id_gaps, relation_gaps = self._ownership_gaps()
        add(
            'ownership',
            _('Core metadata ownership'),
            xml_id_gaps == 0 and relation_gaps == 0,
            _('XML ID gaps: %(xml)s; relation ownership gaps: %(relations)s') % {
                'xml': xml_id_gaps,
                'relations': relation_gaps,
            },
        )

        backup_ok, backup_detail = self._backup_check(backup_reference, backup_confirmed)
        add('backup', _('Encrypted backup'), backup_ok, backup_detail)
        confirmation_ok = confirmation == EXPECTED_CONFIRMATION
        add(
            'confirmation',
            _('Typed confirmation'),
            confirmation_ok,
            _('Exact confirmation matched.') if confirmation_ok else _(
                'Type exactly: %s'
            ) % EXPECTED_CONFIRMATION,
        )
        return checks

    @api.model
    def create_readiness(self, backup_reference, backup_confirmed, confirmation):
        self._assert_apps_password()
        record = self.sudo().create({
            'name': _('WhatsApp uninstall readiness - %s') % fields.Datetime.now(),
            'database_name': self.env.cr.dbname,
            'requested_by_id': self.env.user.id,
            'backup_reference': backup_reference,
            'backup_confirmed': backup_confirmed,
            'confirmation_matched': confirmation == EXPECTED_CONFIRMATION,
        })
        record._refresh_checks(confirmation)
        return record

    def _refresh_checks(self, confirmation=None):
        self.ensure_one()
        confirmation = confirmation if confirmation is not None else (
            EXPECTED_CONFIRMATION if self.confirmation_matched else ''
        )
        checks = self._collect_checks(
            self.backup_reference,
            self.backup_confirmed,
            confirmation,
        )
        blockers = [check for check in checks if not check['ok']]
        lines = [
            '[OK] %s: %s' % (check['label'], check['detail'])
            if check['ok']
            else '[BLOCKED] %s: %s' % (check['label'], check['detail'])
            for check in checks
        ]
        self.write({
            'state': 'blocked' if blockers else 'ready',
            'checked_at': fields.Datetime.now(),
            'blocker_count': len(blockers),
            'report_json': json.dumps(checks, sort_keys=True),
            'report_text': '\n'.join(lines),
            'authorization_token_hash': False,
            'authorization_expires_at': False,
        })
        return not blockers

    def issue_authorization(self):
        self.ensure_one()
        self._assert_apps_password()
        if not self._refresh_checks():
            raise UserError(_(
                'WhatsApp uninstall remains blocked. Resolve every readiness item and run the audit again.'
            ))
        token = secrets.token_urlsafe(32)
        self.write({
            'state': 'authorized',
            'authorization_token_hash': hashlib.sha256(token.encode()).hexdigest(),
            'authorization_expires_at': fields.Datetime.now() + timedelta(
                minutes=AUTHORIZATION_TTL_MINUTES
            ),
            'authorized_at': fields.Datetime.now(),
        })
        return token

    @api.model
    def validate_authorization_token(self, token):
        if not token:
            raise UserError(_('A WhatsApp uninstall authorization token is required.'))
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        records = self.sudo().search([
            ('database_name', '=', self.env.cr.dbname),
            ('state', '=', 'authorized'),
            ('authorization_expires_at', '>=', fields.Datetime.now()),
        ], order='id desc')
        for record in records:
            if hmac.compare_digest(record.authorization_token_hash or '', token_hash):
                return record
        raise UserError(_('The WhatsApp uninstall authorization is invalid, expired, or already used.'))

    @api.model
    def authorized_for_finalize(self):
        record = self.sudo().search([
            ('database_name', '=', self.env.cr.dbname),
            ('state', '=', 'authorized'),
            ('authorization_expires_at', '>=', fields.Datetime.now()),
        ], order='id desc', limit=1)
        if not record:
            raise UserError(_('No active WhatsApp uninstall authorization is available.'))
        return record

    def prepare_uninstall(self):
        self.ensure_one()
        if self.state != 'authorized' or self.authorization_expires_at < fields.Datetime.now():
            raise UserError(_('The WhatsApp uninstall authorization has expired.'))
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('whatsapp.runtime.enabled', 'False')
        cron_data = self.env['ir.model.data'].sudo().search([
            ('module', 'in', ('elsx_whatsapp_marketing', 'elsx_whatsapp_core')),
            ('model', '=', 'ir.cron'),
        ])
        self.env['ir.cron'].sudo().browse(cron_data.mapped('res_id')).exists().write({
            'active': False,
        })
        return True

    def consume(self):
        self.ensure_one()
        if self.state != 'authorized':
            raise UserError(_('The WhatsApp uninstall authorization is not active.'))
        self.write({
            'state': 'consumed',
            'consumed_at': fields.Datetime.now(),
            'authorization_token_hash': False,
        })
        return True
