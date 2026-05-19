# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import logging
import re

_logger = logging.getLogger(__name__)

class WhatsAppTemplate(models.Model):
    _name = 'whatsapp.template'
    _description = 'WhatsApp Message Template'
    _rec_name = 'name'

    is_carousel = fields.Boolean('Is Carousel', default=False)
    card_ids = fields.One2many('whatsapp.template.card', 'template_id', string='Carousel Cards')

    name = fields.Char('Template Name', required=True)
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=False)
    
    # Template details
    template_id = fields.Char('Template ID', help='WhatsApp approved template ID')
    meta_template_name = fields.Char('Meta Template Name', copy=False,
                                     help='Exact approved template name on Meta')
    language = fields.Selection([
        ('en', 'English'),
        ('en_US', 'English (US)'),
        ('en_GB', 'English (UK)'),
        ('es', 'Spanish'),
        ('es_AR', 'Spanish (Argentina)'),
        ('es_MX', 'Spanish (Mexico)'),
        ('fr', 'French'),
        ('de', 'German'),
        ('pt', 'Portuguese'),
        ('pt_BR', 'Portuguese (Brazil)'),
        ('hi', 'Hindi'),
        ('hi_IN', 'Hindi (India)'),
        ('ar', 'Arabic'),
        ('bn', 'Bengali'),
        ('gu', 'Gujarati'),
        ('kn', 'Kannada'),
        ('ml', 'Malayalam'),
        ('mr', 'Marathi'),
        ('pa', 'Punjabi'),
        ('ta', 'Tamil'),
        ('te', 'Telugu'),
        ('ur', 'Urdu'),
        ('id', 'Indonesian'),
        ('ms', 'Malay'),
        ('it', 'Italian'),
        ('nl', 'Dutch'),
        ('ru', 'Russian'),
        ('tr', 'Turkish'),
        ('ja', 'Japanese'),
        ('ko', 'Korean'),
        ('zh_CN', 'Chinese (Simplified)'),
        ('zh_TW', 'Chinese (Traditional)'),
        ('th', 'Thai'),
        ('vi', 'Vietnamese'),
        ('pl', 'Polish'),
        ('ro', 'Romanian'),
        ('uk', 'Ukrainian'),
        ('sv', 'Swedish'),
        ('da', 'Danish'),
        ('fi', 'Finnish'),
        ('nb', 'Norwegian'),
        ('he', 'Hebrew'),
        ('sw', 'Swahili'),
        ('af', 'Afrikaans'),
        ('fil', 'Filipino'),
    ], string='Language', default='en', required=True)
    language_code = fields.Char('Exact Language Code', default='en', copy=False,
                                help='Exact approved Meta locale code, e.g. en_US, es_MX')
    
    category = fields.Selection([
        ('marketing', 'Marketing'),
        ('utility', 'Utility'),
        ('authentication', 'Authentication'),
    ], string='Category', default='marketing', required=True)
    template_category = fields.Char('Template Category')
    
    # Content
    header_type = fields.Selection([
        ('none', 'None'),
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
    ], string='Header Type', default='none')
    
    header_text = fields.Char('Header Text')
    header_media_url = fields.Char('Header Media URL')
    header_media_file = fields.Binary('Header Media File', help='Upload image/video/document for template header')
    header_media_filename = fields.Char('Header Media Filename')
    
    body = fields.Text('Body', required=True, help='Use {{1}}, {{2}} for variables')
    footer = fields.Char('Footer')
    
    # Buttons
    
    has_buttons = fields.Boolean('Has Buttons', default=False)
    button_type = fields.Selection([
        ('quick_reply', 'Quick Reply'),
        ('call_to_action', 'Call to Action'),
        ('copy_code', 'Copy Code (OTP)'),
    ], string='Button Type')
    
    button_text_1 = fields.Char('Button 1 Text (Quick Reply)')
    button_text_2 = fields.Char('Button 2 Text (Quick Reply)')
    button_text_3 = fields.Char('Button 3 Text (Quick Reply)')
    
    # CTA Buttons
    cta_url_text = fields.Char('URL Button Text')
    cta_url_link = fields.Char('URL Link (e.g. https://...)')
    cta_phone_text = fields.Char('Phone Button Text')
    cta_phone_number = fields.Char('Phone Number (with country code)')
    copy_code_example = fields.Char('OTP Example Code', default='123456', help='Example OTP code for Meta approval')
    code_expiration_minutes = fields.Integer('OTP Expiration (minutes)', default=10)

    # Rejection / Meta feedback
    rejection_reason = fields.Text('Rejection Reason', readonly=True, help='Reason provided by Meta if template was rejected')
    quality_score = fields.Selection([
        ('green', 'High'),
        ('yellow', 'Medium'),
        ('red', 'Low'),
        ('unknown', 'Unknown'),
    ], string='Quality Score', default='unknown')

    # Variables/Attributes Mapping
    variable_ids = fields.One2many('whatsapp.template.variable', 'template_id', string='Attributes Mapping')

    @api.onchange('body', 'header_text', 'card_ids', 'card_ids.body')
    def onchange_extract_variables(self):
        self.action_refresh_variables()

    def action_refresh_variables(self):
        """Automatically detect {{1}}, {{2}} and create attribute mapping rows"""
        for rec in self:
            found_vars = set()
            if rec.body:
                found_vars.update(re.findall(r'\{\{\d+\}\}', rec.body))
            if rec.header_type == 'text' and rec.header_text:
                found_vars.update(re.findall(r'\{\{\d+\}\}', rec.header_text))
            
            if rec.is_carousel:
                for card in rec.card_ids:
                    if card.body:
                        found_vars.update(re.findall(r'\{\{\d+\}\}', card.body))
            
            existing = {v.name: v for v in rec.variable_ids}
            new_vars = []
            
            # Sort them so {{1}} comes before {{2}}
            sorted_vars = sorted(list(found_vars), key=lambda x: int(re.findall(r'\d+', x)[0]))
            
            for index, v_name in enumerate(sorted_vars):
                if v_name not in existing:
                    new_vars.append((0, 0, {
                        'name': v_name,
                        'sequence': index + 1,
                        'sample_value': f'Sample {index + 1}',
                        'field_type': 'text',
                    }))
                else:
                    # Update sequence of existing
                    new_vars.append((4, existing[v_name].id, 0))
                    
            # Remove deleted variables
            for v_name, v_rec in existing.items():
                if v_name not in found_vars:
                    new_vars.append((2, v_rec.id, 0))
                    
            if new_vars:
                rec.variable_ids = new_vars

    def _extract_variable_names(self):
        self.ensure_one()
        found = set()
        texts = [self.body or '']
        if self.header_type == 'text':
            texts.append(self.header_text or '')
        if self.is_carousel:
            texts.extend(self.card_ids.mapped('body'))
        for text in texts:
            found.update(re.findall(r'\{\{(\d+)\}\}', text or ''))
        return [f'{{{{{num}}}}}' for num in sorted({int(num) for num in found})]

    def _validate_variable_structure(self):
        """Prevent permanent Meta failures caused by malformed or unmapped variables."""
        for rec in self:
            variable_names = rec._extract_variable_names()
            if not variable_names:
                continue
            nums = [int(re.findall(r'\d+', name)[0]) for name in variable_names]
            expected = list(range(1, len(nums) + 1))
            if nums != expected:
                raise UserError(
                    "Template variables must be sequential without gaps. "
                    f"Found {', '.join(variable_names)}; expected "
                    f"{', '.join(f'{{{{{n}}}}}' for n in expected)}."
                )
            mapped = {var.name: var for var in rec.variable_ids}
            missing_rows = [name for name in variable_names if name not in mapped]
            if missing_rows:
                rec.action_refresh_variables()
                mapped = {var.name: var for var in rec.variable_ids}
            missing_samples = [name for name in variable_names if not mapped.get(name) or not mapped[name].sample_value]
            if missing_samples:
                raise UserError(
                    "Meta requires sample values for every template variable. "
                    f"Missing samples for: {', '.join(missing_samples)}."
                )

    
    # Status
    status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', required=True)
    
    active = fields.Boolean('Active', default=True)
    
    # Usage statistics
    usage_count = fields.Integer('Times Used', default=0)
    
    preview_html = fields.Html('Preview', compute='_compute_preview_html')

    @staticmethod
    def _normalize_language_selection(language_code):
        allowed = {
            'en', 'en_US', 'en_GB', 'es', 'es_AR', 'es_MX', 'fr', 'de', 'pt', 'pt_BR',
            'hi', 'hi_IN', 'ar', 'bn', 'gu', 'kn', 'ml', 'mr', 'pa', 'ta', 'te', 'ur',
            'id', 'ms', 'it', 'nl', 'ru', 'tr', 'ja', 'ko', 'zh_CN', 'zh_TW',
            'th', 'vi', 'pl', 'ro', 'uk', 'sv', 'da', 'fi', 'nb', 'he', 'sw', 'af', 'fil',
        }
        if language_code in allowed:
            return language_code
        if language_code and '_' in language_code:
            base_code = language_code.split('_', 1)[0]
            if base_code in allowed:
                return base_code
        return 'en'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            meta_name = vals.get('meta_template_name') or vals.get('name')
            language_code = vals.get('language_code') or vals.get('language') or 'en'
            if meta_name:
                vals.setdefault('meta_template_name', meta_name)
            vals['language_code'] = language_code
            vals['language'] = self._normalize_language_selection(language_code)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('language_code') and not vals.get('language'):
            vals['language'] = self._normalize_language_selection(vals['language_code'])
        if 'language' in vals and not vals.get('language_code'):
            vals['language_code'] = vals['language']
        return super().write(vals)

    def _get_send_language_code(self):
        """Returns the locale code to use in API calls.
        Meta Cloud API allows both generic (en) and specific (en_US) locales.
        We should trust the language_code set on the template.
        """
        self.ensure_one()
        return self.language_code or self.language or 'en_US'

    def _get_send_template_name(self):
        self.ensure_one()
        name = self.meta_template_name or self.name
        return name.lower().replace(' ', '_')

    def _media_parameter(self, media_type, media_value):
        if not media_value:
            raise UserError(f"{media_type.title()} header templates require a media handle or public URL before sending.")
        media_value = str(media_value).strip()
        if media_value.startswith(('http://', 'https://')):
            return {"type": media_type, media_type: {"link": media_value}}
        # Meta API sometimes requires 'id' to be an integer (e.g. v19.0 JSON schema)
        if media_value.isdigit():
            return {"type": media_type, media_type: {"id": int(media_value)}}
        # If it's a non-digit handle string (e.g. resumable upload handle), return it as 'handle'
        return {"type": media_type, media_type: {"handle": media_value}}

    def _format_variable_value(self, value):
        if value is False or value is None:
            return False
        if isinstance(value, str) and not value:
            return False
        if hasattr(value, 'mapped') and hasattr(value, 'ids'):
            names = [name for name in value.mapped('display_name') if name]
            return ', '.join(names) if names else False
        if isinstance(value, (list, tuple)):
            values = []
            for item in value:
                formatted = self._format_variable_value(item)
                if formatted:
                    values.append(formatted)
            return ', '.join(values) if values else False
        if hasattr(value, 'display_name'):
            return value.display_name
        if hasattr(value, 'name'):
            return value.name
        return str(value)

    def _resolve_variable_value(self, variable, partner=False):
        if not variable:
            return ' '
        if partner and variable.odoo_field:
            field_path = (variable.odoo_field or '').strip()
            candidates = [field_path]
            if field_path.startswith('partner_id.'):
                candidates.append(field_path.split('.', 1)[1])
            elif field_path.startswith('partner.'):
                candidates.append(field_path.split('.', 1)[1])
            elif field_path in ('partner_id', 'partner'):
                candidates.append('display_name')

            for candidate in [path for path in candidates if path]:
                try:
                    value = partner.mapped(candidate)
                    formatted = self._format_variable_value(value)
                    if formatted:
                        return formatted
                except Exception as e:
                    _logger.debug("Template variable %s mapping path %s failed: %s", variable.name, candidate, e)
        return variable.fallback_value or variable.sample_value or ' '

    def _variable_names_for_text(self, text):
        nums = re.findall(r'\{\{(\d+)\}\}', text or '')
        return [f'{{{{{num}}}}}' for num in sorted({int(num) for num in nums})]

    def _variables_for_names(self, names):
        variables_by_name = {var.name: var for var in self.variable_ids}
        return [variables_by_name[name] for name in names if name in variables_by_name]

    def _variable_parameters(self, variables, partner=False):
        return [
            {"type": "text", "text": str(self._resolve_variable_value(variable, partner))}
            for variable in variables
        ]

    def _prepare_send_payload(self, components=None, partner=None):
        self.ensure_one()
        _logger.info(f"Preparing send payload for template {self.name} (ID: {self.id})")
        self._validate_variable_structure()

        if components is None:
            components = []

            if self.is_carousel:
                cards = []
                for idx, card in enumerate(self.card_ids):
                    card_components = []
                    if card.header_type in ['image', 'video']:
                        card_components.append({
                            "type": "header",
                            "parameters": [self._media_parameter(card.header_type, card.header_media_url)]
                        })

                    card_variables = self._variables_for_names(self._variable_names_for_text(card.body))
                    card_body_params = self._variable_parameters(card_variables, partner)
                    if card_body_params:
                        card_components.append({"type": "body", "parameters": card_body_params})

                    cards.append({"index": idx, "components": card_components})

                if cards:
                    components.append({"type": "carousel", "cards": cards})

            else:
                if self.header_type in ['image', 'video', 'document']:
                    header_param = self._media_parameter(self.header_type, self.header_media_url)
                    components.append({"type": "header", "parameters": [header_param]})

                elif self.header_type == 'text' and '{{' in (self.header_text or ''):
                    header_variables = self._variables_for_names(self._variable_names_for_text(self.header_text))
                    header_params = self._variable_parameters(header_variables, partner)
                    if header_params:
                        components.append({"type": "header", "parameters": header_params})

                body_variables = self._variables_for_names(self._variable_names_for_text(self.body))
                body_params = self._variable_parameters(body_variables, partner)
                if body_params:
                    components.append({"type": "body", "parameters": body_params})

                if self.has_buttons:
                    if self.button_type == 'call_to_action' and self.cta_url_link and '{{' in self.cta_url_link:
                        button_variables = self._variables_for_names(self._variable_names_for_text(self.cta_url_link))
                        if button_variables:
                            val = self._resolve_variable_value(button_variables[0], partner)
                            components.append({
                                "type": "button",
                                "sub_type": "URL",
                                "index": 0,
                                "parameters": [{"type": "text", "text": str(val)}]
                            })

                    elif self.button_type == 'copy_code' and self.copy_code_example:
                        components.append({
                            "type": "button",
                            "sub_type": "COPY_CODE",
                            "index": 0,
                            "parameters": [{"type": "text", "text": self.copy_code_example}]
                        })
        else:
            components = list(components)

        payload = {
            'name': self._get_send_template_name(),
            'language': {'code': self._get_send_language_code()},
        }
        if components:
            payload['components'] = components

        return payload

    @api.depends('body', 'header_type', 'header_text', 'footer', 'has_buttons', 'button_type', 'button_text_1', 'button_text_2', 'button_text_3', 'cta_url_text', 'cta_phone_text', 'copy_code_example', 'variable_ids.sample_value', 'header_media_file', 'is_carousel', 'card_ids.body', 'card_ids.button_text_1')
    def _compute_preview_html(self):
        for rec in self:
            if rec.is_carousel:
                cards_html = ""
                for card in rec.card_ids:
                    card_buttons = ""
                    if card.button_text_1:
                        card_buttons += f'<div style="border-top: 1px solid #e9edef; padding: 6px; text-align: center; color: #008069; font-weight: 600; font-size: 13px;">{card.button_text_1}</div>'
                    if card.button_text_2:
                        card_buttons += f'<div style="border-top: 1px solid #e9edef; padding: 6px; text-align: center; color: #008069; font-weight: 600; font-size: 13px;">{card.button_text_2}</div>'

                    cards_html += f"""
                    <div style="flex: 0 0 200px; background: #fff; border-radius: 8px; margin-right: 8px; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); overflow: hidden;">
                        <div style="background: #e9edef; height: 100px; display: flex; align-items: center; justify-content: center; color: #8696a0;">
                            <i class="fa fa-image fa-2x"></i>
                        </div>
                        <div style="padding: 8px; font-size: 13px; color: #111b21;">{card.body}</div>
                        {card_buttons}
                    </div>"""
                
                rec.preview_html = f"""
                <div style="background: #e5ddd5; padding: 12px; border-radius: 12px; font-family: sans-serif;">
                    <div style="display: flex; overflow-x: auto; padding-bottom: 8px;">
                        {cards_html}
                    </div>
                </div>"""
                continue

            # Standard Template Preview Logic...
            # 1. Resolve body with sample variables
            preview_body = rec.body or 'Enter body text...'
            preview_header_text = rec.header_text or ''
            
            # Map variables to sample values
            var_map = {}
            for var in rec.variable_ids:
                var_map[var.name] = var.sample_value or var.name
                
            # Replace {{x}} with highlighted sample value
            def replace_var(match):
                var_name = match.group(0)
                sample = var_map.get(var_name, var_name)
                return f"<span style='background-color: rgba(37, 211, 102, 0.15); color: #00694b; font-weight: 600; padding: 0 4px; border-radius: 4px;'>{sample}</span>"
            
            preview_body = re.sub(r'\{\{\d+\}\}', replace_var, preview_body)
            preview_header_text = re.sub(r'\{\{\d+\}\}', replace_var, preview_header_text)

            # 2. Build Header
            header_html = ""
            if rec.header_type == 'text' and preview_header_text:
                header_html = f"<div style='font-weight: 700; font-size: 15px; margin-bottom: 6px; color: #111b21;'>{preview_header_text}</div>"
            elif rec.header_type == 'image':
                img_data = rec.header_media_file
                if img_data:
                    import base64
                    try:
                        if isinstance(img_data, bytes):
                            try:
                                decoded = img_data.decode('utf-8')
                                base64.b64decode(decoded, validate=True)
                                img_src = f"data:image/png;base64,{decoded}"
                            except Exception:
                                img_src = f"data:image/png;base64,{base64.b64encode(img_data).decode('utf-8')}"
                        else:
                            img_src = f"data:image/png;base64,{str(img_data)}"
                    except Exception:
                        img_src = "https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png"
                else:
                    img_src = "https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png"
                header_html = f"<div style='background: #e9edef; height: 140px; border-radius: 8px; margin-bottom: 8px; overflow: hidden; position: relative;'><img src='{img_src}' style='width: 100%; height: 100%; object-fit: cover;' alt='Image preview'/></div>"
            elif rec.header_type == 'video':
                header_html = f"<div style='background: #111b21; height: 140px; border-radius: 8px; margin-bottom: 8px; display: flex; align-items: center; justify-content: center;'><i class='fa fa-play-circle fa-3x' style='color: rgba(255,255,255,0.8);'></i></div>"
            elif rec.header_type == 'document':
                header_html = f"<div style='background: rgba(0,0,0,0.05); padding: 12px; border-radius: 8px; margin-bottom: 8px; display: flex; align-items: center; gap: 10px;'><i class='fa fa-file-pdf-o fa-2x' style='color: #EA4335;'></i><div style='flex: 1; font-weight: 600; font-size: 13px;'>Document PDF</div></div>"

            # 3. Build Body & Footer
            body_html = f"<div style='color: #111b21; font-size: 14px; white-space: pre-wrap; margin-bottom: 6px; line-height: 1.45;'>{preview_body}</div>"
            
            footer_html = ""
            if rec.footer:
                footer_html = f"<div style='color: #8696a0; font-size: 12px; margin-top: 4px; display: flex; align-items: center; justify-content: space-between;'><span>{rec.footer}</span><span style='font-size: 10px;'>12:00 PM</span></div>"
            else:
                footer_html = f"<div style='color: #8696a0; font-size: 10px; margin-top: 4px; text-align: right;'>12:00 PM</div>"

            # 4. Build Buttons
            buttons_html = ""
            if rec.has_buttons:
                button_styles = "border-top: 1px solid #e9edef; padding: 10px 0; text-align: center; color: #00a884; font-weight: bold; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;"
                if rec.button_type == 'quick_reply':
                    for btn in [rec.button_text_1, rec.button_text_2, rec.button_text_3]:
                        if btn:
                            buttons_html += f"<div style='{button_styles}'><i class='fa fa-reply'></i> {btn}</div>"
                elif rec.button_type == 'call_to_action':
                    if rec.cta_url_text:
                        buttons_html += f"<div style='{button_styles}'><i class='fa fa-external-link'></i> {rec.cta_url_text}</div>"
                    if rec.cta_phone_text:
                        buttons_html += f"<div style='{button_styles}'><i class='fa fa-phone'></i> {rec.cta_phone_text}</div>"
                elif rec.button_type == 'copy_code':
                    buttons_html += f"<div style='{button_styles}'><i class='fa fa-copy'></i> Copy code</div>"

            # 5. Assemble Premium Smartphone UI (iPhone 15 Pro Style)
            device_shell = f"""
            <div style='
                width: 340px; 
                margin: 0 auto; 
                background: #000; 
                border-radius: 50px; 
                padding: 12px; 
                box-shadow: 0 30px 60px rgba(0,0,0,0.3); 
                position: sticky; 
                top: 20px;
                border: 4px solid #333;
                height: 700px;
                display: flex;
                flex-direction: column;'>
                
                <!-- Inner Screen -->
                <div style='
                    background-color: #efeae2; 
                    background-image: url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png"); 
                    flex-grow: 1;
                    border-radius: 38px; 
                    overflow: hidden; 
                    display: flex; 
                    flex-direction: column;
                    position: relative;'>
                    
                    <!-- Dynamic Island (Notch) -->
                    <div style='
                        position: absolute;
                        top: 10px;
                        left: 50%;
                        transform: translateX(-50%);
                        width: 100px;
                        height: 25px;
                        background: #000;
                        border-radius: 20px;
                        z-index: 100;
                        display: flex;
                        align-items: center;
                        justify-content: center;'>
                        <div style='width: 6px; height: 6px; border-radius: 50%; background: #1a1a1a; margin-right: 40px;'></div>
                    </div>

                    <!-- App Bar -->
                    <div style='background: #f0f2f5; color: #111b21; padding: 40px 16px 12px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #d1d7db;'>
                        <i class='fa fa-chevron-left' style='color: #008069;'></i>
                        <div style='width: 40px; height: 40px; background: #dfe5e7; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #54656f;'>
                            <i class='fa fa-user fa-lg'></i>
                        </div>
                        <div style='flex: 1;'>
                            <div style='font-weight: 700; font-size: 16px;'>{rec.account_id.name or 'Business Account'}</div>
                            <div style='font-size: 11px; color: #667781;'>Business Account</div>
                        </div>
                        <i class='fa fa-video-camera' style='color: #008069;'></i>
                        <i class='fa fa-phone' style='color: #008069;'></i>
                    </div>
                    
                    <!-- Chat Area -->
                    <div style='padding: 16px; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; flex-grow: 1;'>
                        <!-- Message Bubble Container -->
                        <div style='display: flex; flex-direction: column; gap: 2px;'>
                            <div style='
                                background: white; 
                                border-radius: 0 12px 12px 12px; 
                                padding: 8px; 
                                box-shadow: 0 1px 2px rgba(11,20,26,.15); 
                                align-self: flex-start; 
                                max-width: 85%; 
                                position: relative;'>
                                
                                <!-- Tail -->
                                <div style='position: absolute; top: 0; left: -10px; width: 10px; height: 13px;'>
                                    <svg viewBox="0 0 8 13" width="10" height="13" style='fill: white;'><path d="M5.188 1H0v11.156L5.188 1z"/></svg>
                                </div>
                                
                                {header_html}
                                {body_html}
                                {footer_html}
                            </div>
                            
                            <!-- Buttons (Attached to Bubble) -->
                            <t t-if="has_buttons">
                                <div style='
                                    background: rgba(255,255,255,0.7); 
                                    backdrop-filter: blur(4px);
                                    border-radius: 12px; 
                                    box-shadow: 0 1px 2px rgba(11,20,26,.1); 
                                    align-self: flex-start; 
                                    width: 85%; 
                                    margin-top: 4px;
                                    display: flex; 
                                    flex-direction: column;
                                    overflow: hidden;'>
                                    {buttons_html}
                                </div>
                            </t>
                        </div>
                    </div>

                    <!-- Input Bar (Fake) -->
                    <div style='background: #f0f2f5; padding: 10px 16px; display: flex; align-items: center; gap: 12px;'>
                        <i class='fa fa-plus' style='color: #008069;'></i>
                        <div style='flex: 1; background: white; border-radius: 20px; padding: 8px 16px; font-size: 14px; color: #8696a0;'>Message</div>
                        <i class='fa fa-camera' style='color: #008069;'></i>
                        <i class='fa fa-microphone' style='color: #008069;'></i>
                    </div>
                </div>
                
                <!-- Home Indicator -->
                <div style='width: 120px; height: 5px; background: rgba(255,255,255,0.3); border-radius: 5px; margin: 15px auto 5px;'></div>
            </div>
            """
            
            rec.preview_html = device_shell

    def action_preview(self):
        """Preview the template"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Template Preview',
            'res_model': 'whatsapp.template',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_duplicate(self):
        """Duplicate this template as a new draft"""
        self.ensure_one()
        new_template = self.copy({
            'name': f"{self.name}_copy",
            'meta_template_name': False,
            'template_id': False,
            'status': 'draft',
            'usage_count': 0,
            'rejection_reason': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'whatsapp.template',
            'res_id': new_template.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _upload_header_media(self):
        """Upload header_media_file to Meta and return the media handle for template submission"""
        self.ensure_one()
        if not self.header_media_file or not self.account_id:
            return None

        import base64
        import io
        import mimetypes

        url = f"https://graph.facebook.com/{self.account_id.api_version}/{self.account_id.phone_number_id}/media"
        headers = {
            'Authorization': f'Bearer {self.account_id.access_token}',
        }

        file_content = base64.b64decode(self.header_media_file)
        # Ensure filename has an appropriate extension for Meta
        ext_map = {'image': '.jpg', 'video': '.mp4', 'document': '.pdf'}
        extension = ext_map.get(self.header_type, '')
        
        orig_filename = self.header_media_filename or 'header_media'
        if extension and not orig_filename.lower().endswith(extension):
            filename = orig_filename + extension
        else:
            filename = orig_filename

        self.account_id._check_media_upload_size(self.header_media_file, self.header_type, filename)

        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            type_map = {'image': 'image/jpeg', 'video': 'video/mp4', 'document': 'application/pdf'}
            mime_type = type_map.get(self.header_type, 'application/octet-stream')

        files = {'file': (filename, io.BytesIO(file_content), mime_type)}
        # Meta expects simple 'type' like 'image', 'video' or 'document'
        data = {'messaging_product': 'whatsapp', 'type': self.header_type}

        try:
            response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            resp_data = response.json() if response.content else {}
            if response.status_code in (200, 201):
                media_handle = resp_data.get('id')
                self.header_media_url = media_handle
                _logger.info(f"Header media uploaded: {media_handle}")
                return media_handle
            else:
                error = resp_data.get('error', {})
                _logger.error(f"Header media upload failed: {error.get('message', '')}")
                return None
        except Exception as e:
            _logger.error(f"Header media upload exception: {e}")
            return None



    def action_open_meta_manager(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://business.facebook.com/wa/manage/message-templates/',
            'target': 'new',
        }

    def action_submit_to_meta(self):
        """Submit the template to Meta for approval"""
        self.ensure_one()
        if not self.account_id:
            raise UserError("Please select a WhatsApp Account first.")

        # Validation
        self.action_refresh_variables()
        self._validate_variable_structure()
        for var in self.variable_ids:
            if not var.sample_value:
                raise UserError(f"Missing sample value for variable {var.name}. Meta requires samples for all variables.")
        if self.has_buttons and not self.button_type:
            raise UserError("Please select a button type or disable buttons.")
        if self.button_type == 'call_to_action':
            has_url = bool(self.cta_url_text and self.cta_url_link)
            has_phone = bool(self.cta_phone_text and self.cta_phone_number)
            if not has_url and not has_phone:
                raise UserError("Call-to-action templates need a URL button or phone button.")
            if self.cta_url_link and not self.cta_url_link.startswith(('http://', 'https://')):
                raise UserError("URL buttons must start with http:// or https://.")
        if self.button_type == 'copy_code' and self.category != 'authentication':
            raise UserError("Copy-code OTP buttons are only valid for Authentication templates.")
        if self.is_carousel and not self.card_ids:
            raise UserError("Carousel templates require at least one card.")
        if self.is_carousel and len(self.card_ids) > 10:
            raise UserError("Meta allows a maximum of 10 cards per carousel template.")

        if self.header_type in ['image', 'video', 'document'] and not self.header_media_url:
            media_handle = self._upload_header_media()
            if not media_handle:
                raise UserError("Failed to upload header media. Please try again or provide a valid media file.")
        if self.is_carousel:
            for card in self.card_ids:
                if card.header_media_file and not card.header_media_url:
                    handle = card._upload_media_to_meta(self.account_id)
                    if not handle:
                        raise UserError(f"Failed to upload carousel media for card '{card.body[:30] or card.id}'.")

        url = f"https://graph.facebook.com/{self.account_id.api_version}/{self.account_id.business_account_id}/message_templates"
        headers = {
            'Authorization': f'Bearer {self.account_id.access_token}',
            'Content-Type': 'application/json',
        }

        # 1. Clean Name (Meta requires lowercase alphanumeric and underscores only)
        clean_name = re.sub(r'[^a-z0-9_]', '', self.name.lower().replace(' ', '_'))
        language_code = self.language_code or self.language or 'en'
        write_vals = {
            'meta_template_name': clean_name,
            'language_code': language_code,
            'language': self._normalize_language_selection(language_code),
        }
        if clean_name != self.name:
            write_vals['name'] = clean_name
        self.write(write_vals)

        components = []
        if self.is_carousel:
            carousel_cards = []
            for card in self.card_ids:
                card_components = [
                    {
                        "type": "HEADER",
                        "format": card.header_type.upper(),
                        "example": {"header_handle": [card.header_media_url or "DUMMY_HANDLE"]}
                    },
                    {
                        "type": "BODY",
                        "text": card.body
                    }
                ]
                card_buttons = []
                if card.button_text_1:
                    if card.button_type_1 == 'quick_reply':
                        card_buttons.append({"type": "QUICK_REPLY", "text": card.button_text_1})
                    else:
                        card_buttons.append({"type": "URL", "text": card.button_text_1, "url": card.button_url_1 or "https://example.com"})
                if card.button_text_2:
                    card_buttons.append({"type": "QUICK_REPLY", "text": card.button_text_2})
                if card_buttons:
                    card_components.append({"type": "BUTTONS", "buttons": card_buttons})
                carousel_cards.append({"components": card_components})
            components.append({"type": "CAROUSEL", "cards": carousel_cards})
        else:
            # Standard Header
            if self.header_type != 'none':
                header_comp = {'type': 'HEADER', 'format': self.header_type.upper()}
                if self.header_type == 'text':
                    header_comp['text'] = self.header_text
                    text_vars = set(re.findall(r'\{\{\d+\}\}', self.header_text or ''))
                    if text_vars:
                        var_name = sorted(list(text_vars), key=lambda x: int(re.findall(r'\d+', x)[0]))[0]
                        var_rec = self.variable_ids.filtered(lambda x: x.name == var_name)
                        sample = var_rec[0].sample_value if var_rec else 'Sample Header'
                        header_comp['example'] = {'header_text': [sample]}
                elif self.header_type in ['image', 'video', 'document']:
                    header_comp['example'] = {'header_handle': [self.header_media_url]}
                components.append(header_comp)

            # Standard Body
            body_comp = {'type': 'BODY', 'text': self.body}
            vars_found = set(re.findall(r'\{\{\d+\}\}', self.body))
            if vars_found:
                sorted_vars = sorted(list(vars_found), key=lambda x: int(re.findall(r'\d+', x)[0]))
                example_values = []
                for v_name in sorted_vars:
                    var_rec = self.variable_ids.filtered(lambda x: x.name == v_name)
                    example_values.append(var_rec[0].sample_value if var_rec else f'Sample for {v_name}')
                body_comp['example'] = {'body_text': [example_values]}
            components.append(body_comp)

            # Standard Footer
            if self.category == 'authentication' and self.button_type == 'copy_code':
                components.append({
                    'type': 'FOOTER',
                    'code_expiration_minutes': max(self.code_expiration_minutes or 10, 1),
                })
            elif self.footer:
                components.append({'type': 'FOOTER', 'text': self.footer})

        # Buttons
        if self.has_buttons:
            buttons = []
            if self.button_type == 'quick_reply':
                if self.button_text_1:
                    buttons.append({'type': 'QUICK_REPLY', 'text': self.button_text_1})
                if self.button_text_2:
                    buttons.append({'type': 'QUICK_REPLY', 'text': self.button_text_2})
                if self.button_text_3:
                    buttons.append({'type': 'QUICK_REPLY', 'text': self.button_text_3})
            elif self.button_type == 'call_to_action':
                if self.cta_url_text and self.cta_url_link:
                    buttons.append({'type': 'URL', 'text': self.cta_url_text, 'url': self.cta_url_link})
                if self.cta_phone_text and self.cta_phone_number:
                    buttons.append({'type': 'PHONE_NUMBER', 'text': self.cta_phone_text, 'phone_number': self.cta_phone_number})
            elif self.button_type == 'copy_code':
                buttons.append({
                    'type': 'OTP',
                    'otp_type': 'COPY_CODE',
                    'text': 'Copy Code',
                })
            
            if buttons:
                components.append({
                    'type': 'BUTTONS',
                    'buttons': buttons
                })


        payload = {
            'name': clean_name,
            'language': language_code,
            'category': self.category.upper(),
            'allow_category_change': True,
            'components': components
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response_data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                self.write({
                    'status': 'pending',
                    'template_id': response_data.get('id')
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Submitted!',
                        'message': 'Template submitted for approval.',
                        'type': 'success',
                    }
                }
            else:
                error = response_data.get('error', {})
                msg = f"[{error.get('code', '?')}] {error.get('message', 'Unknown error')}"
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Submission Failed',
                        'message': msg,
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error(f"Template submission failed: {str(e)}")
            raise

class WhatsAppTemplateVariable(models.Model):
    """Maps {{1}}, {{2}} to specific Odoo fields or data types for dynamic personalization"""
    _name = 'whatsapp.template.variable'
    _description = 'Template Attribute Mapping'
    _order = 'sequence'

    template_id = fields.Many2one('whatsapp.template', required=True, ondelete='cascade')
    name = fields.Char('Variable', required=True, help="e.g. {{1}}")
    sequence = fields.Integer('Sequence', default=1)
    
    sample_value = fields.Char('Sample Value', required=True, help="Dummy value sent to Meta for approval")
    
    field_type = fields.Selection([
        ('text', 'Text (e.g. Name, City)'),
        ('currency', 'Currency Amount'),
        ('date_time', 'Date / Time'),
        ('url', 'URL Link'),
        ('document', 'Document URL'),
    ], string='Attribute Type', default='text', required=True)
    
    odoo_field = fields.Char('Map to Odoo Field', help='Optional: Automatically pull data (e.g. partner_id.name)')
    
    fallback_value = fields.Char('Fallback Value', help='Used if mapped Odoo field is empty')


class WhatsAppTemplateCard(models.Model):
    """Individual cards for Carousel Templates"""
    _name = 'whatsapp.template.card'
    _description = 'WhatsApp Template Card'
    _order = 'sequence'

    template_id = fields.Many2one('whatsapp.template', required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    
    header_type = fields.Selection([
        ('image', 'Image'),
        ('video', 'Video'),
    ], string='Header Type', default='image', required=True)
    
    header_media_file = fields.Binary('Card Media', required=True)
    header_media_filename = fields.Char('Filename')
    header_media_url = fields.Char('Media Handle/URL')
    
    body = fields.Text('Card Body', required=True, help="Max 160 characters")
    
    # Buttons (Max 2 per card)
    button_text_1 = fields.Char('Button 1', help="Max 25 characters")
    button_text_2 = fields.Char('Button 2')
    
    button_type_1 = fields.Selection([
        ('quick_reply', 'Quick Reply'),
        ('url', 'URL'),
    ], string='Button 1 Type', default='quick_reply')
    
    button_url_1 = fields.Char('Button 1 URL')

    def _upload_media_to_meta(self, account):
        """Upload card media and return Meta media handle."""
        self.ensure_one()
        if not account:
            raise UserError("A WhatsApp account is required to upload carousel media.")
        if not self.header_media_file:
            raise UserError("Carousel card media file is missing.")

        extension = '.jpg' if self.header_type == 'image' else '.mp4'
        filename = self.header_media_filename or f"carousel_card_{self.id or 'new'}{extension}"
        if extension and not filename.lower().endswith(extension):
            filename = f"{filename}{extension}"

        media_id = account._upload_media_to_meta(self.header_media_file, filename, self.header_type)
        self.write({'header_media_url': media_id})
        return media_id

