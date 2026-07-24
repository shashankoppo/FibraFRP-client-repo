# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ELSXSaasBillingPlan(models.Model):
    _name = 'elsx.saas.billing.plan'
    _description = 'ELSx SaaS Billing Plan / Pricing Tier'
    _order = 'sequence, name'

    sequence = fields.Integer(default=10)
    name = fields.Char('Plan Name', required=True)
    code = fields.Char('Plan Code', required=True)
    description = fields.Html('Description')

    # Pricing
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    setup_fee = fields.Monetary('Setup Fee', currency_field='currency_id')
    monthly_price = fields.Monetary('Monthly Price', currency_field='currency_id', required=True)
    annual_price = fields.Monetary('Annual Price (discounted)', currency_field='currency_id')
    weekly_price = fields.Monetary('Weekly Price', currency_field='currency_id')
    yearly_price = fields.Monetary('Yearly Price', currency_field='currency_id')
    three_year_price = fields.Monetary('3-Year Price', currency_field='currency_id')
    five_year_price = fields.Monetary('5-Year Price', currency_field='currency_id')

    # Limits
    max_users = fields.Integer('Max Users', default=10)
    storage_quota_gb = fields.Integer('Storage Quota (GB)', default=5)
    api_calls_per_day = fields.Integer('API Calls Per Day', default=10000)

    # Features included
    enable_crm = fields.Boolean('Includes CRM', default=True)
    enable_accounting = fields.Boolean('Includes Accounting', default=True)
    enable_whatsapp = fields.Boolean('Includes WhatsApp', default=False)
    enable_attendance = fields.Boolean('Includes Attendance', default=False)
    enable_tally = fields.Boolean('Includes Tally Integration', default=False)
    enable_face_attendance = fields.Boolean('Includes Face Attendance', default=False)

    # Support
    support_tier = fields.Selection([
        ('community', 'Community Support'),
        ('standard', 'Standard Support (9-5)'),
        ('priority', 'Priority Support (24x5)'),
        ('enterprise', 'Enterprise Support (24x7)'),
    ], default='standard')

    # Billing cycle options
    allow_monthly = fields.Boolean('Allow Monthly Billing', default=True)
    allow_annual = fields.Boolean('Allow Annual Billing', default=True)
    allow_weekly = fields.Boolean('Allow Weekly Billing', default=False)
    allow_yearly = fields.Boolean('Allow Yearly Billing', default=True)
    allow_three_year = fields.Boolean('Allow 3-Year Billing', default=False)
    allow_five_year = fields.Boolean('Allow 5-Year Billing', default=False)

    is_active = fields.Boolean('Active', default=True)

    _plan_code_unique = models.Constraint('UNIQUE (code)', 'Plan code must be unique.')

    @api.constrains('monthly_price', 'annual_price')
    def _check_prices(self):
        for plan in self:
            if plan.annual_price and plan.annual_price >= (plan.monthly_price * 12):
                raise ValidationError(_('Annual price should be less than 12x monthly price for it to be a discount.'))


