# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Sidecar Real-Time Settings
    whatsapp_sidecar_url = fields.Char(
        string='Real-time Sidecar URL',
        config_parameter='whatsapp.sidecar.url',
        help="URL of the Node.js zero-latency WebSocket server (e.g. http://node_sidecar:3000)"
    )
    whatsapp_sidecar_secret = fields.Char(
        string='Sidecar Secret Key',
        config_parameter='whatsapp.sidecar.secret',
        help="Secret key used to authenticate requests between Odoo and the Node sidecar"
    )

    # General Preferences
    whatsapp_default_account_id = fields.Many2one(
        'whatsapp.account',
        string='Default WhatsApp Account',
        config_parameter='whatsapp.default.account.id',
        help="The default account used for outbound messages if none is specified"
    )
    
    # Automation & Bots
    whatsapp_enable_bot = fields.Boolean(
        string='Enable Bot Engine',
        config_parameter='whatsapp.enable.bot',
        default=True,
        help="If enabled, incoming messages will be processed by the Bot Engine before being assigned to agents."
    )

    # Compliance & Retention
    whatsapp_retention_days = fields.Integer(
        string='Message Retention (Days)',
        config_parameter='whatsapp.retention.days',
        default=365,
        help="Number of days to keep message history before automatic archival/deletion. 0 means keep forever."
    )
