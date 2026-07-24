# -*- coding: utf-8 -*-
import re
from urllib.parse import quote_plus

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..utils import is_saas_system_enabled


SAFE_DB_RE = re.compile(r'^[A-Za-z0-9_.-]+$')


def _ensure_saas_system_enabled(env):
    if not is_saas_system_enabled(env):
        raise UserError(_(
            'The SaaS system is deactivated. Provisioning, billing automation, and tenant module installation are disabled to protect production client data.'
        ))


class ELSXSaasTenant(models.Model):
    _name = 'elsx.saas.tenant'
    _description = 'ELSx SaaS Tenant'
    _order = 'create_date desc, name'

    name = fields.Char('Tenant Name / Subdomain', required=True)
    legal_name = fields.Char('Legal Company Name')
    db_name = fields.Char('Database Name', compute='_compute_db_name', inverse='_inverse_db_name', store=True, readonly=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('requested', 'Provision Requested'),
        ('provisioning', 'Provisioning'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('archived', 'Archived'),
    ], default='draft', required=True)
    plan = fields.Selection([
        ('starter', 'Starter'),
        ('business', 'Business'),
        ('enterprise', 'Enterprise'),
        ('custom', 'Custom'),
    ], default='starter', required=True)
    admin_email = fields.Char('Tenant Admin Email')
    admin_name = fields.Char('Tenant Admin Name')
    user_id = fields.Many2one('res.users', string='SaaS User (Owner)', help='The portal user who owns this tenant.')
    custom_domain = fields.Char('Custom Domain')
    base_url = fields.Char(
        'Base URL',
        help='Public URL used for this tenant. Leave blank until DNS/reverse proxy is configured.',
    )
    production_db = fields.Boolean('Production Tenant', default=True)
    backup_verified = fields.Boolean('Encrypted Backup Verified')
    allow_provisioning = fields.Boolean(
        'Allow Provision Request',
        help='Admin confirmation that backup, DNS, reverse proxy, and capacity checks are done.',
    )
    client_database_created = fields.Boolean('Database Created')
    filestore_present = fields.Boolean('Filestore Present')
    modules_upgraded = fields.Boolean('Modules Upgraded')
    webhook_checked = fields.Boolean('Webhook Checked')
    health_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('ok', 'OK'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], default='unknown')
    last_health_check = fields.Datetime()
    max_users = fields.Integer('Max Users', default=10)
    app_allowance = fields.Integer('App Allowance', default=3, help='Maximum number of custom/third-party apps allowed.')
    installed_app_count = fields.Integer(compute='_compute_module_request_count', string='Installed Apps')
    storage_quota_gb = fields.Integer('Storage Quota (GB)', default=5)
    enable_crm = fields.Boolean(default=True)
    enable_whatsapp = fields.Boolean(default=True)
    enable_accounting = fields.Boolean(default=True)
    enable_attendance = fields.Boolean(default=True)
    enable_tally = fields.Boolean(default=False)
    enable_face_attendance = fields.Boolean(default=False)
    notes = fields.Text()
    deployment_plan = fields.Text(compute='_compute_deployment_plan')
    protected_summary = fields.Text(compute='_compute_protected_summary')
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id.id,
        required=True,
    )
    billing_cycle = fields.Selection([
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('annual', 'Annual'),
        ('three_year', '3-Year'),
        ('five_year', '5-Year'),
        ('custom', 'Custom'),
    ], default='monthly', required=True)
    monthly_recurring_revenue = fields.Monetary('MRR', currency_field='currency_id')
    setup_fee = fields.Monetary(currency_field='currency_id')
    contract_start = fields.Date()
    contract_end = fields.Date()
    next_billing_date = fields.Date()
    payment_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('trial', 'Trial'),
        ('current', 'Current'),
        ('due', 'Due'),
        ('overdue', 'Overdue'),
        ('paused', 'Paused'),
    ], default='unknown')
    annual_recurring_revenue = fields.Monetary(
        'ARR',
        compute='_compute_revenue_metrics',
        currency_field='currency_id',
    )
    module_request_ids = fields.One2many('elsx.saas.module.request', 'tenant_id', string='Module Requests')
    module_request_count = fields.Integer(compute='_compute_module_request_count')
    approved_module_request_count = fields.Integer(compute='_compute_module_request_count')

    _db_name_unique = models.Constraint('UNIQUE (db_name)', 'Database name must be unique per SaaS tenant record.')

    @api.depends('name')
    def _compute_db_name(self):
        for record in self:
            if record.name and not record.db_name:
                slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', record.name.strip().lower()).strip('_.-')
                record.db_name = 'elsx_%s' % (slug or 'tenant')

    def _inverse_db_name(self):
        return

    @api.depends(
        'db_name',
        'admin_email',
        'enable_crm',
        'enable_whatsapp',
        'enable_accounting',
        'enable_attendance',
        'enable_tally',
        'enable_face_attendance',
    )
    def _compute_deployment_plan(self):
        for tenant in self:
            modules = tenant._selected_modules()
            tenant.deployment_plan = '\n'.join([
                '# 1. Create/restore tenant database manually from /web/database/manager',
                '# Database: %s' % (tenant.db_name or '<set database name>'),
                '# Tenant admin email: %s' % (tenant.admin_email or '<set admin email>'),
                '',
                '# 2. Upgrade only the tenant database after backup',
                'read -s -p "Backup passphrase: " BACKUP_PASSPHRASE',
                'echo',
                'export BACKUP_PASSPHRASE',
                'EXTRA_UPGRADE_MODULES=%s bash deploy/safe_production_update.sh %s' % (
                    ','.join(modules),
                    tenant.db_name or '<db_name>',
                ),
                '',
                '# 3. Start optional face sidecar only if face attendance was approved',
                '# docker compose --profile face up -d face_sidecar',
                '',
                '# 4. Verify login, CRM, WhatsApp, invoices, attendance, Tally, and logs.',
            ])

    @api.depends(
        'enable_crm',
        'enable_whatsapp',
        'enable_accounting',
        'enable_attendance',
        'enable_tally',
        'enable_face_attendance',
    )
    def _compute_protected_summary(self):
        for tenant in self:
            tenant.protected_summary = ', '.join(tenant._selected_modules())

    @api.depends('monthly_recurring_revenue')
    def _compute_revenue_metrics(self):
        for tenant in self:
            tenant.annual_recurring_revenue = tenant.monthly_recurring_revenue * 12

    @api.depends('module_request_ids.state')
    def _compute_module_request_count(self):
        for tenant in self:
            tenant.module_request_count = len(tenant.module_request_ids)
            tenant.approved_module_request_count = len(
                tenant.module_request_ids.filtered(lambda request: request.state in ('approved', 'staged', 'installed'))
            )
            tenant.installed_app_count = len(
                tenant.module_request_ids.filtered(lambda request: request.state == 'installed')
            )

    @api.constrains('db_name')
    def _check_db_name(self):
        for tenant in self:
            if tenant.db_name and not SAFE_DB_RE.match(tenant.db_name):
                raise ValidationError(_('Database name may contain only letters, numbers, dot, dash, and underscore.'))

    @api.constrains('admin_email')
    def _check_admin_email(self):
        for tenant in self:
            if tenant.admin_email and '@' not in tenant.admin_email:
                raise ValidationError(_('Tenant admin email must be a valid email address.'))

    def _selected_modules(self):
        self.ensure_one()
        modules = ['elsx_client_restrictions']
        if self.enable_crm:
            modules += ['contacts', 'crm', 'sale']
        if self.enable_accounting:
            modules.append('account')
        if self.enable_whatsapp:
            modules.append('elsx_whatsapp_marketing')
        if self.enable_attendance:
            modules += ['hr_attendance', 'elsx_attendance_tracking']
        if self.enable_tally:
            modules.append('elsx_tally_integration')
        if self.enable_face_attendance:
            modules.append('elsx_face_attendance')
        seen = []
        for module in modules:
            if module not in seen:
                seen.append(module)
        return seen

    def action_request_provisioning(self):
        _ensure_saas_system_enabled(self.env)
        self.ensure_one()
        if not self.backup_verified:
            raise UserError(_('Verify an encrypted backup before requesting tenant provisioning.'))
        if self.production_db and not self.allow_provisioning:
            raise UserError(_('Enable "Allow Provision Request" after DNS, reverse proxy, capacity, and backup checks are complete.'))
        self.state = 'requested'
        return self._notify(
            _('Provision request recorded'),
            _('Use the generated deployment plan. No database was created automatically.'),
            'success',
        )

    def action_mark_provisioning(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'provisioning'})
        return self._notify(_('Tenant marked provisioning'), _('Administrative state only. No live database was changed.'), 'info')

    def action_mark_active(self):
        _ensure_saas_system_enabled(self.env)
        for tenant in self:
            if not tenant.client_database_created:
                raise UserError(_('Mark "Database Created" before activating %s.') % tenant.display_name)
            if not tenant.modules_upgraded:
                raise UserError(_('Mark "Modules Upgraded" before activating %s.') % tenant.display_name)
        self.write({'state': 'active', 'health_status': 'ok', 'last_health_check': fields.Datetime.now()})
        return self._notify(_('Tenant activated'), _('Tenant registry was updated. Existing tenant data was not modified.'), 'success')

    def action_suspend(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'suspended', 'health_status': 'warning'})
        return self._notify(_('Tenant suspended in registry'), _('This does not disable logins by itself; apply access rules separately if required.'), 'warning')

    def action_archive(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'archived'})
        return self._notify(_('Tenant archived in registry'), _('No database, filestore, or user data was deleted.'), 'info')

    def action_reset_to_draft(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'draft'})
        return self._notify(_('Tenant reset to draft'), _('Administrative state only.'), 'info')

    def action_open_database_manager(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/database/manager',
            'target': 'new',
        }

    def action_open_tenant_url(self):
        self.ensure_one()
        url = ''
        if self.custom_domain:
            domain = self.custom_domain.strip().rstrip('/')
            if not domain.startswith('http'):
                domain = 'https://' + domain
            url = '%s/?db=%s' % (domain, quote_plus(self.db_name or ''))
        elif self.base_url:
            db_query = quote_plus(self.db_name or '')
            separator = '&' if '?' in self.base_url else '?'
            url = '%s%sdb=%s' % (self.base_url.rstrip('/'), separator, db_query)
        else:
            raise UserError(_('Set Base URL or Custom Domain first.'))

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_copy_plan_notice(self):
        self.ensure_one()
        return self._notify(
            _('Deployment plan ready'),
            _('Open the Deployment Plan tab and run those commands from the server shell.'),
            'info',
        )

    def action_open_module_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Module Requests'),
            'res_model': 'elsx.saas.module.request',
            'view_mode': 'list,form',
            'domain': [('tenant_id', '=', self.id)],
            'context': {'default_tenant_id': self.id},
        }

    def _notify(self, title, message, notification_type='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notification_type,
                'sticky': False,
            },
        }


