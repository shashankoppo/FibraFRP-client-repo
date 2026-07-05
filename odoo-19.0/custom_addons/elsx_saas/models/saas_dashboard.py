from odoo import _, fields, models


class ELSXSaasDashboard(models.TransientModel):
    _name = 'elsx.saas.dashboard'
    _description = 'ELSx SaaS Command Center'

    name = fields.Char(default='ELSx SaaS Command Center')
    tenant_count = fields.Integer(compute='_compute_metrics')
    active_tenant_count = fields.Integer(compute='_compute_metrics')
    warning_tenant_count = fields.Integer(compute='_compute_metrics')
    suspended_tenant_count = fields.Integer(compute='_compute_metrics')
    pending_module_request_count = fields.Integer(compute='_compute_metrics')
    high_risk_module_request_count = fields.Integer(compute='_compute_metrics')
    open_ticket_count = fields.Integer(compute='_compute_metrics')
    breached_ticket_count = fields.Integer(compute='_compute_metrics')
    open_invoice_count = fields.Integer(compute='_compute_metrics')
    overdue_invoice_count = fields.Integer(compute='_compute_metrics')
    mrr_total = fields.Monetary(compute='_compute_metrics', currency_field='company_currency_id')
    arr_total = fields.Monetary(compute='_compute_metrics', currency_field='company_currency_id')
    company_currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    confidentiality_status = fields.Selection(
        [('ok', 'Ready'), ('warning', 'Needs Review'), ('danger', 'Risk')],
        compute='_compute_metrics',
    )
    integrity_status = fields.Selection(
        [('ok', 'Ready'), ('warning', 'Needs Review'), ('danger', 'Risk')],
        compute='_compute_metrics',
    )
    availability_status = fields.Selection(
        [('ok', 'Ready'), ('warning', 'Needs Review'), ('danger', 'Risk')],
        compute='_compute_metrics',
    )
    confidentiality_note = fields.Text(compute='_compute_metrics')
    integrity_note = fields.Text(compute='_compute_metrics')
    availability_note = fields.Text(compute='_compute_metrics')
    operator_guidance = fields.Text(compute='_compute_metrics')

    def _compute_metrics(self):
        Tenant = self.env['elsx.saas.tenant'].sudo()
        ModuleRequest = self.env['elsx.saas.module.request'].sudo()
        Ticket = self.env['elsx.saas.support.ticket'].sudo()
        BillingCycle = self.env['elsx.saas.billing.cycle'].sudo()

        tenant_count = Tenant.search_count([])
        active_tenant_count = Tenant.search_count([('state', '=', 'active')])
        warning_tenant_count = Tenant.search_count([
            '|',
            ('health_status', 'in', ('warning', 'error')),
            ('backup_verified', '=', False),
        ])
        suspended_tenant_count = Tenant.search_count([('state', 'in', ('suspended', 'archived'))])
        pending_module_request_count = ModuleRequest.search_count([
            ('state', 'in', ('draft', 'review', 'approved', 'staged')),
        ])
        high_risk_module_request_count = ModuleRequest.search_count([
            ('risk_level', 'in', ('high', 'critical')),
            ('state', 'not in', ('installed', 'cancelled', 'rejected')),
        ])
        open_ticket_count = Ticket.search_count([('state', 'not in', ('resolved', 'closed'))])
        breached_ticket_count = Ticket.search_count([('sla_status', '=', 'breached')])
        open_invoice_count = BillingCycle.search_count([('payment_status', 'in', ('draft', 'sent', 'partial'))])
        overdue_invoice_count = BillingCycle.search_count([('payment_status', '=', 'overdue')])
        active_tenants = Tenant.search([('state', '=', 'active')])
        mrr_total = sum(active_tenants.mapped('monthly_recurring_revenue'))
        arr_total = sum(active_tenants.mapped('annual_recurring_revenue'))

        confidentiality_status = 'ok'
        confidentiality_note = _('Tenant data remains inside each database. API tokens and SaaS records are visible only to SaaS administrators.')
        if pending_module_request_count:
            confidentiality_status = 'warning'
            confidentiality_note = _('Review pending module requests before install/upgrade. Do not install third-party modules without dependency and data-scope review.')

        integrity_status = 'ok'
        integrity_note = _('Backup-first workflow is ready. Browser actions do not create, drop, clone, or rewrite tenant databases.')
        if warning_tenant_count:
            integrity_status = 'warning'
            integrity_note = _('Some tenants need backup or health review before any upgrade. Use the readiness audit before deployment.')

        availability_status = 'ok'
        availability_note = _('No critical availability signals are currently recorded in the SaaS console.')
        if breached_ticket_count or overdue_invoice_count or suspended_tenant_count:
            availability_status = 'warning'
            availability_note = _('Open SLA, billing, or suspended tenant issues need attention before broad tenant rollout.')

        guidance = [
            _('1. Review tenants with missing backup or warning health status.'),
            _('2. Approve module requests only after manifest, dependency, and production impact review.'),
            _('3. Use TARGET_DBS for production updates; avoid all-database upgrades unless deliberately planned.'),
            _('4. Keep WhatsApp Marketing, CRM, invoices, attendance, and Tally isolated unless a confirmed bug needs a scoped fix.'),
        ]

        for dashboard in self:
            dashboard.tenant_count = tenant_count
            dashboard.active_tenant_count = active_tenant_count
            dashboard.warning_tenant_count = warning_tenant_count
            dashboard.suspended_tenant_count = suspended_tenant_count
            dashboard.pending_module_request_count = pending_module_request_count
            dashboard.high_risk_module_request_count = high_risk_module_request_count
            dashboard.open_ticket_count = open_ticket_count
            dashboard.breached_ticket_count = breached_ticket_count
            dashboard.open_invoice_count = open_invoice_count
            dashboard.overdue_invoice_count = overdue_invoice_count
            dashboard.mrr_total = mrr_total
            dashboard.arr_total = arr_total
            dashboard.confidentiality_status = confidentiality_status
            dashboard.integrity_status = integrity_status
            dashboard.availability_status = availability_status
            dashboard.confidentiality_note = confidentiality_note
            dashboard.integrity_note = integrity_note
            dashboard.availability_note = availability_note
            dashboard.operator_guidance = '\n'.join(guidance)

    def _open_action(self, xmlid, domain=None):
        action = self.env.ref(xmlid).sudo().read()[0]
        if domain is not None:
            action['domain'] = domain
        return action

    def action_refresh(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SaaS Dashboard Refreshed'),
                'message': _('Live counts were refreshed from the current database.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_tenants(self):
        return self._open_action('elsx_saas.action_elsx_saas_tenant')

    def action_open_tenant_warnings(self):
        return self._open_action('elsx_saas.action_elsx_saas_tenant', [
            '|',
            ('health_status', 'in', ('warning', 'error')),
            ('backup_verified', '=', False),
        ])

    def action_open_module_requests(self):
        return self._open_action('elsx_saas.action_elsx_saas_module_request')

    def action_open_high_risk_requests(self):
        return self._open_action('elsx_saas.action_elsx_saas_module_request', [
            ('risk_level', 'in', ('high', 'critical')),
            ('state', 'not in', ('installed', 'cancelled', 'rejected')),
        ])

    def action_open_billing_cycles(self):
        return self._open_action('elsx_saas.action_elsx_saas_billing_cycle')

    def action_open_support_tickets(self):
        return self._open_action('elsx_saas.action_elsx_saas_support_ticket')

    def action_open_health_checks(self):
        return self._open_action('elsx_saas.action_elsx_saas_health_check')

    def action_open_usage(self):
        return self._open_action('elsx_saas.action_elsx_saas_tenant_usage')