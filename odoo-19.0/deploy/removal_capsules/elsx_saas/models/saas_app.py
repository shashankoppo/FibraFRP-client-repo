# -*- coding: utf-8 -*-
from odoo import fields, models

class ELSXSaasApp(models.Model):
    _name = 'elsx.saas.app'
    _description = 'SaaS App Catalog'
    _order = 'sequence, name'

    name = fields.Char('App Name', required=True, translate=True)
    module_name = fields.Char('Technical Name', required=True, help="The technical name of the Odoo module (e.g., website_sale)")
    sequence = fields.Integer(default=10)
    image_1920 = fields.Image("App Icon", max_width=1920, max_height=1920)
    summary = fields.Char('Summary', translate=True)
    description = fields.Html('Description', translate=True)

    category = fields.Selection([
        ('sales', 'Sales'),
        ('finance', 'Finance'),
        ('hr', 'Human Resources'),
        ('marketing', 'Marketing'),
        ('website', 'Website'),
        ('inventory', 'Inventory & MRP'),
        ('productivity', 'Productivity'),
        ('other', 'Other')
    ], default='other', string='Category')

    monthly_price = fields.Monetary('Monthly Price', currency_field='currency_id')
    one_time_price = fields.Monetary('One-Time Setup Price', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    is_published = fields.Boolean('Published', default=True, help="If checked, this app will be visible in the user's App Store.")
    is_popular = fields.Boolean('Popular', default=False, help="Highlight this app in the App Store.")

    # Computed fields for the Kanban view styling
    color = fields.Integer('Color Index', default=0)

    def action_request_app(self):
        self.ensure_one()
        return {
            'name': 'Request Module',
            'type': 'ir.actions.act_window',
            'res_model': 'elsx.saas.module.request',
            'view_mode': 'form',
            'context': {
                'default_app_id': self.id,
                'default_name': self.name,
                'default_module_name': self.module_name,
                'default_monthly_cost': self.monthly_price,
                'default_one_time_cost': self.one_time_price,
            },
        }
