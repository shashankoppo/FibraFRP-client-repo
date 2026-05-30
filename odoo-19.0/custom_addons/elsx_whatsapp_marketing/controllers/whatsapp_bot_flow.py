# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class WhatsAppBotFlowController(http.Controller):
    """Authenticated JSON endpoints for the visual flow builder."""

    @http.route('/whatsapp_bot_flow/load', type='jsonrpc', auth='user')
    def load_flow_graph(self, flow_id, **kwargs):
        flow = request.env['whatsapp.bot.flow'].browse(int(flow_id)).exists()
        if not flow:
            return {'ok': False, 'error': 'Flow not found.'}
        return {'ok': True, 'graph': flow.get_visual_graph()}

    @http.route('/whatsapp_bot_flow/save', type='jsonrpc', auth='user')
    def save_flow_graph(self, flow_id, graph=None, **kwargs):
        flow = request.env['whatsapp.bot.flow'].browse(int(flow_id)).exists()
        if not flow:
            return {'ok': False, 'error': 'Flow not found.'}
        saved_graph = flow.save_visual_graph(graph or {})
        return {'ok': True, 'graph': saved_graph}
