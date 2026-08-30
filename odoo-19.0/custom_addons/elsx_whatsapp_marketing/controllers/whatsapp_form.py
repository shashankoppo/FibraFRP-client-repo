# -*- coding: utf-8 -*-
import base64
import json
import time
import hashlib
from html import escape

from odoo import fields, http
from odoo.http import request


class WhatsAppPublicFormController(http.Controller):

    def _request_ip(self):
        forwarded = request.httprequest.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.httprequest.remote_addr or ''

    def _rate_limit_ip(self, icp, token, ip_address):
        rate_seconds = int(icp.get_param('whatsapp.form.rate_limit.ip.seconds', default='30') or 0)
        if not rate_seconds or not ip_address:
            return False
        digest = hashlib.sha256(('%s:%s' % (token, ip_address)).encode('utf-8')).hexdigest()
        param_key = 'whatsapp.form.rate_limit.ip.%s' % digest
        now = time.time()
        previous = float(icp.get_param(param_key, default='0') or 0)
        if previous and now - previous < rate_seconds:
            return True
        icp.set_param(param_key, str(now))
        return False

    def _allowed_mimetypes(self, icp):
        raw = icp.get_param(
            'whatsapp.form.allowed_mimetypes',
            default='image/jpeg,image/png,image/webp,application/pdf',
        ) or ''
        return {item.strip().lower() for item in raw.split(',') if item.strip()}

    def _render_layout(self, title, body, status=200):
        html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f4f7f6; color: #162323; }}
    .wrap {{ max-width: 680px; margin: 0 auto; padding: 28px 16px; }}
    .card {{ background: #fff; border: 1px solid #dfe7e5; border-radius: 12px; padding: 22px; box-shadow: 0 10px 28px rgba(15, 35, 35, .08); }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    p {{ color: #526361; line-height: 1.45; }}
    label {{ display: block; font-weight: 650; margin: 16px 0 6px; }}
    input, textarea, select {{ width: 100%; box-sizing: border-box; border: 1px solid #cbd8d5; border-radius: 8px; padding: 11px 12px; font: inherit; }}
    textarea {{ min-height: 110px; resize: vertical; }}
    .hint {{ color: #667781; font-size: 13px; margin-top: 4px; }}
    .required {{ color: #b42318; }}
    .error {{ background: #fff1f1; border: 1px solid #ffd1d1; color: #9a1111; border-radius: 8px; padding: 10px 12px; margin: 12px 0; }}
    button {{ margin-top: 20px; border: 0; border-radius: 999px; padding: 12px 18px; background: #00a884; color: #fff; font-weight: 700; cursor: pointer; }}
    button.secondary {{ margin-top: 8px; background: #e8f3f0; color: #17635a; }}
    .success {{ background: #eefbf4; border: 1px solid #b8ebcf; color: #176337; border-radius: 8px; padding: 12px; }}
  </style>
  <script>
    function waCaptureLocation(key) {{
      if (!navigator.geolocation) {{
        alert("Location capture is not available in this browser.");
        return;
      }}
      navigator.geolocation.getCurrentPosition(function(pos) {{
        var value = pos.coords.latitude + "," + pos.coords.longitude;
        var input = document.getElementById(key);
        if (input) input.value = value;
      }}, function() {{
        alert("Location permission was not granted.");
      }});
    }}
  </script>
</head>
<body><div class="wrap"><div class="card">{body}</div></div></body>
</html>""".format(title=escape(title or ''), body=body)
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')], status=status)

    def _form_fields_html(self, form, submitted=None, errors=None, hidden=None):
        submitted = submitted or {}
        errors = errors or []
        hidden = hidden or {}
        parts = []
        if errors:
            parts.append('<div class="error">%s</div>' % '<br/>'.join(escape(error) for error in errors))
        parts.append('<form method="post" enctype="multipart/form-data">')
        parts.append('<input type="text" name="website_url" tabindex="-1" autocomplete="off" style="position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden;"/>')
        for key, value in hidden.items():
            if value not in (None, False, ''):
                parts.append('<input type="hidden" name="%s" value="%s"/>' % (escape(key), escape(str(value))))
        for field in form.field_ids.sorted('sequence'):
            key = field.field_key
            value = submitted.get(key, '')
            label = escape(field.name)
            required = ' required' if field.required else ''
            parts.append('<label for="%s">%s%s</label>' % (escape(key), label, ' <span class="required">*</span>' if field.required else ''))
            placeholder = escape(field.placeholder or '')
            if field.field_type == 'textarea':
                parts.append('<textarea id="%s" name="%s" placeholder="%s"%s>%s</textarea>' % (
                    escape(key), escape(key), placeholder, required, escape(value)
                ))
            elif field.field_type == 'select':
                parts.append('<select id="%s" name="%s"%s>' % (escape(key), escape(key), required))
                parts.append('<option value="">Select...</option>')
                for option in [line.strip() for line in (field.options_text or '').splitlines() if line.strip()]:
                    selected = ' selected' if option == value else ''
                    parts.append('<option value="%s"%s>%s</option>' % (escape(option), selected, escape(option)))
                parts.append('</select>')
            elif field.field_type in ('checkbox', 'consent'):
                checked = ' checked' if value in ('on', 'true', '1', True) else ''
                parts.append('<input id="%s" name="%s" type="checkbox"%s%s/>' % (escape(key), escape(key), checked, required))
            elif field.field_type == 'file':
                parts.append('<input id="%s" name="%s" type="file"%s/>' % (escape(key), escape(key), required))
            elif field.field_type == 'location':
                parts.append('<input id="%s" name="%s" type="text" placeholder="%s" value="%s"%s/>' % (
                    escape(key), escape(key), placeholder or 'Latitude,Longitude or delivery address', escape(value), required
                ))
                parts.append('<button class="secondary" type="button" onclick="waCaptureLocation(\'%s\')">Use my current location</button>' % escape(key))
            else:
                input_type = {
                    'email': 'email',
                    'phone': 'tel',
                    'number': 'number',
                    'date': 'date',
                }.get(field.field_type, 'text')
                parts.append('<input id="%s" name="%s" type="%s" placeholder="%s" value="%s"%s/>' % (
                    escape(key), escape(key), input_type, placeholder, escape(value), required
                ))
            if field.help_text:
                parts.append('<div class="hint">%s</div>' % escape(field.help_text))
        parts.append('<button type="submit">%s</button>' % escape(form.submit_label or 'Submit'))
        parts.append('</form>')
        return ''.join(parts)

    @http.route('/whatsapp/form/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def whatsapp_form_get(self, token, **kwargs):
        form = request.env['whatsapp.form'].sudo().search([('public_token', '=', token), ('active', '=', True)], limit=1)
        if not form:
            return self._render_layout('Form not found', '<h1>Form not available</h1><p>This form link is invalid or inactive.</p>', status=404)
        body = '<h1>%s</h1><p>%s</p>%s' % (
            escape(form.title or form.name),
            escape(form.description or ''),
            self._form_fields_html(form, hidden={
                'campaign_id': kwargs.get('campaign_id'),
                'source': kwargs.get('source'),
            }),
        )
        return self._render_layout(form.title or form.name, body)

    @http.route('/whatsapp/form/<string:token>', type='http', auth='public', methods=['POST'], csrf=False)
    def whatsapp_form_post(self, token, **post):
        form = request.env['whatsapp.form'].sudo().search([('public_token', '=', token), ('active', '=', True)], limit=1)
        if not form:
            return self._render_layout('Form not found', '<h1>Form not available</h1><p>This form link is invalid or inactive.</p>', status=404)

        ICP = request.env['ir.config_parameter'].sudo()
        rate_seconds = int(ICP.get_param('whatsapp.form.rate_limit.seconds', default='5') or 0)
        ip_address = self._request_ip()
        user_agent = (request.httprequest.headers.get('User-Agent') or '')[:512]
        session_key = 'wa_form_last_%s' % token
        now = time.time()
        if rate_seconds and request.session.get(session_key) and now - float(request.session.get(session_key) or 0) < rate_seconds:
            return self._render_layout('Please wait', '<h1>Please wait</h1><div class="error">Please wait a few seconds before submitting again.</div>', status=429)
        if self._rate_limit_ip(ICP, token, ip_address):
            return self._render_layout('Please wait', '<h1>Please wait</h1><div class="error">Please wait before submitting this form again.</div>', status=429)
        request.session[session_key] = now

        if post.get('website_url'):
            return self._render_layout(form.title or form.name, '<h1>Submitted</h1><div class="success">%s</div>' % escape(form.success_message or 'Thank you.'))

        values = {}
        errors = []
        upload_files = []
        max_upload_mb = int(ICP.get_param('whatsapp.form.max_upload.mb', default='10') or 10)
        max_upload_bytes = max(max_upload_mb, 1) * 1024 * 1024
        max_files = max(int(ICP.get_param('whatsapp.form.max_files', default='3') or 3), 0)
        max_total_upload_mb = int(ICP.get_param('whatsapp.form.max_total_upload.mb', default='20') or 20)
        max_total_upload_bytes = max(max_total_upload_mb, 1) * 1024 * 1024
        allowed_mimetypes = self._allowed_mimetypes(ICP)
        total_upload_bytes = 0
        total_upload_count = 0
        consent_given = False
        for field in form.field_ids.sorted('sequence'):
            value = post.get(field.field_key)
            if field.field_type == 'file':
                files = request.httprequest.files.getlist(field.field_key)
                files = [item for item in files if item and item.filename]
                if field.required and not files:
                    errors.append('%s is required.' % field.name)
                names = []
                for uploaded in files:
                    total_upload_count += 1
                    if max_files and total_upload_count > max_files:
                        errors.append('Too many files uploaded. Maximum allowed is %s.' % max_files)
                        continue
                    mimetype = (uploaded.mimetype or '').lower()
                    if allowed_mimetypes and mimetype not in allowed_mimetypes:
                        errors.append('%s has unsupported file type %s.' % (uploaded.filename, mimetype or 'unknown'))
                        continue
                    content = uploaded.read()
                    total_upload_bytes += len(content)
                    if len(content) > max_upload_bytes:
                        errors.append('%s is larger than the %s MB upload limit.' % (uploaded.filename, max_upload_mb))
                        continue
                    if total_upload_bytes > max_total_upload_bytes:
                        errors.append('Uploaded files exceed the %s MB total upload limit.' % max_total_upload_mb)
                        continue
                    names.append(uploaded.filename)
                    upload_files.append((field, uploaded.filename, mimetype, content))
                values[field.field_key] = names
                continue
            if field.field_type in ('checkbox', 'consent'):
                value = bool(value)
                if field.field_type == 'consent' and value:
                    consent_given = True
            elif isinstance(value, str):
                value = value.strip()
            if field.required and value in (False, None, ''):
                errors.append('%s is required.' % field.name)
            if field.field_type == 'email' and value and '@' not in value:
                errors.append('%s must be a valid email address.' % field.name)
            if field.field_type == 'number' and value:
                try:
                    float(value)
                except (TypeError, ValueError):
                    errors.append('%s must be a number.' % field.name)
            if field.field_type == 'location' and value and len(value) > 180:
                errors.append('%s is too long. Use coordinates or a short delivery location.' % field.name)
            values[field.field_key] = value
        if form.require_consent and not consent_given:
            errors.append('Consent is required.')

        if errors:
            body = '<h1>%s</h1><p>%s</p>%s' % (
                escape(form.title or form.name),
                escape(form.description or ''),
                self._form_fields_html(form, submitted=post, errors=errors, hidden={
                    'campaign_id': post.get('campaign_id'),
                    'source': post.get('source'),
                }),
            )
            return self._render_layout(form.title or form.name, body, status=400)

        campaign = request.env['whatsapp.campaign'].sudo().browse()
        if post.get('campaign_id'):
            try:
                campaign = request.env['whatsapp.campaign'].sudo().browse(int(post.get('campaign_id'))).exists()
            except (TypeError, ValueError):
                campaign = request.env['whatsapp.campaign'].sudo().browse()

        submission = request.env['whatsapp.form.submission'].sudo().create({
            'form_id': form.id,
            'campaign_id': campaign.id if campaign else False,
            'customer_name': values.get('name') or values.get('full_name') or values.get('customer_name'),
            'phone': values.get('phone') or values.get('mobile') or values.get('whatsapp'),
            'email': values.get('email'),
            'values_json': json.dumps(values, ensure_ascii=False),
            'source': post.get('source') or 'public_whatsapp_form',
            'ip_address': ip_address,
            'user_agent': user_agent,
            'consent_given': consent_given,
            'consent_date': fields.Datetime.now() if consent_given else False,
        })
        if consent_given and submission.partner_id and form.account_id:
            if 'whatsapp_opt_in' in submission.partner_id._fields:
                submission.partner_id.sudo().write({'whatsapp_opt_in': True})
            request.env['whatsapp.consent.log'].sudo().create({
                'partner_id': submission.partner_id.id,
                'account_id': form.account_id.id,
                'consent_type': 'all',
                'status': 'opted_in',
                'source': 'website',
                'ip_address': ip_address,
                'user_agent': user_agent,
                'notes': 'Consent captured from public WhatsApp form %s.' % form.display_name,
            })
        attachments = []
        for field, filename, mimetype, content in upload_files:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': filename,
                'res_model': 'whatsapp.form.submission',
                'res_id': submission.id,
                'type': 'binary',
                'datas': base64.b64encode(content),
                'mimetype': mimetype,
                'description': 'Uploaded through WhatsApp form field %s' % field.name,
            })
            attachments.append(attachment.id)
        if attachments:
            submission.sudo().write({'attachment_ids': [(6, 0, attachments)]})
        return self._render_layout(
            form.title or form.name,
            '<h1>Submitted</h1><div class="success">%s</div>' % escape(form.success_message or 'Thank you.'),
        )
