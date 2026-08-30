# -*- coding: utf-8 -*-
import json
import logging
import time

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ElsxAiProvider(models.Model):
    _name = 'elsx.ai.provider'
    _description = 'ELSX AI Provider'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider_type = fields.Selection([
        ('rules', 'Rules Draft Engine'),
        ('openai', 'OpenAI Compatible'),
        ('anthropic', 'Anthropic / Claude'),
        ('nvidia_nim', 'NVIDIA NIM'),
        ('deepseek', 'DeepSeek'),
        ('alibaba_qwen', 'Alibaba / Qwen'),
        ('huggingface', 'HuggingFace Inference'),
        ('local', 'Local / Self Hosted'),
        ('custom', 'Custom HTTP Endpoint'),
    ], default='rules', required=True)
    default_model = fields.Char(default='elsx-rules-v1')
    api_base_url = fields.Char(
        help="Base endpoint for the provider. For OpenAI-compatible providers this can be the full /chat/completions URL or the base /v1 URL."
    )
    api_key = fields.Char(groups='base.group_system')
    request_format = fields.Selection([
        ('openai_chat', 'OpenAI Chat Completions'),
        ('anthropic_messages', 'Anthropic Messages'),
        ('huggingface_inference', 'HuggingFace Inference'),
        ('custom_json', 'Custom JSON'),
    ], default='openai_chat', required=True)
    api_key_header = fields.Char(
        default='Authorization',
        help="Header used for custom providers. Standard providers use their native auth header automatically."
    )
    organization_id = fields.Char(groups='base.group_system')
    project_id = fields.Char(groups='base.group_system')
    timeout_seconds = fields.Integer(default=30)
    max_retries = fields.Integer(default=1)
    temperature = fields.Float(default=0.3)
    max_tokens = fields.Integer(default=800)
    response_path = fields.Char(
        help="Optional dot path to extract text from custom JSON, e.g. choices.0.message.content."
    )
    request_extra_json = fields.Text(
        help="Optional JSON object merged into provider requests. Keep credentials in API Key, not here."
    )
    enabled_tools = fields.Text(
        help="Reserved for future tool/function calling configuration. AI remains draft-only by default."
    )
    cost_input_per_1k = fields.Float(string='Input Cost / 1K Tokens', digits=(16, 6))
    cost_output_per_1k = fields.Float(string='Output Cost / 1K Tokens', digits=(16, 6))
    test_status = fields.Selection([
        ('untested', 'Untested'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], default='untested', readonly=True)
    last_test_date = fields.Datetime(readonly=True)
    last_test_error = fields.Text(readonly=True)
    last_test_response = fields.Text(readonly=True)
    notes = fields.Text()

    @api.model
    def _ai_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('elsx_ai.enabled', default='False') == 'True'

    @api.model
    def _auto_write_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('elsx_ai.auto_write', default='False') == 'True'

    @api.model
    def _whatsapp_draft_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('whatsapp.ai.draft.enabled', default='True') == 'True'

    @api.model
    def _whatsapp_auto_send_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('whatsapp.ai.auto_send', default='False') == 'True'

    @api.model
    def _get_default_provider(self):
        provider_id = self.env['ir.config_parameter'].sudo().get_param('elsx_ai.default_provider_id')
        provider = self.browse(int(provider_id)) if provider_id and str(provider_id).isdigit() else self.browse()
        if provider.exists() and provider.active:
            return provider
        return self.search([('active', '=', True)], order='sequence, id', limit=1)

    @api.model
    def _select_runtime_provider(self, prompt=False):
        """Prefer the configured real provider over the seed rules prompt binding.

        The seed prompts are intentionally safe and may point to the local rules
        engine. In production, admins expect Settings > Default AI Provider to
        control WhatsApp drafts. This keeps rules as a fallback without trapping
        every prompt in canned responses.
        """
        default_provider = self._get_default_provider()
        prompt_provider = prompt.provider_id if prompt and prompt.provider_id and prompt.provider_id.active else self.browse()
        if (
            default_provider
            and default_provider.active
            and default_provider.provider_type != 'rules'
            and (not prompt_provider or prompt_provider.provider_type == 'rules')
        ):
            return default_provider
        return prompt_provider or default_provider

    def action_test_provider(self):
        self.ensure_one()
        job = self.env['elsx.ai.job'].create({
            'name': _('Provider test: %s') % self.name,
            'provider_id': self.id,
            'job_type': 'custom',
            'input_text': 'Generate a short operational health check response in one sentence.',
        })
        try:
            job.with_context(bypass_ai_enabled=True).action_run()
            response = job.response_text or job.response_json or ''
            self.write({
                'test_status': 'success',
                'last_test_date': fields.Datetime.now(),
                'last_test_error': False,
                'last_test_response': response[:4000],
            })
        except Exception as exc:
            self.write({
                'test_status': 'failed',
                'last_test_date': fields.Datetime.now(),
                'last_test_error': str(exc),
                'last_test_response': False,
            })
            raise
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Provider Test'),
            'res_model': 'elsx.ai.job',
            'res_id': job.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _default_format_for_type(self):
        self.ensure_one()
        if self.provider_type == 'anthropic':
            return 'anthropic_messages'
        if self.provider_type == 'huggingface':
            return 'huggingface_inference'
        if self.provider_type == 'custom':
            return self.request_format or 'custom_json'
        return self.request_format or 'openai_chat'

    def _chat_endpoint(self):
        self.ensure_one()
        base = (self.api_base_url or '').strip().rstrip('/')
        if self.provider_type == 'rules':
            return False
        if not base:
            raise UserError(_("AI provider '%s' needs an API base URL.") % self.name)
        if self._default_format_for_type() == 'huggingface_inference':
            return base
        if self._default_format_for_type() == 'anthropic_messages':
            return base if base.endswith('/messages') else f"{base}/v1/messages"
        if base.endswith('/chat/completions') or base.endswith('/messages'):
            return base
        return f"{base}/chat/completions" if base.endswith('/v1') else f"{base}/v1/chat/completions"

    def _request_headers(self):
        self.ensure_one()
        headers = {'Content-Type': 'application/json'}
        if self.provider_type == 'anthropic':
            if self.api_key:
                headers['x-api-key'] = self.api_key
            headers['anthropic-version'] = '2023-06-01'
        elif self.provider_type == 'huggingface':
            if self.api_key:
                headers['Authorization'] = f"Bearer {self.api_key}"
        elif self.provider_type == 'custom':
            if self.api_key and self.api_key_header:
                value = self.api_key if self.api_key.lower().startswith(('bearer ', 'token ')) else f"Bearer {self.api_key}"
                headers[self.api_key_header] = value
        else:
            if self.api_key:
                headers['Authorization'] = f"Bearer {self.api_key}"
            if self.organization_id:
                headers['OpenAI-Organization'] = self.organization_id
            if self.project_id:
                headers['OpenAI-Project'] = self.project_id
        return headers

    def _extra_payload(self):
        self.ensure_one()
        if not self.request_extra_json:
            return {}
        try:
            extra = json.loads(self.request_extra_json)
        except Exception as exc:
            raise UserError(_("Provider extra request JSON is invalid: %s") % exc)
        if not isinstance(extra, dict):
            raise UserError(_("Provider extra request JSON must be an object."))
        return extra

    def _build_payload(self, job):
        self.ensure_one()
        system_prompt = job.prompt_id.system_prompt or ''
        user_prompt = job.prompt_id.user_prompt or ''
        input_text = job.input_text or ''
        if job.input_payload:
            input_text = "%s\n\nPayload:\n%s" % (input_text, job.input_payload) if input_text else job.input_payload
        final_user_prompt = "\n\n".join(part for part in [user_prompt, input_text] if part).strip() or input_text or "Respond briefly."
        model = self.default_model or self.env['ir.config_parameter'].sudo().get_param('elsx_ai.default_model') or 'default'
        fmt = self._default_format_for_type()
        extra = self._extra_payload()
        if fmt == 'anthropic_messages':
            payload = {
                'model': model,
                'max_tokens': self.max_tokens or 800,
                'temperature': self.temperature,
                'messages': [{'role': 'user', 'content': final_user_prompt}],
            }
            if system_prompt:
                payload['system'] = system_prompt
        elif fmt == 'huggingface_inference':
            payload = {
                'inputs': "\n\n".join(part for part in [system_prompt, final_user_prompt] if part),
                'parameters': {
                    'temperature': self.temperature,
                    'max_new_tokens': self.max_tokens or 800,
                },
            }
        elif fmt == 'custom_json':
            payload = {
                'model': model,
                'system_prompt': system_prompt,
                'prompt': final_user_prompt,
                'input': input_text,
                'job_type': job.job_type,
            }
        else:
            payload = {
                'model': model,
                'temperature': self.temperature,
                'max_tokens': self.max_tokens or 800,
                'messages': [
                    {'role': 'system', 'content': system_prompt or 'You are a careful business assistant. Produce drafts only.'},
                    {'role': 'user', 'content': final_user_prompt},
                ],
            }
        payload.update(extra)
        return payload


class ElsxAiPrompt(models.Model):
    _name = 'elsx.ai.prompt'
    _description = 'ELSX AI Prompt Template'
    _order = 'purpose, name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    purpose = fields.Selection([
        ('whatsapp_reply', 'WhatsApp Draft Reply'),
        ('crm_reply', 'CRM Draft Reply'),
        ('ocr', 'Document OCR'),
        ('classification', 'Classification'),
        ('campaign', 'Campaign Draft'),
        ('custom', 'Custom'),
    ], default='custom', required=True)
    system_prompt = fields.Text()
    user_prompt = fields.Text()
    provider_id = fields.Many2one('elsx.ai.provider')

    _code_unique = models.Constraint(
        'unique(code)',
        'AI prompt code must be unique.',
    )

    @api.model
    def _ensure_default_prompt(self, xmlid_name, values):
        """Create/link default prompts without duplicating live DB rows."""
        module = 'elsx_whatsapp_marketing'
        values = dict(values or {})
        code = values.get('code')
        if not xmlid_name or not code:
            return False

        prompt = self.sudo().search([('code', '=', code)], limit=1)
        if prompt:
            prompt.write(values)
        else:
            prompt = self.sudo().create(values)

        xmlid = self.env['ir.model.data'].sudo().search([
            ('module', '=', module),
            ('name', '=', xmlid_name),
        ], limit=1)
        xmlid_values = {
            'module': module,
            'name': xmlid_name,
            'model': self._name,
            'res_id': prompt.id,
            'noupdate': True,
        }
        if xmlid:
            xmlid.write(xmlid_values)
        else:
            self.env['ir.model.data'].sudo().create(xmlid_values)
        return prompt.id


