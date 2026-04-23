# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    elsx_openai_api_key = fields.Char(
        string="ELSX OpenAI API Key",
        config_parameter="elsx_ai_ocr.openai_api_key",
        help="API Key for Vision extraction to bypass Odoo Enterprise servers."
    )
    
    elsx_active_llm_engine = fields.Selection([
        ('openai', 'OpenAI (GPT-4o)'),
        ('anthropic', 'Anthropic (Claude)'),
        ('local', 'Local Llama (Open Source)')
    ], string="Active Vision Engine", default='openai', config_parameter="elsx_ai_ocr.active_engine")
