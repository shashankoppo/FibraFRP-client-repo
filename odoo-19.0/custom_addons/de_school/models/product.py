
from odoo import api, fields, models, tools, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    """
    ** Services Only **
    - Prepaid: will invoice with first invoice
    ** Product & Services **
    - Rental: it would be for both product and services - invoicing will be on monthly basis till end date
    - On Demand: it will charge on the basis of quantity. in case of product it will consume on issuance, on both cases a resident request will generate for processing.
    """
    fee_invoice_policy  = fields.Selection([
        ('prepaid', 'Prepaid/Fixed Price'),
        ('recurr', 'Recurring'),
        ('delivery','Delivery'), 
    ], string="Invoicing Policy", default="prepaid", copy=False)
    refundable_fee = fields.Boolean(string='Refundable', default=False)

class ProductProduct(models.Model):
    _inherit = "product.product"