class ElsxAiJob(models.Model):
    _name = 'elsx.ai.job'
    _description = 'ELSX AI Job'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True)
    provider_id = fields.Many2one('elsx.ai.provider', ondelete='set null')
    prompt_id = fields.Many2one('elsx.ai.prompt', ondelete='set null')
    job_type = fields.Selection([
        ('whatsapp_reply', 'WhatsApp Draft Reply'),
        ('crm_reply', 'CRM Draft Reply'),
        ('ocr', 'Document OCR'),
        ('classification', 'Classification'),
        ('campaign', 'Campaign Draft'),
        ('custom', 'Custom'),
    ], default='custom', required=True, index=True)
    state = fields.Selection([
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('reviewed', 'Reviewed'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    ], default='queued', required=True, index=True)
    origin_model = fields.Char(index=True)
    origin_res_id = fields.Integer(index=True)
    origin_ref = fields.Char(compute='_compute_origin_ref', store=True)
    input_text = fields.Text()
    input_payload = fields.Text()
    response_text = fields.Text(readonly=True)
    response_json = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    attempts = fields.Integer(default=0, readonly=True)
    duration_ms = fields.Float(readonly=True)
    usage_prompt_tokens = fields.Integer(readonly=True)
    usage_completion_tokens = fields.Integer(readonly=True)
    estimated_cost = fields.Float(readonly=True, digits=(16, 6))
    auto_apply = fields.Boolean(default=False)
    log_ids = fields.One2many('elsx.ai.job.log', 'job_id')

    _state_type_idx = models.Index("(state, job_type, create_date)")
    _origin_idx = models.Index("(origin_model, origin_res_id)")

    @api.depends('origin_model', 'origin_res_id')
    def _compute_origin_ref(self):
        for job in self:
            job.origin_ref = f"{job.origin_model},{job.origin_res_id}" if job.origin_model and job.origin_res_id else False

    @api.model
    def create_job(self, job_type, name, origin=False, input_text=False, input_payload=False, prompt_code=False):
        prompt = self.env['elsx.ai.prompt'].search([('code', '=', prompt_code)], limit=1) if prompt_code else self.env['elsx.ai.prompt']
        provider = self.env['elsx.ai.provider']._select_runtime_provider(prompt)
        vals = {
            'name': name,
            'job_type': job_type,
            'provider_id': provider.id if provider else False,
            'prompt_id': prompt.id if prompt else False,
            'input_text': input_text or False,
            'input_payload': json.dumps(input_payload, ensure_ascii=False, indent=2) if isinstance(input_payload, (dict, list)) else (input_payload or False),
        }
        if origin:
            vals.update({'origin_model': origin._name, 'origin_res_id': origin.id})
        return self.create(vals)

    def _log(self, level, message, payload=False):
        self.ensure_one()
        self.env['elsx.ai.job.log'].create({
            'job_id': self.id,
            'level': level,
            'message': message,
            'payload': json.dumps(payload, ensure_ascii=False, indent=2) if isinstance(payload, (dict, list)) else (payload or False),
        })

    def _safe_log_payload(self, payload, max_text=800):
        """Keep AI logs useful without storing huge customer conversations."""
        if isinstance(payload, dict):
            return {key: self._safe_log_payload(value, max_text=max_text) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._safe_log_payload(item, max_text=max_text) for item in payload[:10]]
        if isinstance(payload, str) and len(payload) > max_text:
            return payload[:max_text] + '... [truncated]'
        return payload

    def _rule_based_response(self):
        self.ensure_one()
        text = (self.input_text or '').strip()
        try:
            payload = json.loads(self.input_payload or '{}')
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if self.job_type == 'whatsapp_reply':
            brand_name = (payload.get('brand_name') or 'our team').strip()
            customer_name = (payload.get('customer_name') or 'there').strip()
            latest = (payload.get('latest_inbound') or text or '').lower()
            instructions = (payload.get('reply_instructions') or '').lower()
            signature = (payload.get('reply_signature') or '').strip()
            mention_brand = 'do not mention brand' not in instructions and 'avoid brand' not in instructions
            greeting = f"Hi {customer_name}, "
            if 'no thanks' in instructions or 'do not say thanks' in instructions:
                first_line = f"{greeting}I can help with that."
            elif mention_brand:
                first_line = f"{greeting}thanks for contacting {brand_name}."
            else:
                first_line = f"{greeting}thanks for your message."

            if any(term in latest for term in ('price', 'quote', 'quotation', 'catalog', 'catalogue', 'dealer', 'buy')):
                next_line = "Please share product type, size, load capacity, quantity, and delivery city so our team can guide you accurately."
            elif any(term in latest for term in ('support', 'help', 'issue', 'problem', 'complaint', 'warranty')):
                next_line = "Could you please share the issue details, order/reference number if available, city, and any photos or documents?"
            else:
                next_line = "How can we help you today? Please share your requirement and our team will guide you."

            draft = f"{first_line} {next_line}".strip()
            if signature:
                draft = f"{draft}\n\n{signature}"
            return draft[:4096]
        if self.job_type == 'crm_reply':
            return (
                "Thank you for your enquiry. Based on the conversation, the next step is to confirm requirement, "
                "share catalogue/pricing, and schedule a sales follow-up."
            )
        if self.job_type == 'campaign':
            return (
                "Dear {{name}}, we are sharing FiberaFRP product information for your review. "
                "Reply with Catalogue, Price, or Sales and our team will assist you."
            )
        if self.job_type == 'classification':
            lowered = text.lower()
            sentiment = 'negative' if any(word in lowered for word in ('problem', 'issue', 'delay', 'complaint')) else 'neutral'
            return json.dumps({'sentiment': sentiment, 'intent': 'support' if sentiment == 'negative' else 'general'}, ensure_ascii=False)
        if self.job_type == 'ocr':
            return json.dumps({
                'status': 'needs_review',
                'message': 'OCR approval workflow is ready. Live extraction is disabled until provider validation passes.',
            }, ensure_ascii=False)
        return "AI provider configuration is healthy. Rules Draft Engine responded successfully."

    def _json_path_value(self, payload, path):
        current = payload
        for part in (path or '').split('.'):
            if not part:
                continue
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except Exception:
                    return False
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return False
        return current

    def _extract_provider_text(self, provider, response_json):
        self.ensure_one()
        if provider.response_path:
            value = self._json_path_value(response_json, provider.response_path)
            if value not in (False, None):
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        fmt = provider._default_format_for_type()
        if fmt == 'anthropic_messages':
            content = response_json.get('content') if isinstance(response_json, dict) else False
            if isinstance(content, list):
                texts = [item.get('text') for item in content if isinstance(item, dict) and item.get('text')]
                if texts:
                    return "\n".join(texts)
        if fmt == 'huggingface_inference':
            if isinstance(response_json, list) and response_json:
                first = response_json[0]
                if isinstance(first, dict):
                    return first.get('generated_text') or first.get('summary_text') or json.dumps(first, ensure_ascii=False)
            if isinstance(response_json, dict):
                return response_json.get('generated_text') or response_json.get('summary_text') or response_json.get('text')
        if isinstance(response_json, dict):
            value = self._json_path_value(response_json, 'choices.0.message.content')
            if value:
                return value
            value = self._json_path_value(response_json, 'choices.0.text')
            if value:
                return value
            for key in ('output_text', 'text', 'response', 'message', 'content'):
                if response_json.get(key):
                    return response_json[key] if isinstance(response_json[key], str) else json.dumps(response_json[key], ensure_ascii=False)
        return json.dumps(response_json, ensure_ascii=False)

    def _usage_from_response(self, response_json):
        usage = response_json.get('usage', {}) if isinstance(response_json, dict) else {}
        return {
            'prompt_tokens': int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0),
            'completion_tokens': int(usage.get('completion_tokens') or usage.get('output_tokens') or 0),
        }

    def _execute_provider(self, provider):
        self.ensure_one()
        if provider.provider_type == 'rules':
            return self._rule_based_response(), False, {}

        endpoint = provider._chat_endpoint()
        payload = provider._build_payload(self)
        headers = provider._request_headers()
        last_error = False
        attempts = max(1, (provider.max_retries or 0) + 1)
        for attempt in range(attempts):
            try:
                safe_payload = self._safe_log_payload(payload)
                self._log('debug', 'AI provider request prepared.', {
                    'provider': provider.name,
                    'endpoint': endpoint,
                    'request_format': provider._default_format_for_type(),
                    'attempt': attempt + 1,
                    'payload': safe_payload,
                })
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=max(1, provider.timeout_seconds or 30),
                )
                raw_text = response.text or ''
                if response.status_code >= 400:
                    raise UserError(_("AI provider returned HTTP %s: %s") % (response.status_code, raw_text[:500]))
                try:
                    response_json = response.json()
                except Exception:
                    response_json = {'text': raw_text}
                extracted = self._extract_provider_text(provider, response_json) or raw_text
                usage = self._usage_from_response(response_json)
                self._log('info', 'AI provider response received.', {
                    'status_code': response.status_code,
                    'response_preview': raw_text[:1000],
                })
                return extracted, response_json, usage
            except Exception as exc:
                last_error = exc
                self._log('warning', 'AI provider attempt failed: %s' % exc, {'attempt': attempt + 1})
                if attempt + 1 >= attempts:
                    raise
                time.sleep(min(2, attempt + 1))
        raise last_error or UserError(_("AI provider request failed."))

    def action_run(self):
        for job in self:
            if not self.env.context.get('bypass_ai_enabled') and not self.env['elsx.ai.provider']._ai_enabled():
                job.write({
                    'state': 'failed',
                    'error_message': 'AI is disabled in Settings. Enable ELSX AI only after provider configuration is tested.',
                })
                job._log('warning', job.error_message)
                raise UserError(_(job.error_message))

            provider = job.provider_id or self.env['elsx.ai.provider']._get_default_provider()
            if not provider:
                job.write({'state': 'failed', 'error_message': 'No active AI provider is configured.'})
                job._log('error', job.error_message)
                raise UserError(_(job.error_message))

            start = time.monotonic()
            job.write({
                'provider_id': provider.id,
                'state': 'running',
                'attempts': job.attempts + 1,
                'error_message': False,
            })
            try:
                response, response_json, usage = job._execute_provider(provider)
                parsed = False
                if response_json:
                    parsed = response_json
                elif response and response[:1] in ('{', '['):
                    try:
                        parsed = json.loads(response)
                    except Exception:
                        parsed = False
                prompt_tokens = usage.get('prompt_tokens') if usage else 0
                completion_tokens = usage.get('completion_tokens') if usage else 0
                estimated_cost = (
                    (prompt_tokens / 1000.0) * (provider.cost_input_per_1k or 0.0)
                    + (completion_tokens / 1000.0) * (provider.cost_output_per_1k or 0.0)
                )
                vals = {
                    'state': 'done',
                    'response_text': response or False,
                    'response_json': json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else False,
                    'duration_ms': round((time.monotonic() - start) * 1000, 2),
                    'usage_prompt_tokens': prompt_tokens,
                    'usage_completion_tokens': completion_tokens,
                    'estimated_cost': estimated_cost,
                }
                job.write(vals)
                job._log('info', 'AI job completed. Output is draft-only until a user applies it.')
            except Exception as exc:
                job.write({
                    'state': 'failed',
                    'error_message': str(exc),
                    'duration_ms': round((time.monotonic() - start) * 1000, 2),
                })
                job._log('error', str(exc))
                _logger.exception("AI job %s failed", job.id)
        return True

    def action_mark_reviewed(self):
        self.write({'state': 'reviewed'})
        return True

    def action_apply_to_origin(self):
        for job in self:
            if job.auto_apply and not self.env['elsx.ai.provider']._auto_write_enabled():
                raise UserError(_("AI auto-write is disabled. Review the output and apply manually."))
            if not job.origin_model or not job.origin_res_id:
                raise UserError(_("This AI job is not linked to a business record."))
            record = self.env[job.origin_model].browse(job.origin_res_id)
            if not record.exists():
                raise UserError(_("The linked business record no longer exists."))
            if job.job_type == 'whatsapp_reply' and record._name == 'whatsapp.chat':
                record.write({
                    'ai_suggested_reply': job.response_text or job.response_json or '',
                    'quick_reply_text': job.response_text or job.response_json or '',
                })
            elif job.job_type == 'campaign' and record._name == 'whatsapp.campaign':
                record.write({'message_body': job.response_text or ''})
            else:
                raise UserError(_("No safe apply handler exists for this AI job type."))
            job.write({'state': 'applied'})
            job._log('info', 'AI output applied to origin by user %s.' % self.env.user.display_name)
        return True


class ElsxAiJobLog(models.Model):
    _name = 'elsx.ai.job.log'
    _description = 'ELSX AI Job Log'
    _order = 'create_date desc, id desc'

    job_id = fields.Many2one('elsx.ai.job', required=True, ondelete='cascade')
    level = fields.Selection([
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], default='info', required=True)
    message = fields.Text(required=True)
    payload = fields.Text()


class ElsxAiTool(models.Model):
    _name = 'elsx.ai.tool'
    _description = 'ELSX AI Tool Definition'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=False)
    description = fields.Text()
    schema_json = fields.Text(
        help="JSON schema for future provider tool/function calling. Disabled by default."
    )
    allow_auto_execute = fields.Boolean(
        default=False,
        help="Reserved for future use. WhatsApp customer sends remain disabled unless explicitly approved."
    )

    _code_unique = models.Constraint(
        'unique(code)',
        'AI tool code must be unique.',
    )
