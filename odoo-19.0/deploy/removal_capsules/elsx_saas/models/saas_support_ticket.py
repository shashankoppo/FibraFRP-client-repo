# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, AccessDenied


class ELSXSaasSupportTicket(models.Model):
    _name = 'elsx.saas.support.ticket'
    _description = 'ELSx SaaS Support Ticket'
    _order = 'priority desc, create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Identifiers
    ticket_number = fields.Char('Ticket Number', readonly=True, copy=False)
    name = fields.Char(string='Subject', required=True, tracking=True)

    # Tenant & Contact
    tenant_id = fields.Many2one('elsx.saas.tenant', required=True, ondelete='cascade', tracking=True, default=lambda self: self.env['elsx.saas.tenant'].search([('user_id', '=', self.env.uid)], limit=1))
    submitted_by = fields.Many2one('res.partner', 'Submitted By', required=True, default=lambda self: self.env.user.partner_id)
    assigned_to = fields.Many2one('res.users', 'Assigned To', tracking=True)

    # Categories
    category = fields.Selection([
        ('billing', 'Billing & Payment'),
        ('technical', 'Technical Issue'),
        ('feature_request', 'Feature Request'),
        ('general_inquiry', 'General Inquiry'),
        ('module_request', 'Module Request'),
        ('integration', 'Integration'),
        ('performance', 'Performance'),
        ('security', 'Security'),
        ('other', 'Other'),
    ], required=True, tracking=True)

    sub_category = fields.Char('Sub-Category')

    # Content
    description = fields.Text('Description', required=True)
    attachments_count = fields.Integer(compute='_compute_attachments_count')

    # Status & Priority
    state = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('waiting_customer', 'Waiting for Customer'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('reopened', 'Reopened'),
    ], default='new', tracking=True)

    priority = fields.Selection([
        ('1', 'Critical'),
        ('2', 'High'),
        ('3', 'Normal'),
        ('4', 'Low'),
    ], default='3', tracking=True)

    severity = fields.Selection([
        ('critical', 'Critical - System Down'),
        ('high', 'High - Major Feature Affected'),
        ('medium', 'Medium - Minor Feature Affected'),
        ('low', 'Low - Cosmetic/Information'),
    ], default='medium')

    # Timing
    create_date = fields.Datetime(readonly=True, tracking=True)
    first_response_date = fields.Datetime(readonly=True)
    resolution_date = fields.Datetime(readonly=True)
    closed_date = fields.Datetime(readonly=True)

    hours_to_first_response = fields.Float(compute='_compute_response_time')
    hours_to_resolution = fields.Float(compute='_compute_resolution_time')

    # SLA
    sla_timer_hours = fields.Float('SLA Timer (hours)', compute='_compute_sla_timer')
    sla_status = fields.Selection([
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('breached', 'Breached'),
    ], compute='_compute_sla_status')

    # Resolution
    internal_notes = fields.Text('Internal Notes')
    resolution_notes = fields.Text('Resolution Notes')
    resolution_category = fields.Selection([
        ('resolved', 'Resolved'),
        ('workaround', 'Workaround Provided'),
        ('closed_user_request', 'Closed by User Request'),
        ('wont_fix', 'Won\'t Fix'),
        ('duplicate', 'Duplicate'),
    ])

    # Metrics
    message_count = fields.Integer(compute='_compute_message_count')
    is_customer_satisfied = fields.Selection([
        ('satisfied', 'Satisfied'),
        ('neutral', 'Neutral'),
        ('unsatisfied', 'Unsatisfied'),
    ])
    satisfaction_reason = fields.Char()

    # Related records
    related_module_request_id = fields.Many2one('elsx.saas.module.request', 'Related Module Request')

    _ticket_number_unique = models.Constraint('UNIQUE (ticket_number)', 'Ticket number must be unique.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('ticket_number'):
                vals['ticket_number'] = self.env['ir.sequence'].next_by_code('elsx.saas.support.ticket') or 'TICKET/0000'

        return super().create(vals_list)

    @api.depends('state')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.message_ids)

    @api.depends('message_ids', 'attachments_count')
    def _compute_attachments_count(self):
        for record in self:
            count = 0
            for message in record.message_ids:
                count += len(message.attachment_ids)
            record.attachments_count = count

    @api.depends('create_date', 'first_response_date')
    def _compute_response_time(self):
        for record in self:
            if record.create_date and record.first_response_date:
                delta = record.first_response_date - record.create_date
                record.hours_to_first_response = delta.total_seconds() / 3600
            else:
                record.hours_to_first_response = 0

    @api.depends('create_date', 'resolution_date')
    def _compute_resolution_time(self):
        for record in self:
            if record.create_date and record.resolution_date:
                delta = record.resolution_date - record.create_date
                record.hours_to_resolution = delta.total_seconds() / 3600
            else:
                record.hours_to_resolution = 0

    @api.depends('priority', 'create_date')
    def _compute_sla_timer(self):
        """Calculate SLA timer based on priority."""
        for record in self:
            if record.create_date:
                now = fields.Datetime.now()
                elapsed = (now - record.create_date).total_seconds() / 3600

                # SLA targets in hours based on priority
                sla_targets = {'1': 1, '2': 4, '3': 24, '4': 72}
                sla_target = sla_targets.get(record.priority, 24)

                record.sla_timer_hours = sla_target - elapsed
            else:
                record.sla_timer_hours = 0

    @api.depends('sla_timer_hours', 'state')
    def _compute_sla_status(self):
        for record in self:
            if record.state in ('resolved', 'closed'):
                record.sla_status = 'on_track'
            elif record.sla_timer_hours > 0:
                record.sla_status = 'on_track'
            elif record.sla_timer_hours > -4:  # 4 hours grace
                record.sla_status = 'at_risk'
            else:
                record.sla_status = 'breached'

    def action_assign_to_me(self):
        """Assign ticket to current user."""
        self.assigned_to = self.env.user
        self.state = 'assigned'

    def action_start_work(self):
        """Mark ticket as in progress."""
        self.write({
            'state': 'in_progress',
            'assigned_to': self.env.user,
        })

    def action_mark_waiting_customer(self):
        """Mark as waiting for customer response."""
        self.state = 'waiting_customer'

    def action_resolve(self):
        """Mark ticket as resolved."""
        if not self.resolution_notes:
            raise UserError(_('Please provide resolution notes before marking as resolved.'))

        self.write({
            'state': 'resolved',
            'resolution_date': fields.Datetime.now(),
        })

    def action_close(self):
        """Close the ticket."""
        self.write({
            'state': 'closed',
            'closed_date': fields.Datetime.now(),
        })

    def action_reopen(self):
        """Reopen a closed/resolved ticket."""
        self.write({
            'state': 'reopened',
            'resolution_date': None,
            'closed_date': None,
        })

    def action_send_customer_message(self):
        """Send a message to the customer."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Message'),
            'view_mode': 'form',
            'res_model': 'elsx.saas.ticket.message',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_is_internal': False,
            },
        }

    def action_add_internal_note(self):
        """Add an internal note."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add Internal Note'),
            'view_mode': 'form',
            'res_model': 'elsx.saas.ticket.message',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_is_internal': True,
            },
        }


class ELSXSaasTicketMessage(models.Model):
    _name = 'elsx.saas.ticket.message'
    _description = 'Support Ticket Message'
    _order = 'create_date desc'

    ticket_id = fields.Many2one('elsx.saas.support.ticket', required=True, ondelete='cascade')
    author_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)

    is_internal = fields.Boolean('Internal Note', default=False)
    message = fields.Html('Message', required=True)

    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    create_date = fields.Datetime(readonly=True, default=fields.Datetime.now)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        # Update ticket state when message is added
        for record in records:
            ticket = record.ticket_id

            if not record.is_internal and ticket.state == 'new':
                ticket.first_response_date = fields.Datetime.now()
                ticket.state = 'assigned'

        return records
