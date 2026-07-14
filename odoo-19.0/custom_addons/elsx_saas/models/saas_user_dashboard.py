# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ELSXSaasUserDashboard(models.TransientModel):
    _name = 'elsx.saas.user.dashboard'
    _description = 'ELSx SaaS User Portal'

    name = fields.Char(default='My SaaS Portal')

    # Active tenant info
    tenant_id = fields.Many2one('elsx.saas.tenant', compute='_compute_metrics')
    tenant_name = fields.Char(compute='_compute_metrics')
    tenant_domain = fields.Char(compute='_compute_metrics')
    tenant_state = fields.Char(compute='_compute_metrics')

    # App allowance
    app_allowance = fields.Integer(compute='_compute_metrics')
    installed_app_count = fields.Integer(compute='_compute_metrics')

    # Billing
    open_invoice_count = fields.Integer(compute='_compute_metrics')
    overdue_invoice_count = fields.Integer(compute='_compute_metrics')
    next_billing_date = fields.Date(compute='_compute_metrics')
    monthly_recurring_revenue = fields.Monetary(compute='_compute_metrics', currency_field='company_currency_id')
    company_currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Support
    open_ticket_count = fields.Integer(compute='_compute_metrics')

    # Warning flags
    has_overdue_invoices = fields.Boolean(compute='_compute_metrics')
    is_suspended = fields.Boolean(compute='_compute_metrics')

    def _compute_metrics(self):
        Tenant = self.env['elsx.saas.tenant']
        Ticket = self.env['elsx.saas.support.ticket']
        BillingCycle = self.env['elsx.saas.billing.cycle']

        # User only sees their own tenants due to record rules
        my_tenant = Tenant.search([], limit=1)

        for dashboard in self:
            if my_tenant:
                dashboard.tenant_id = my_tenant.id
                dashboard.tenant_name = my_tenant.name
                dashboard.tenant_domain = my_tenant.custom_domain or my_tenant.base_url or my_tenant.db_name
                dashboard.tenant_state = my_tenant.state
                dashboard.app_allowance = my_tenant.app_allowance
                dashboard.installed_app_count = my_tenant.installed_app_count
                dashboard.next_billing_date = my_tenant.next_billing_date
                dashboard.monthly_recurring_revenue = my_tenant.monthly_recurring_revenue
                dashboard.is_suspended = my_tenant.state in ('suspended', 'archived')
            else:
                dashboard.tenant_id = False
                dashboard.tenant_name = 'No Active Tenant'
                dashboard.tenant_domain = ''
                dashboard.tenant_state = 'draft'
                dashboard.app_allowance = 0
                dashboard.installed_app_count = 0
                dashboard.next_billing_date = False
                dashboard.monthly_recurring_revenue = 0.0
                dashboard.is_suspended = False

            # Invoices
            invoices = BillingCycle.search([])
            dashboard.open_invoice_count = len(invoices.filtered(lambda i: i.payment_status in ('draft', 'sent', 'partial')))
            dashboard.overdue_invoice_count = len(invoices.filtered(lambda i: i.payment_status == 'overdue'))
            dashboard.has_overdue_invoices = dashboard.overdue_invoice_count > 0

            # Support tickets
            open_tickets = Ticket.search([('state', 'not in', ('resolved', 'closed'))])
            dashboard.open_ticket_count = len(open_tickets)

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
                'title': _('Portal Refreshed'),
                'message': _('Live metrics were refreshed.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_my_tenant(self):
        if self.tenant_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'elsx.saas.tenant',
                'res_id': self.tenant_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False

    def action_open_billing(self):
        return self._open_action('elsx_saas.action_my_saas_invoices')

    def action_open_overdue_billing(self):
        return self._open_action('elsx_saas.action_my_saas_invoices', [('payment_status', '=', 'overdue')])

    def action_open_tickets(self):
        return self._open_action('elsx_saas.action_my_saas_tickets')

    def action_request_app(self):
        return self._open_action('elsx_saas.action_saas_native_apps')