class ELSXSaasBillingCycle(models.Model):
    _name = 'elsx.saas.billing.cycle'
    _description = 'ELSx SaaS Billing Cycle / Invoice'
    _order = 'invoice_date desc, tenant_id'
    _inherit = ['mail.thread']

    # Identifiers
    name = fields.Char('Invoice Number', readonly=True, copy=False)
    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade', tracking=True)

    # Dates
    cycle_start_date = fields.Date('Cycle Start', required=True)
    cycle_end_date = fields.Date('Cycle End', required=True)
    invoice_date = fields.Date('Invoice Date', required=True)
    due_date = fields.Date('Due Date')

    # Plan
    plan_id = fields.Many2one('elsx.saas.billing.plan', 'Plan', required=True)
    billing_cycle = fields.Selection([
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('annual', 'Annual'),
        ('three_year', '3-Year'),
        ('five_year', '5-Year'),
        ('custom', 'Custom'),
    ], required=True)

    # Amounts
    currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id', store=True)

    base_amount = fields.Monetary('Base Amount', currency_field='currency_id')
    setup_fee = fields.Monetary('Setup Fee', currency_field='currency_id')
    discount_amount = fields.Monetary('Discount', currency_field='currency_id')
    tax_amount = fields.Monetary('Tax', currency_field='currency_id')

    total_amount = fields.Monetary(
        'Total Amount',
        currency_field='currency_id',
        compute='_compute_total_amount',
        store=True,
    )

    # Payment
    payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    paid_amount = fields.Monetary('Amount Paid', currency_field='currency_id')
    paid_date = fields.Date('Payment Date')

    # Line items
    line_ids = fields.One2many('elsx.saas.billing.line', 'cycle_id', string='Line Items')

    # Adjustments
    notes = fields.Text('Notes')

    _invoice_number_unique = models.Constraint('UNIQUE (name)', 'Invoice number must be unique.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('elsx.saas.billing.cycle') or 'INV/0000'

        return super().create(vals_list)

    @api.depends('base_amount', 'setup_fee', 'discount_amount', 'tax_amount')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = (
                (record.base_amount or 0) +
                (record.setup_fee or 0) +
                (record.tax_amount or 0) -
                (record.discount_amount or 0)
            )

    def action_send_invoice(self):
        """Send invoice to tenant admin."""
        self.payment_status = 'sent'
        self.message_post(
            subject=_('Invoice %s Sent') % self.name,
            body=_('Invoice has been sent to %s') % self.tenant_id.admin_email,
        )

    def action_mark_paid(self):
        """Mark invoice as paid."""
        self.write({
            'payment_status': 'paid',
            'paid_date': fields.Date.today(),
            'paid_amount': self.total_amount,
        })
        self.message_post(body=_('Invoice marked as paid.'))

    def action_mark_overdue(self):
        """Mark invoice as overdue."""
        self.payment_status = 'overdue'
        self.message_post(body=_('Invoice marked as overdue.'))

    @api.model
    def _cron_detect_overdue(self):
        """Cron job: mark billing cycles as overdue when past due date."""
        today = fields.Date.today()
        overdue_cycles = self.search([
            ('due_date', '<', today),
            ('payment_status', 'in', ('draft', 'sent', 'partial')),
        ])
        for cycle in overdue_cycles:
            cycle.payment_status = 'overdue'
            cycle.message_post(body=_('Automatically marked overdue by scheduled check on %s.') % today)


class ELSXSaasBillingLine(models.Model):
    _name = 'elsx.saas.billing.line'
    _description = 'Billing Cycle Line Item'
    _order = 'sequence, id'

    cycle_id = fields.Many2one('elsx.saas.billing.cycle', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(related='cycle_id.tenant_id', store=True, readonly=True)

    sequence = fields.Integer(default=10)
    description = fields.Char('Description', required=True)

    item_type = fields.Selection([
        ('plan', 'Plan Fee'),
        ('addon', 'Add-on / Extra'),
        ('adjustment', 'Adjustment'),
        ('credit', 'Credit'),
        ('tax', 'Tax'),
    ], default='plan', required=True)

    quantity = fields.Float('Quantity', default=1)
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    currency_id = fields.Many2one(related='cycle_id.currency_id', store=True, readonly=True)

    subtotal = fields.Monetary(
        'Subtotal',
        currency_field='currency_id',
        compute='_compute_subtotal',
        store=True,
    )

    details = fields.Text('Details')

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (line.quantity or 0) * (line.unit_price or 0)


class ELSXSaasSubscription(models.Model):
    _name = 'elsx.saas.subscription'
    _description = 'ELSx SaaS Active Subscription'
    _order = 'activation_date desc, tenant_id'

    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade')
    plan_id = fields.Many2one('elsx.saas.billing.plan', required=True)

    # Subscription dates
    activation_date = fields.Date('Activation Date', default=fields.Date.today)
    next_billing_date = fields.Date('Next Billing Date', required=True)
    cancellation_date = fields.Date('Cancellation Date')

    # Billing
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

    currency_id = fields.Many2one(related='tenant_id.currency_id', store=True, readonly=True)

    # Payment method
    payment_method = fields.Selection([
        ('credit_card', 'Credit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('invoice', 'Invoice'),
        ('custom', 'Custom'),
    ], required=True)

    # Overrides
    custom_monthly_price = fields.Monetary('Custom Monthly Price (optional)', currency_field='currency_id')

    # Status
    is_active = fields.Boolean('Active', default=True)
    is_trial = fields.Boolean('Trial Subscription', default=False)
    trial_end_date = fields.Date('Trial End Date')
    grace_period_days = fields.Integer('Grace Period (Days)', default=7, help='Days after billing date before suspension warning.')

    auto_renew = fields.Boolean('Auto-Renew', default=True)

    # Add-ons
    addon_ids = fields.Many2many('elsx.saas.addon', string='Active Add-ons')

    # History
    billing_cycle_ids = fields.One2many('elsx.saas.billing.cycle', string='Billing History', compute='_compute_billing_cycles')

    _tenant_subscription_unique = models.Constraint('UNIQUE (tenant_id)', 'A tenant can have only one active subscription record.')

    @api.depends('tenant_id')
    def _compute_billing_cycles(self):
        for sub in self:
            sub.billing_cycle_ids = self.env['elsx.saas.billing.cycle'].search([
                ('tenant_id', '=', sub.tenant_id.id),
            ])

    def action_cancel_subscription(self):
        """Cancel subscription."""
        self.write({
            'is_active': False,
            'cancellation_date': fields.Date.today(),
            'auto_renew': False,
        })

    def action_upgrade_plan(self):
        """Guide admins through a controlled plan change.

        The plan field is editable on the subscription itself. Keep this as a
        notice instead of opening a missing wizard or silently changing tenant
        capacity in production.
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Change'),
                'message': _('Edit the subscription plan after backup/staging approval, then update the tenant deployment plan. No tenant database is changed automatically.'),
                'type': 'info',
                'sticky': True,
            },
        }

    def action_add_addon(self):
        """Guide admins through a controlled add-on change."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Add-on Change'),
                'message': _('Add approved add-ons on the subscription after review. This console records billing/governance only; it does not install modules automatically.'),
                'type': 'info',
                'sticky': True,
            },
        }

    @api.model
    def _cron_auto_generate_invoices(self):
        """Cron job: generate next billing cycle for subscriptions due today or earlier."""
        today = fields.Date.today()
        due_subs = self.search([
            ('is_active', '=', True),
            ('next_billing_date', '<=', today),
        ])
        BillingCycle = self.env['elsx.saas.billing.cycle']
        for sub in due_subs:
            plan = sub.plan_id
            if not plan:
                continue
            cycle_map = {
                'weekly': 7,
                'monthly': 30,
                'quarterly': 90,
                'yearly': 365,
                'annual': 365,
                'three_year': 1095,
                'five_year': 1825,
                'custom': 30,
            }
            days = cycle_map.get(sub.billing_cycle, 30)
            cycle_end = today + timedelta(days=days)
            price = sub.custom_monthly_price or plan.monthly_price
            if sub.billing_cycle == 'weekly' and plan.weekly_price:
                price = plan.weekly_price
            elif sub.billing_cycle == 'annual' and plan.annual_price:
                price = plan.annual_price
            elif sub.billing_cycle == 'yearly' and (plan.yearly_price or plan.annual_price):
                price = plan.yearly_price or plan.annual_price
            elif sub.billing_cycle == 'three_year' and plan.three_year_price:
                price = plan.three_year_price
            elif sub.billing_cycle == 'five_year' and plan.five_year_price:
                price = plan.five_year_price
            BillingCycle.create({
                'tenant_id': sub.tenant_id.id,
                'plan_id': plan.id,
                'billing_cycle': sub.billing_cycle,
                'cycle_start_date': today,
                'cycle_end_date': cycle_end,
                'invoice_date': today,
                'due_date': today + timedelta(days=14),
                'base_amount': price,
                'payment_status': 'draft',
            })
            sub.next_billing_date = cycle_end


class ELSXSaasAddon(models.Model):
    _name = 'elsx.saas.addon'
    _description = 'ELSx SaaS Billing Add-on / Extra Feature'
    _order = 'sequence, name'

    sequence = fields.Integer(default=10)
    name = fields.Char('Add-on Name', required=True)
    description = fields.Html('Description')

    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    monthly_price = fields.Monetary('Monthly Price', currency_field='currency_id', required=True)

    is_active = fields.Boolean('Active', default=True)
    addon_limit_ids = fields.One2many('elsx.saas.addon.limit', 'addon_id', string='Limits')


class ELSXSaasAddonLimit(models.Model):
    _name = 'elsx.saas.addon.limit'
    _description = 'Add-on Quota Limit'

    addon_id = fields.Many2one('elsx.saas.addon', required=True, ondelete='cascade')
    name = fields.Char('Limit Type', required=True)
    value = fields.Float('Limit Value')
    unit = fields.Char('Unit')
