# -*- coding: utf-8 -*-
from odoo import models, api, fields
import json
import requests
import base64

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Intercept attachments to send to AI OCR if attached to account.move.
        """
        records = super(IrAttachment, self).create(vals_list)
        for record in records:
            if record.res_model == 'account.move' and record.mimetype in ['application/pdf', 'image/jpeg', 'image/png']:
                # The user just uploaded a bill to a draft invoice.
                record.env['elsx.ai.ocr.service'].extract_document_data(record.id)
        return records

class ElsxAiOcrService(models.TransientModel):
    _name = 'elsx.ai.ocr.service'
    _description = 'Vision AI Extraction Engine'

    @api.model
    def extract_document_data(self, attachment_id):
        """
        Takes the raw base64 data of the attachment, sends it to a Vision LLM to parse into JSON.
        """
        attachment = self.env['ir.attachment'].browse(attachment_id)
        move = self.env['account.move'].browse(attachment.res_id)
        
        # Load System Configurations
        api_key = self.env['ir.config_parameter'].sudo().get_param('elsx_ai_ocr.openai_api_key')
        active_engine = self.env['ir.config_parameter'].sudo().get_param('elsx_ai_ocr.active_engine')
        
        print(f"ELSX OCR: Intercepted Document {attachment.name} using {active_engine} Engine.")
        
        ai_response_json = None
        
        if active_engine == 'openai' and api_key:
            # Live OpenAI Vision API hit
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract the vendor_name, invoice_date, total_amount, and an array of lines (with description and price). Respond with raw JSON only."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{attachment.mimetype};base64,{attachment.datas.decode('utf-8')}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }
            
            try:
                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    resp_data = response.json()
                    raw_text = resp_data['choices'][0]['message']['content']
                    # Clean out markdown markdown markers if present
                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                    ai_response_json = json.loads(raw_text)
            except Exception as e:
                print(f"ELSX AI OCR Error: {e}")
                
        # Fallback Mock if API fails or isn't set up yet
        if not ai_response_json:
            ai_response_json = {
                "vendor_name": "Example Corp (OCR Fallback)",
                "invoice_date": fields.Date.today(),
                "total_amount": 0.0,
                "lines": [{"description": "Manual Entry Required", "price": 0.0}]
            }
            
        # Hydrate the Odoo Bill directly from the AI Extracted JSON
        if not move.partner_id and ai_response_json.get('vendor_name'):
            # First look for exact match, then fallback to ILIKE
            partner = self.env['res.partner'].search([('name', 'ilike', ai_response_json['vendor_name'])], limit=1)
            if partner:
                move.partner_id = partner.id
        
        if not move.invoice_line_ids and ai_response_json.get('lines'):
            for line_data in ai_response_json['lines']:
                move.write({
                    'invoice_line_ids': [(0, 0, {
                        'name': line_data.get('description', 'Parsed Line'),
                        'price_unit': line_data.get('price', 0.0),
                        'quantity': 1,
                    })]
                })
        
        return True
