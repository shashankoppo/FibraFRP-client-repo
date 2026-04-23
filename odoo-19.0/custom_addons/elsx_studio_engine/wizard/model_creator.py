# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ElsxStudioModelCreator(models.TransientModel):
    _name = 'elsx.studio.model.creator'
    _description = 'Dynamic Model Generator (Studio Clone)'

    name = fields.Char(string="Model Name", required=True)
    model_id = fields.Char(string="Technical Name (e.g. x_elsx_cust)", required=True)

    def action_generate_model(self):
        """
        Equivalent to creating a new app in Odoo Studio.
        Injects directly into ir.model.
        """
        self.env['ir.model'].create({
            'name': self.name,
            'model': self.model_id,
            'state': 'manual',
        })
        return {'type': 'ir.actions.act_window_close'}