class ELSXSaasModuleRequest(models.Model):
    _name = 'elsx.saas.module.request'
    _description = 'ELSx SaaS Third-Party Module Request'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True)
    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade')
    app_id = fields.Many2one('elsx.saas.app', string='App from Catalog')
    module_name = fields.Char(
        help='Technical module name, for example website_sale or vendor_custom_module.',
    )
    source_type = fields.Selection([
        ('standard', 'Standard Addon'),
        ('custom', 'Custom Addon'),
        ('third_party', 'Third-Party Addon'),
    ], default='third_party', required=True)
    vendor = fields.Char()

    @api.onchange('app_id')
    def _onchange_app_id(self):
        if self.app_id:
            self.name = self.app_id.name
            self.module_name = self.app_id.module_name
            self.monthly_cost = self.app_id.monthly_price
            self.one_time_cost = self.app_id.one_time_price
    license_reference = fields.Char()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Review'),
        ('approved', 'Approved'),
        ('staged', 'Staged'),
        ('installed', 'Installed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True)
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('blocked', 'Blocked'),
    ], default='medium', required=True)
    currency_id = fields.Many2one(related='tenant_id.currency_id', store=True, readonly=True)
    one_time_cost = fields.Monetary(currency_field='currency_id')
    monthly_cost = fields.Monetary(currency_field='currency_id')
    requires_python_package = fields.Boolean()
    requires_node_package = fields.Boolean()
    requires_external_service = fields.Boolean()
    touches_accounting = fields.Boolean()
    touches_whatsapp = fields.Boolean()
    touches_attendance = fields.Boolean()
    touches_crm = fields.Boolean()
    backup_verified = fields.Boolean('Backup Verified')
    manifest_reviewed = fields.Boolean('Manifest Reviewed')
    dependency_reviewed = fields.Boolean('Dependencies Reviewed')
    staging_tested = fields.Boolean('Staging Tested')
    production_approved = fields.Boolean('Production Approved')
    notes = fields.Text()
    rejection_reason = fields.Text()
    impact_summary = fields.Text(compute='_compute_impact_summary')
    deployment_plan = fields.Text(compute='_compute_deployment_plan')

    @api.constrains('module_name')
    def _check_module_name(self):
        for request in self:
            if request.module_name and not SAFE_DB_RE.match(request.module_name):
                raise ValidationError(_('Module technical name may contain only letters, numbers, dot, dash, and underscore.'))

    @api.depends(
        'module_name',
        'source_type',
        'risk_level',
        'requires_python_package',
        'requires_node_package',
        'requires_external_service',
        'touches_accounting',
        'touches_whatsapp',
        'touches_attendance',
        'touches_crm',
        'backup_verified',
        'manifest_reviewed',
        'dependency_reviewed',
        'staging_tested',
        'production_approved',
    )
    def _compute_impact_summary(self):
        for request in self:
            impacted = []
            if request.touches_crm:
                impacted.append(_('CRM'))
            if request.touches_whatsapp:
                impacted.append(_('WhatsApp Marketing'))
            if request.touches_accounting:
                impacted.append(_('Accounting/Invoicing'))
            if request.touches_attendance:
                impacted.append(_('Attendance'))
            checks = [
                _('Backup verified: %s') % (_('Yes') if request.backup_verified else _('No')),
                _('Manifest reviewed: %s') % (_('Yes') if request.manifest_reviewed else _('No')),
                _('Dependencies reviewed: %s') % (_('Yes') if request.dependency_reviewed else _('No')),
                _('Staging tested: %s') % (_('Yes') if request.staging_tested else _('No')),
                _('Production approved: %s') % (_('Yes') if request.production_approved else _('No')),
            ]
            extras = []
            if request.requires_python_package:
                extras.append(_('Python package'))
            if request.requires_node_package:
                extras.append(_('Node package'))
            if request.requires_external_service:
                extras.append(_('External service'))
            request.impact_summary = '\n'.join([
                _('Module: %s') % (request.module_name or '-'),
                _('Source: %s') % dict(request._fields['source_type'].selection).get(request.source_type, request.source_type),
                _('Risk: %s') % dict(request._fields['risk_level'].selection).get(request.risk_level, request.risk_level),
                _('Business areas touched: %s') % (', '.join(impacted) or _('None selected')),
                _('Extra runtime needs: %s') % (', '.join(extras) or _('None')),
                '',
                *checks,
            ])

    @api.depends('tenant_id.db_name', 'module_name')
    def _compute_deployment_plan(self):
        for request in self:
            request.deployment_plan = _('SaaS system is deactivated. Tenant module installation is disabled and no client database will be changed from this UI.')

    def action_submit_review(self):
        _ensure_saas_system_enabled(self.env)
        for request in self:
            if request.tenant_id.installed_app_count >= request.tenant_id.app_allowance:
                raise UserError(_('App Allowance Exceeded! This tenant is only allowed %s apps. Please upgrade their plan or increase the allowance.') % request.tenant_id.app_allowance)
        self.write({'state': 'review'})
        return self._notify(_('Module request submitted'), _('Review manifest, dependencies, and staging plan before approval.'), 'info')

    def action_approve(self):
        _ensure_saas_system_enabled(self.env)
        for request in self:
            if request.risk_level == 'blocked':
                raise UserError(_('Blocked-risk module requests cannot be approved.'))
            missing = []
            if not request.backup_verified:
                missing.append(_('Backup Verified'))
            if not request.manifest_reviewed:
                missing.append(_('Manifest Reviewed'))
            if not request.dependency_reviewed:
                missing.append(_('Dependencies Reviewed'))
            if missing:
                raise UserError(_('Complete these checks before approval: %s') % ', '.join(missing))
        self.write({'state': 'approved'})
        return self._notify(_('Module request approved'), _('Use staging before production deployment.'), 'success')

    def action_mark_staged(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'staged', 'staging_tested': True})
        return self._notify(_('Module staged'), _('Production remains unchanged until the safe deployment script is run.'), 'success')

    def action_mark_installed(self):
        _ensure_saas_system_enabled(self.env)
        for request in self:
            if not request.production_approved:
                raise UserError(_('Mark Production Approved before setting this request installed.'))
            if request.monthly_cost > 0:
                request.tenant_id.monthly_recurring_revenue += request.monthly_cost
        self.write({'state': 'installed'})
        return self._notify(_('Module request installed'), _('Registry updated only. Verify tenant health after deployment.'), 'success')

    def action_install_tenant_module(self):
        _ensure_saas_system_enabled(self.env)
        self.ensure_one()
        import odoo
        from odoo import api, SUPERUSER_ID
        from odoo.exceptions import UserError

        if not self.tenant_id.db_name:
            raise UserError(_('Tenant has no database assigned.'))
        if self.state not in ['approved', 'staged']:
            raise UserError(_('Request must be approved or staged before installation.'))

        try:
            db_registry = odoo.registry(self.tenant_id.db_name)
            with db_registry.cursor() as tenant_cr:
                tenant_env = api.Environment(tenant_cr, SUPERUSER_ID, {})
                module = tenant_env['ir.module.module'].search([('name', '=', self.module_name)])
                if not module:
                    # Update local module list for tenant first just in case
                    tenant_env['ir.module.module'].update_list()
                    module = tenant_env['ir.module.module'].search([('name', '=', self.module_name)])

                if not module:
                    raise UserError(_('Module %s not found in tenant database even after update_list.') % self.module_name)

                module.button_immediate_install()
        except Exception as e:
            raise UserError(_('Failed to install module on tenant database: %s') % str(e))

        self.production_approved = True
        self.action_mark_installed()
        return self._notify(_('Module installed automatically'), _('Successfully installed %s on tenant %s.') % (self.module_name, self.tenant_id.db_name), 'success')

    def action_reject(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'rejected'})
        return self._notify(_('Module request rejected'), _('No server or tenant data was changed.'), 'warning')

    def action_reset_draft(self):
        _ensure_saas_system_enabled(self.env)
        self.write({'state': 'draft'})
        return self._notify(_('Module request reset'), _('Administrative state only.'), 'info')

    def _notify(self, title, message, notification_type='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notification_type,
                'sticky': False,
            },
        }
