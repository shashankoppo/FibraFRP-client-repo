# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class ElsxSignController(http.Controller):

    @http.route(['/sign/document/<int:request_id>'], type='http', auth='public', website=True)
    def sign_document_portal(self, request_id, token=None, **kwargs):
        """
        Public facing page where the user views the PDF and signs it.
        """
        sign_request = request.env['elsx.sign.request'].sudo().browse(request_id)
        
        # Security Check
        if not sign_request.exists() or sign_request.access_token != token:
            return request.render('http_routing.404')
        
        if sign_request.state == 'signed':
            return request.render('elsx_sign.document_already_signed_template', {
                'sign_request': sign_request
            })

        # Render the signing canvas interface
        return request.render('elsx_sign.document_signing_portal_template', {
            'sign_request': sign_request,
            'pdf_url': f"/web/content/{sign_request.document_attachment_id.id}?download=false",
            'token': token,
        })

    @http.route(['/sign/submit_signature'], type='json', auth='public', csrf=False)
    def submit_signature(self, request_id, token, signature_data, **kwargs):
        """
        JSON endpoint hit by the JS Canvas to save the signature blob.
        """
        sign_request = request.env['elsx.sign.request'].sudo().browse(int(request_id))
        
        if sign_request.exists() and sign_request.access_token == token and sign_request.state != 'signed':
            # Extract header from Data URL "data:image/png;base64,iVBORw0KGgo..."
            if ',' in signature_data:
                signature_data = signature_data.split(',')[1]
                
            ip_address = request.httprequest.environ.get('REMOTE_ADDR')
            sign_request.action_mark_signed(signature_data, ip_address)
            return {'success': True}
        
        return {'success': False, 'error': 'Invalid Token or Request'}
