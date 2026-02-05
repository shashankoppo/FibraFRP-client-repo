from odoo import models, fields

class ResPartnerTitle(models.Model):
    _name = 'res.partner.title'
    _description = 'Partner Title'

    name = fields.Char('Title', required=True, translate=True)
    shortcut = fields.Char('Abbreviation', translate=True)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    title = fields.Many2one('res.partner.title', 'Title')
    mobile = fields.Char('Mobile')

class HrContractType(models.Model):
    _name = 'hr.contract.type'
    _description = 'Contract Type'

    name = fields.Char('Contract Type', required=True)
