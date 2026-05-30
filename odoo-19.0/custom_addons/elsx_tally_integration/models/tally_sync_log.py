# -*- coding: utf-8 -*-
from odoo import fields, models


class ElsxTallySyncLog(models.Model):
    _name = 'elsx.tally.sync.log'
    _description = 'Tally Sync Log'
    _order = 'create_date desc'

    name = fields.Char(default='Tally Sync', required=True)
    move_id = fields.Many2one('account.move', string='Invoice / Bill', ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', related='move_id.company_id', store=True, readonly=True)
    operation = fields.Selection([
        ('xml_export', 'XML Export'),
        ('push', 'Push to Tally'),
        ('test', 'Connection Test'),
    ], default='xml_export', required=True)
    state = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], default='success', required=True)
    gateway_url = fields.Char()
    request_payload = fields.Text()
    response_payload = fields.Text()
    error_message = fields.Text()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)

