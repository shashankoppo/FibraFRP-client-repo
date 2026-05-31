# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
import requests
import json
import logging
import re
import base64
from html import escape as html_escape

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
    meta_state = fields.Char('Meta State', readonly=True, help='Raw template state reported by Meta, such as PAUSED or DISABLED.')
    meta_quality_rating = fields.Char('Meta Quality Rating', readonly=True)
    meta_disabled_reason = fields.Char('Meta Disabled/Paused Reason', readonly=True)
    last_meta_event = fields.Char('Last Meta Event', readonly=True)
    last_meta_event_date = fields.Datetime('Last Meta Event Date', readonly=True)
    audit_ids = fields.One2many('whatsapp.template.audit', 'template_id', string='Meta Audit Trail')

    # Variables/Attributes Mapping
    variable_ids = fields.One2many('whatsapp.template.variable', 'template_id', string='Attributes Mapping')

    def _variable_source_texts(self):
        self.ensure_one()
        texts = [self.body or '']
        if self.header_type == 'text':
            texts.append(self.header_text or '')
        if self.is_carousel:
            texts.extend(self.card_ids.mapped('body'))
        elif self.has_buttons and self.button_type == 'call_to_action':
            texts.append(self.cta_url_link or '')
        return texts

    @api.onchange('is_carousel', 'body', 'header_type', 'header_text', 'has_buttons', 'button_type', 'cta_url_link', 'card_ids')
    def onchange_extract_variables(self):
        self.action_refresh_variables()

    def action_refresh_variables(self):
        """Automatically detect {{1}}, {{2}} and create attribute mapping rows"""
        for rec in self:
            found_vars = set()
            for text in rec._variable_source_texts():
                found_vars.update(re.findall(r'\{\{\d+\}\}', text or ''))
            
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
        for text in self._variable_source_texts():
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
        ('paused', 'Paused'),
        ('disabled', 'Disabled'),
    ], string='Status', default='draft', required=True)
    
    active = fields.Boolean('Active', default=True)
    
    # Usage statistics
    usage_count = fields.Integer('Times Used', default=0)
    
    preview_html = fields.Html('Preview', compute='_compute_preview_html')
    preview_text = fields.Text('Preview Text', compute='_compute_preview_html')

    def _log_meta_audit(self, event, status=False, reason=False, raw_data=False):
        """Store Meta status/sync feedback so admins can debug template health."""
        for rec in self:
            rec.env['whatsapp.template.audit'].sudo().create({
                'template_id': rec.id,
                'account_id': rec.account_id.id if rec.account_id else False,
                'event': event or 'sync',
                'status': status or rec.status,
                'reason': reason or False,
                'raw_data': json.dumps(raw_data, ensure_ascii=False, indent=2) if isinstance(raw_data, (dict, list)) else (raw_data or False),
            })
            rec.sudo().write({
                'last_meta_event': event or status or 'sync',
                'last_meta_event_date': fields.Datetime.now(),
            })

    def _validate_meta_constraints(self):
        """Validate common Meta WhatsApp template rules before submit/send test."""
        for rec in self:
            rec._validate_variable_structure()
            if rec.header_type == 'text' and len(rec.header_text or '') > 60:
                raise UserError("Text headers can be at most 60 characters.")
            if len(rec.footer or '') > 60:
                raise UserError("Footers can be at most 60 characters.")
            if len(rec.body or '') > 4096:
                raise UserError("Template body is too long. Keep it within WhatsApp's 4096 character text limit.")
            if rec.is_carousel:
                if not rec.card_ids:
                    raise UserError("Carousel templates need at least one card.")
                if len(rec.card_ids) > 10:
                    raise UserError("Carousel templates can contain at most 10 cards.")
                for card in rec.card_ids:
                    if not (card.body or '').strip():
                        raise UserError("Every carousel card needs body text.")
                    if len(card.body or '') > 160:
                        raise UserError("Carousel card body text can be at most 160 characters.")
                    if card.header_type in ('image', 'video') and not (card.header_media_file or card.header_media_url):
                        raise UserError("Every carousel card needs image/video header media.")
                    if card.button_text_1 and len(card.button_text_1) > 25:
                        raise UserError("Carousel button text can be at most 25 characters.")
                    if card.button_text_2 and len(card.button_text_2) > 25:
                        raise UserError("Carousel button text can be at most 25 characters.")
                    if card.button_type_1 == 'url' and card.button_url_1 and not card.button_url_1.startswith(('http://', 'https://')):
                        raise UserError("Carousel URL buttons must start with http:// or https://.")
            if rec.header_type in ('image', 'video', 'document') and not (
                rec.header_media_url or rec.header_media_file
            ):
                raise UserError(
                    f"{rec.header_type.title()} header templates require a default media file or uploaded Meta media handle."
                )
            if rec.has_buttons and not rec.button_type:
                raise UserError("Please select a button type or disable buttons.")
            if rec.has_buttons and rec.button_type == 'quick_reply':
                buttons = [text for text in [rec.button_text_1, rec.button_text_2, rec.button_text_3] if text]
                if not buttons:
                    raise UserError("Quick-reply templates need at least one button.")
                if len(buttons) > 3:
                    raise UserError("WhatsApp quick-reply templates support a maximum of 3 buttons.")
                if any(len(text) > 25 for text in buttons):
                    raise UserError("Quick-reply button text can be at most 25 characters.")
            if rec.has_buttons and rec.button_type == 'call_to_action':
                has_url = bool(rec.cta_url_text and rec.cta_url_link)
                has_phone = bool(rec.cta_phone_text and rec.cta_phone_number)
                if not has_url and not has_phone:
                    raise UserError("Call-to-action templates need a URL button or phone button.")
                if rec.cta_url_link and not rec.cta_url_link.startswith(('http://', 'https://')):
                    raise UserError("URL buttons must start with http:// or https://.")
                if rec.cta_url_link and rec.cta_url_link.count('{{') > 1:
                    raise UserError("URL buttons can contain at most one variable placeholder.")
                if any(text and len(text) > 25 for text in [rec.cta_url_text, rec.cta_phone_text]):
                    raise UserError("Call-to-action button text can be at most 25 characters.")
            if rec.has_buttons and rec.button_type == 'copy_code' and rec.category != 'authentication':
                raise UserError("Copy-code OTP buttons are only valid for Authentication templates.")

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
        name = self.meta_template_name or self.name or ''
        import re
        name = name.lower()
        name = re.sub(r'[^a-z0-9_]', '_', name)
        name = re.sub(r'_+', '_', name)
        return name.strip('_')


    def _media_parameter(self, media_type, media_value, media_filename=False):
        if not media_value:
            raise UserError(f"{media_type.title()} header templates require a media handle or public URL before sending.")
        media_value = str(media_value).strip()
        if media_value.startswith(('http://', 'https://')):
            media_object = {"link": media_value}
            if media_type == 'document' and media_filename:
                media_object["filename"] = str(media_filename)
            return {"type": media_type, media_type: media_object}
        # Meta API sometimes requires 'id' to be an integer (e.g. v19.0 JSON schema)
        if media_value.isdigit():
            media_object = {"id": int(media_value)}
            if media_type == 'document' and media_filename:
                media_object["filename"] = str(media_filename)
            return {"type": media_type, media_type: media_object}
        # If it's a non-digit handle string (e.g. resumable upload handle), return it as 'handle'
        media_object = {"handle": media_value}
        if media_type == 'document' and media_filename:
            media_object["filename"] = str(media_filename)
        return {"type": media_type, media_type: media_object}

    def _header_media_upload_filename(self, media_type, filename=None):
        self.ensure_one()
        filename = (filename or self.header_media_filename or f"{self._get_send_template_name()}_header").strip()
        if '.' in filename:
            return filename
        extension = {
            'image': 'jpg',
            'video': 'mp4',
            'document': 'pdf',
        }.get(media_type, 'bin')
        return f"{filename}.{extension}"

    def _resolve_header_media_value(
        self,
        media_type,
        media_file=False,
        media_filename=False,
        media_url=False,
        account=False,
    ):
        self.ensure_one()
        if media_url:
            return str(media_url).strip()

        upload_account = account or self.account_id
        if media_file:
            if not upload_account:
                raise UserError(f"{media_type.title()} header templates require a WhatsApp account to upload media.")
            filename = self._header_media_upload_filename(media_type, media_filename)
            return upload_account._upload_media_to_meta(media_file, filename, media_type)

        if self.header_media_url:
            return self.header_media_url

        if self.header_media_file:
            if not upload_account:
                raise UserError(f"{media_type.title()} header templates require a WhatsApp account to upload media.")
            filename = self._header_media_upload_filename(media_type)
            media_id = upload_account._upload_media_to_meta(self.header_media_file, filename, media_type)
            self.sudo().write({'header_media_url': media_id})
            return media_id

        raise UserError(
            f"{self.display_name}: {media_type.title()} header templates require a media handle, "
            "public HTTPS URL, template header file, or per-send media attachment before sending."
        )

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

    def _resolve_variable_value(self, variable, partner=False, record=False):
        if not variable:
            return ' '
        field_path = (variable.odoo_field or '').strip()
        # Try resolving against explicit record first (e.g. account.move, sale.order)
        if record and field_path:
            for candidate in [field_path]:
                try:
                    value = record.mapped(candidate)
                    formatted = self._format_variable_value(value)
                    if formatted:
                        return formatted
                except Exception as e:
                    _logger.debug("Template variable %s record path %s failed: %s", variable.name, candidate, e)
        # Fall back to partner-based resolution (original behavior)
        if partner and field_path:
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

    def _variable_parameters(self, variables, partner=False, record=False):
        return [
            {"type": "text", "text": str(self._resolve_variable_value(variable, partner=partner, record=record))}
            for variable in variables
        ]

    def _prepare_send_payload(
        self,
        components=None,
        partner=None,
        record=None,
        header_media_file=False,
        header_media_filename=False,
        header_media_url=False,
        account=False,
    ):
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
                    card_body_params = self._variable_parameters(card_variables, partner=partner, record=record)
                    if card_body_params:
                        card_components.append({"type": "body", "parameters": card_body_params})

                    cards.append({"index": idx, "components": card_components})

                if cards:
                    components.append({"type": "carousel", "cards": cards})

            else:
                if self.header_type in ['image', 'video', 'document']:
                    header_media_value = self._resolve_header_media_value(
                        self.header_type,
                        media_file=header_media_file,
                        media_filename=header_media_filename,
                        media_url=header_media_url,
                        account=account,
                    )
                    header_filename = header_media_filename or self.header_media_filename
                    if self.header_type == 'document':
                        header_filename = self._header_media_upload_filename(self.header_type, header_filename)
                    header_param = self._media_parameter(
                        self.header_type,
                        header_media_value,
                        media_filename=header_filename,
                    )
                    components.append({"type": "header", "parameters": [header_param]})

                elif self.header_type == 'text' and '{{' in (self.header_text or ''):
                    header_variables = self._variables_for_names(self._variable_names_for_text(self.header_text))
                    header_params = self._variable_parameters(header_variables, partner=partner, record=record)
                    if header_params:
                        components.append({"type": "header", "parameters": header_params})

                body_variables = self._variables_for_names(self._variable_names_for_text(self.body))
                body_params = self._variable_parameters(body_variables, partner=partner, record=record)
                if body_params:
                    components.append({"type": "body", "parameters": body_params})

                if self.has_buttons:
                    if self.button_type == 'call_to_action' and self.cta_url_link and '{{' in self.cta_url_link:
                        button_variables = self._variables_for_names(self._variable_names_for_text(self.cta_url_link))
                        if button_variables:
                            val = self._resolve_variable_value(button_variables[0], partner=partner, record=record)
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

    def _preview_data_uri(self, binary_value, mime_type='image/*'):
        if not binary_value:
            return False
        try:
            if isinstance(binary_value, bytes):
                encoded = binary_value.decode('utf-8')
            else:
                encoded = str(binary_value)
            # If the value is already base64, keep it. Otherwise encode it.
            try:
                base64.b64decode(encoded, validate=True)
            except Exception:
                encoded = base64.b64encode(encoded.encode('utf-8')).decode('utf-8')
            return f"data:{mime_type};base64,{encoded}"
        except Exception:
            return False

    def _preview_document_icon_class(self, filename):
        name = (filename or '').lower()
        if name.endswith(('.doc', '.docx')):
            return 'fa-file-word-o text-primary'
        if name.endswith(('.xls', '.xlsx')):
            return 'fa-file-excel-o text-success'
        if name.endswith(('.ppt', '.pptx')):
            return 'fa-file-powerpoint-o text-warning'
        if name.endswith('.pdf'):
            return 'fa-file-pdf-o text-danger'
        return 'fa-file-text-o text-muted'

    def _render_preview_text(self, text, partner=False, record=False, highlight=True):
        """Render template variables exactly once for all template previews."""
        self.ensure_one()
        rendered = html_escape(text or '')
        variables_by_name = {var.name: var for var in self.variable_ids}

        def replace_numbered(match):
            token = match.group(0)
            variable = variables_by_name.get(token)
            value = self._resolve_variable_value(variable, partner=partner, record=record) if variable else token
            value = html_escape(str(value or ''))
            if not highlight:
                return value
            return (
                "<span style='background:rgba(37,211,102,.14);color:#00694b;"
                "font-weight:600;padding:0 4px;border-radius:4px;'>%s</span>"
            ) % value

        rendered = re.sub(r'\{\{\d+\}\}', replace_numbered, rendered)
        replacements = self.env['whatsapp.placeholder'].get_placeholder_values(
            context_type='contact',
            partner=partner,
            record=record,
        )
        for token, value in replacements.items():
            rendered = rendered.replace(token, html_escape(str(value or '')))
        return rendered

    def _preview_media_url(self, message=False, field_name='header_media_file', media_type='image', media_file=False, media_url=False):
        self.ensure_one()
        if message and message.media_file:
            route = 'image' if media_type == 'image' else 'content'
            return f"/web/{route}/whatsapp.message/{message.id}/media_file"
        if media_file:
            mime = 'image/*' if media_type == 'image' else 'application/octet-stream'
            return self._preview_data_uri(media_file, mime)
        if self.id and getattr(self, field_name, False):
            route = 'image' if media_type == 'image' else 'content'
            return f"/web/{route}/whatsapp.template/{self.id}/{field_name}"
        url = media_url or (message.media_url if message else False) or self.header_media_url
        return url if url and str(url).startswith(('http://', 'https://')) else False

    def _render_preview_header_html(
        self,
        partner=False,
        record=False,
        message=False,
        header_media_file=False,
        header_media_filename=False,
        header_media_url=False,
    ):
        self.ensure_one()
        header_type = self.header_type
        filename = (
            header_media_filename
            or (message.media_filename if message else False)
            or self.header_media_filename
            or self.name
            or 'Attachment'
        )
        has_media_reference = bool(
            header_media_file
            or header_media_url
            or (message and (message.media_file or message.media_url))
            or self.header_media_file
            or self.header_media_url
        )
        if header_type == 'text' and self.header_text:
            return (
                "<div style='font-weight:700;font-size:15px;margin-bottom:6px;color:#111b21;'>%s</div>"
            ) % self._render_preview_text(self.header_text, partner=partner, record=record)
        if header_type == 'image':
            img_src = self._preview_media_url(
                message=message,
                media_type='image',
                media_file=header_media_file,
                media_url=header_media_url,
            )
            if img_src:
                return (
                    "<div style='background:#e9edef;height:150px;border-radius:8px;margin-bottom:8px;"
                    "overflow:hidden;'><img src='%s' style='width:100%%;height:100%%;object-fit:cover;' "
                    "alt='Header image preview'/></div>"
                ) % html_escape(img_src)
            if has_media_reference:
                return (
                    "<div style='background:#e9edef;border-radius:8px;height:120px;margin-bottom:8px;"
                    "display:flex;align-items:center;justify-content:center;color:#667781;'>"
                    "<i class='fa fa-image fa-2x' title='Image header'></i><span style='margin-left:8px;'>"
                    "Image header attached</span></div>"
                )
            return (
                "<div style='background:#e9edef;border-radius:8px;height:120px;margin-bottom:8px;"
                "display:flex;align-items:center;justify-content:center;color:#667781;'>"
                "<i class='fa fa-image fa-2x' title='Image header'></i><span style='margin-left:8px;'>"
                "Image header required</span></div>"
            )
        if header_type == 'video':
            video_src = self._preview_media_url(
                message=message,
                media_type='video',
                media_file=header_media_file,
                media_url=header_media_url,
            )
            if video_src:
                return (
                    "<div style='background:#111b21;border-radius:8px;margin-bottom:8px;overflow:hidden;'>"
                    "<video src='%s' controls style='width:100%%;max-height:180px;display:block;'></video></div>"
                ) % html_escape(video_src)
            if has_media_reference:
                return (
                    "<div style='background:#111b21;height:120px;border-radius:8px;margin-bottom:8px;"
                    "display:flex;align-items:center;justify-content:center;color:white;'>"
                    "<i class='fa fa-play-circle fa-3x' title='Video header'></i><span style='margin-left:8px;'>"
                    "Video header attached</span></div>"
                )
            return (
                "<div style='background:#111b21;height:120px;border-radius:8px;margin-bottom:8px;"
                "display:flex;align-items:center;justify-content:center;color:white;'>"
                "<i class='fa fa-play-circle fa-3x' title='Video header'></i><span style='margin-left:8px;'>"
                "Video header required</span></div>"
            )
        if header_type == 'document':
            doc_src = self._preview_media_url(
                message=message,
                media_type='document',
                media_file=header_media_file,
                media_url=header_media_url,
            )
            icon = self._preview_document_icon_class(filename)
            label = html_escape(filename or 'Document header')
            if doc_src:
                name_html = "<a href='%s' target='_blank' style='color:#111b21;text-decoration:none;font-weight:600;'>%s</a>" % (
                    html_escape(doc_src),
                    label,
                )
                hint = 'Document header attached'
            elif has_media_reference:
                name_html = "<span style='color:#111b21;font-weight:600;'>%s</span>" % label
                hint = 'Document header attached'
            else:
                name_html = "<span style='color:#111b21;font-weight:600;'>%s</span>" % label
                hint = 'Document header required before sending'
            return (
                "<div style='background:#fff;border:1px solid #e9edef;border-radius:8px;margin-bottom:8px;"
                "padding:10px;display:flex;align-items:center;gap:10px;box-shadow:0 1px 1px rgba(11,20,26,.08);'>"
                "<i class='fa %s fa-2x'></i><div style='min-width:0;flex:1;'>"
                "<div style='overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>%s</div>"
                "<div style='font-size:12px;color:#667781;'>%s</div></div></div>"
            ) % (icon, name_html, html_escape(hint))
        return ''

    def _render_preview_buttons_html(self):
        self.ensure_one()
        if not self.has_buttons:
            return ''
        labels = []
        if self.button_type == 'quick_reply':
            labels = [('fa-reply', self.button_text_1), ('fa-reply', self.button_text_2), ('fa-reply', self.button_text_3)]
        elif self.button_type == 'call_to_action':
            labels = [('fa-external-link', self.cta_url_text), ('fa-phone', self.cta_phone_text)]
        elif self.button_type == 'copy_code':
            labels = [('fa-copy', 'Copy code')]
        buttons = ''.join(
            "<div style='background:#fff;color:#00a884;font-weight:600;text-align:center;padding:10px;"
            "font-size:14px;border-top:1px solid #e9edef;display:flex;align-items:center;justify-content:center;gap:8px;'>"
            "<i class='fa %s'></i>%s</div>" % (icon, html_escape(label))
            for icon, label in labels if label
        )
        if not buttons:
            return ''
        return (
            "<div style='margin-top:6px;border-radius:8px;overflow:hidden;"
            "box-shadow:0 1px 1px rgba(11,20,26,.08);'>%s</div>"
        ) % buttons

    def _render_preview_carousel_html(self, partner=False, record=False):
        self.ensure_one()
        cards = []
        for card in self.card_ids.sorted('sequence'):
            media = ''
            if card.header_media_file and card.id:
                media = (
                    "<img src='/web/image/whatsapp.template.card/%s/header_media_file' "
                    "style='width:100%%;height:110px;object-fit:cover;' alt='Card media'/>"
                ) % card.id
            elif card.header_media_url and str(card.header_media_url).startswith(('http://', 'https://')):
                media = (
                    "<img src='%s' style='width:100%%;height:110px;object-fit:cover;' alt='Card media'/>"
                ) % html_escape(card.header_media_url)
            else:
                media = (
                    "<div style='height:110px;background:#e9edef;display:flex;align-items:center;"
                    "justify-content:center;color:#667781;'><i class='fa fa-image fa-2x'></i></div>"
                )
            card_buttons = ''
            for text in [card.button_text_1, card.button_text_2]:
                if text:
                    card_buttons += (
                        "<div style='border-top:1px solid #e9edef;padding:8px;text-align:center;"
                        "color:#00a884;font-weight:600;font-size:13px;'>%s</div>"
                    ) % html_escape(text)
            cards.append(
                "<div style='flex:0 0 210px;background:#fff;border-radius:8px;margin-right:8px;"
                "box-shadow:0 1px 1px rgba(11,20,26,.13);overflow:hidden;'>"
                "%s<div style='padding:9px;font-size:13px;color:#111b21;white-space:pre-wrap;'>%s</div>%s</div>"
                % (media, self._render_preview_text(card.body, partner=partner, record=record), card_buttons)
            )
        return (
            "<div style='display:flex;overflow-x:auto;padding:2px 0 8px;'>%s</div>"
        ) % ''.join(cards or [
            "<div style='background:#fff;border-radius:8px;padding:12px;color:#667781;'>Add carousel cards to preview.</div>"
        ])

    @api.model
    def _render_text_preview_html(self, body, partner=False, shell=True):
        value = html_escape(body or '')
        if partner:
            value = value.replace('{{name}}', html_escape(partner.name or ''))
            value = value.replace('{{company}}', html_escape(getattr(partner, 'company_name', False) or ''))
        bubble = (
            "<div style='background:#fff;border-radius:0 8px 8px 8px;padding:10px 12px;"
            "box-shadow:0 1px .5px rgba(11,20,26,.13);max-width:560px;'>"
            "<div style='font-size:14px;color:#111b21;white-space:pre-wrap;line-height:1.45;'>%s</div>"
            "<div style='font-size:11px;color:#667781;text-align:right;margin-top:4px;'>Now</div></div>"
        ) % value
        if not shell:
            return bubble
        return (
            "<div style='background:#efeae2;padding:14px;border-radius:8px;"
            "font-family:sans-serif;'>%s</div>"
        ) % bubble

    def _render_customer_preview_html(
        self,
        partner=False,
        record=False,
        message=False,
        header_media_file=False,
        header_media_filename=False,
        header_media_url=False,
        body_override=False,
        shell=True,
        compact=False,
        include_template_name=False,
    ):
        self.ensure_one()
        if self.is_carousel:
            content = self._render_preview_carousel_html(partner=partner, record=record)
        else:
            header_html = self._render_preview_header_html(
                partner=partner,
                record=record,
                message=message,
                header_media_file=header_media_file,
                header_media_filename=header_media_filename,
                header_media_url=header_media_url,
            )
            body_html = self._render_preview_text(
                body_override if body_override is not False else self.body,
                partner=partner,
                record=record,
            )
            footer_html = (
                "<div style='font-size:12px;color:#667781;margin-top:6px;'>%s</div>" % html_escape(self.footer)
                if self.footer else ''
            )
            buttons_html = self._render_preview_buttons_html()
            label_html = (
                "<div style='font-weight:600;color:#667781;font-size:12px;margin-bottom:6px;'>"
                "<i class='fa fa-bolt'></i> %s</div>" % html_escape(self._get_send_template_name() or self.name)
                if include_template_name else ''
            )
            content = (
                "%s%s<div style='font-size:14px;color:#111b21;white-space:pre-wrap;"
                "line-height:1.45;'>%s</div>%s"
                "<div style='font-size:11px;color:#667781;text-align:right;margin-top:4px;'>Now</div>%s"
            ) % (label_html, header_html, body_html, footer_html, buttons_html)
        bubble_width = '100%' if compact else '340px'
        bubble = (
            "<div class='wa-template-preview-bubble' style='background:#fff;border-radius:0 8px 8px 8px;"
            "padding:8px;box-shadow:0 1px .5px rgba(11,20,26,.13);max-width:%s;'>%s</div>"
        ) % (bubble_width, content)
        if not shell:
            return bubble
        width = '100%' if compact else '380px'
        return (
            "<div class='wa-template-preview-shell' style='background:#efeae2;"
            "background-image:radial-gradient(rgba(17,27,33,.06) .8px, transparent .8px);"
            "background-size:18px 18px;padding:14px;border-radius:10px;font-family:sans-serif;"
            "max-width:%s;margin:0 auto;'>%s</div>"
        ) % (width, bubble)

    def _render_customer_preview_text(
        self,
        partner=False,
        record=False,
        message=False,
        header_media_file=False,
        header_media_filename=False,
        header_media_url=False,
        body_override=False,
        include_meta=True,
    ):
        """Return a safe, readable preview for Odoo forms that should not use HtmlViewer."""
        self.ensure_one()
        lines = []
        if include_meta:
            lines.append("Template: %s" % (self.display_name or self.name or "-"))
            lines.append("Status: %s | Language: %s" % (self.status or "-", self.language or "-"))
        preview = self._render_customer_preview_html(
            partner=partner,
            record=record,
            message=message,
            header_media_file=header_media_file,
            header_media_filename=header_media_filename,
            header_media_url=header_media_url,
            body_override=body_override,
            shell=False,
            compact=True,
        )
        text = html2plaintext(preview or '').strip()
        if text:
            lines.append(text)
        if self.header_type in ('image', 'video', 'document') and not (
            header_media_file
            or header_media_url
            or self.header_media_file
            or self.header_media_url
        ):
            lines.append(
                "Warning: %s header needs a media file, Meta media handle, or public HTTPS URL before sending."
                % self.header_type.title()
            )
        return "\n".join(line for line in lines if line)

    @api.depends('body', 'header_type', 'header_text', 'footer', 'has_buttons', 'button_type', 'button_text_1', 'button_text_2', 'button_text_3', 'cta_url_text', 'cta_url_link', 'cta_phone_text', 'cta_phone_number', 'copy_code_example', 'variable_ids.sample_value', 'header_media_file', 'header_media_filename', 'header_media_url', 'is_carousel', 'card_ids.body', 'card_ids.header_media_file', 'card_ids.header_media_url', 'card_ids.button_type_1', 'card_ids.button_text_1', 'card_ids.button_text_2', 'card_ids.button_url_1')
    def _compute_preview_html(self):
        for rec in self:
            try:
                rec.preview_html = rec._render_customer_preview_html(shell=True)
                rec.preview_text = rec._render_customer_preview_text()
            except Exception as exc:
                _logger.warning("Template preview failed for %s: %s", rec.id or rec.name, exc)
                safe_msg = html_escape(str(exc) or 'Template preview is not ready yet.')
                rec.preview_html = (
                    "<div class='alert alert-warning mb-0'>"
                    "<strong>Preview not ready.</strong><br/>%s"
                    "</div>"
                ) % safe_msg
                rec.preview_text = "Preview not ready. %s" % safe_msg
            continue
            if rec.is_carousel:
                cards_html = ""
                for card in rec.card_ids:
                    card_buttons = ""
                    if card.button_text_1:
                        card_buttons += f'<div style="border-top: 1px solid #e9edef; padding: 6px; text-align: center; color: #008069; font-weight: 600; font-size: 13px;">{html_escape(card.button_text_1)}</div>'
                    if card.button_text_2:
                        card_buttons += f'<div style="border-top: 1px solid #e9edef; padding: 6px; text-align: center; color: #008069; font-weight: 600; font-size: 13px;">{html_escape(card.button_text_2)}</div>'

                    cards_html += f"""
                    <div style="flex: 0 0 200px; background: #fff; border-radius: 8px; margin-right: 8px; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); overflow: hidden;">
                        <div style="background: #e9edef; height: 100px; display: flex; align-items: center; justify-content: center; color: #8696a0;">
                            <i class="fa fa-image fa-2x"></i>
                        </div>
                        <div style="padding: 8px; font-size: 13px; color: #111b21;">{html_escape(card.body or '')}</div>
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
            preview_body = html_escape(rec.body or 'Enter body text...')
            preview_header_text = html_escape(rec.header_text or '')
            
            # Map variables to sample values
            var_map = {}
            for var in rec.variable_ids:
                var_map[var.name] = var.sample_value or var.name
                
            # Replace {{x}} with highlighted sample value
            def replace_var(match):
                var_name = match.group(0)
                sample = html_escape(str(var_map.get(var_name, var_name)))
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
                                decoded_str = img_data.decode('utf-8')
                                base64.b64decode(decoded_str, validate=True)
                                img_src = f"data:image/png;base64,{decoded_str}"
                            except Exception:
                                img_src = f"data:image/png;base64,{base64.b64encode(img_data).decode('utf-8')}"
                        else:
                            try:
                                base64.b64decode(img_data, validate=True)
                                img_src = f"data:image/png;base64,{img_data}"
                            except Exception:
                                img_src = f"data:image/png;base64,{base64.b64encode(img_data.encode('utf-8')).decode('utf-8')}"
                    except Exception:
                        img_src = False

                else:
                    img_src = False
                if img_src:
                    header_html = f"<div style='background: #e9edef; height: 140px; border-radius: 8px; margin-bottom: 8px; overflow: hidden; position: relative;'><img src='{img_src}' style='width: 100%; height: 100%; object-fit: cover;' alt='Image preview'/></div>"
                else:
                    header_html = "<div style='background:#e9edef;height:140px;border-radius:8px;margin-bottom:8px;display:flex;align-items:center;justify-content:center;color:#667781;'><i class='fa fa-image me-1'></i> Image header</div>"
            elif rec.header_type == 'video':
                header_html = f"<div style='background: #111b21; height: 140px; border-radius: 8px; margin-bottom: 8px; display: flex; align-items: center; justify-content: center;'><i class='fa fa-play-circle fa-3x' style='color: rgba(255,255,255,0.8);'></i></div>"
            elif rec.header_type == 'document':
                header_html = f"<div style='background: rgba(0,0,0,0.05); padding: 12px; border-radius: 8px; margin-bottom: 8px; display: flex; align-items: center; gap: 10px;'><i class='fa fa-file-pdf-o fa-2x' style='color: #EA4335;'></i><div style='flex: 1; font-weight: 600; font-size: 13px;'>Document PDF</div></div>"

            # 3. Build Body & Footer
            body_html = f"<div style='color: #111b21; font-size: 14px; white-space: pre-wrap; margin-bottom: 6px; line-height: 1.45;'>{preview_body}</div>"
            
            footer_html = ""
            if rec.footer:
                footer_html = f"<div style='color: #8696a0; font-size: 12px; margin-top: 4px; display: flex; align-items: center; justify-content: space-between;'><span>{html_escape(rec.footer)}</span><span style='font-size: 10px;'>12:00 PM</span></div>"
            else:
                footer_html = f"<div style='color: #8696a0; font-size: 10px; margin-top: 4px; text-align: right;'>12:00 PM</div>"

            # 4. Build Buttons
            buttons_html = ""
            if rec.has_buttons:
                button_styles = "border-top: 1px solid #e9edef; padding: 10px 0; text-align: center; color: #00a884; font-weight: bold; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;"
                if rec.button_type == 'quick_reply':
                    for btn in [rec.button_text_1, rec.button_text_2, rec.button_text_3]:
                        if btn:
                            buttons_html += f"<div style='{button_styles}'><i class='fa fa-reply'></i> {html_escape(btn)}</div>"
                elif rec.button_type == 'call_to_action':
                    if rec.cta_url_text:
                        buttons_html += f"<div style='{button_styles}'><i class='fa fa-external-link'></i> {html_escape(rec.cta_url_text)}</div>"
                    if rec.cta_phone_text:
                        buttons_html += f"<div style='{button_styles}'><i class='fa fa-phone'></i> {html_escape(rec.cta_phone_text)}</div>"
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
                    background-image: radial-gradient(rgba(17,27,33,.06) .8px, transparent .8px);
                    background-size: 18px 18px;
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
                            <div style='font-weight: 700; font-size: 16px;'>{html_escape(rec.account_id.name or 'Business Account')}</div>
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
            'views': [(False, 'form')],
            'res_id': self.id,
            'target': 'new',
        }

    def action_send_test(self):
        """Open the normal send wizard prefilled with this template."""
        self.ensure_one()
        if self.status != 'approved':
            raise UserError("Only approved templates can be sent as a WhatsApp test.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Template Test',
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_account_id': self.account_id.id if self.account_id else False,
                'default_template_id': self.id,
            },
        }

    def action_generate_ai_draft(self):
        """Draft template body text without submitting anything to Meta."""
        self.ensure_one()
        if not self.env['elsx.ai.provider']._whatsapp_draft_enabled():
            raise UserError("WhatsApp AI drafts are disabled in Settings.")
        job = self.env['elsx.ai.job'].create_job(
            'custom',
            'AI template draft for %s' % (self.name or 'template'),
            origin=self,
            input_text=(
                "Draft a WhatsApp template body for FiberaFRP. "
                "Keep it Meta-friendly, concise, non-spammy, and include variables only when useful.\n"
                "Template name: %s\nCategory: %s\nExisting body: %s"
            ) % (self.name or '', self.category or '', self.body or ''),
            prompt_code='whatsapp_template_default',
        )
        job.action_run()
        if job.response_text:
            self.body = job.response_text[:4096]
            self.action_refresh_variables()
        return {
            'type': 'ir.actions.act_window',
            'name': 'AI Template Draft Job',
            'res_model': 'elsx.ai.job',
            'res_id': job.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
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
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_archive_record(self):
        self.write({'active': False})
        return True

    def action_unarchive_record(self):
        self.write({'active': True})
        return True

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
        self._validate_meta_constraints()
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
                    'template_id': response_data.get('id'),
                    'meta_state': response_data.get('status') or 'PENDING',
                })
                self._log_meta_audit('submitted', status='pending', raw_data=response_data or payload)
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
                self._log_meta_audit('submission_failed', status='rejected', reason=msg, raw_data=response_data or payload)
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


class WhatsAppTemplateAudit(models.Model):
    _name = 'whatsapp.template.audit'
    _description = 'WhatsApp Template Meta Audit'
    _order = 'create_date desc, id desc'

    template_id = fields.Many2one('whatsapp.template', required=True, ondelete='cascade')
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account')
    event = fields.Char(required=True)
    status = fields.Char()
    reason = fields.Text()
    raw_data = fields.Text('Raw Meta Payload')


class WhatsAppTemplateVariable(models.Model):
    """Maps {{1}}, {{2}} to specific Odoo fields or data types for dynamic personalization"""
    _name = 'whatsapp.template.variable'
    _description = 'Template Attribute Mapping'
    _order = 'sequence'

    template_id = fields.Many2one('whatsapp.template', required=True, ondelete='cascade')
    name = fields.Char('Variable', required=True, help="e.g. {{1}}")
    sequence = fields.Integer('Sequence', default=1)
    
    sample_value = fields.Char('Sample Value', help="Dummy value sent to Meta for approval")
    
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
    
    header_media_file = fields.Binary('Card Media')
    header_media_filename = fields.Char('Filename')
    header_media_url = fields.Char('Media Handle/URL')
    
    body = fields.Text('Card Body', help="Max 160 characters")
    
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

