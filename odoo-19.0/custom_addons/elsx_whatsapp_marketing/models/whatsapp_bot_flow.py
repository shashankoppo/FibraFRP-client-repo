# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import json
import requests
import time
import re
from datetime import timedelta

_logger = logging.getLogger(__name__)

CANVAS_ACTION_MAP = {
    'trigger': False,
    'message': 'send_text',
    'action': 'transfer',
    'wait_reply': 'wait_response',
    'ask_question': 'ask_question',
    'assign_agent': 'transfer',
    'assign_team': 'assign_team',
    'create_lead': 'create_lead',
    'add_tag': 'assign_tag',
    'chat_status': 'chat_status',
    'update_contact': 'update_contact',
    'api_call': 'http_request',
    'set_variable': 'set_variable',
    'send_list': 'send_list',
    'send_cta_url': 'send_cta_url',
    'send_catalog': 'send_catalog',
    'send_form_link': 'send_form_link',
    'send_payment_link': 'send_payment_link',
    'end': 'end',
}

MESSAGE_NODE_ACTIONS = {
    'text': 'send_text',
    'template': 'send_template',
    'buttons': 'send_buttons',
    'list': 'send_list',
    'media': 'send_media',
}

ACTION_NODE_ACTIONS = {
    'assign_agent': 'transfer',
    'add_label': 'assign_tag',
    'add_tag': 'assign_tag',
    'create_lead': 'create_lead',
    'api_call': 'http_request',
    'delay': 'delay',
    'wait_reply': 'wait_response',
    'ask_question': 'ask_question',
    'set_variable': 'set_variable',
    'assign_team': 'assign_team',
    'chat_status': 'chat_status',
    'update_contact': 'update_contact',
    'send_catalog': 'send_catalog',
    'send_cta_url': 'send_cta_url',
    'send_form_link': 'send_form_link',
    'send_payment_link': 'send_payment_link',
    'end': 'end',
}

LEGACY_NODE_CATEGORIES = {
    'trigger': 'trigger',
    'condition': 'condition',
    'send_text': 'message',
    'send_template': 'message',
    'send_buttons': 'message',
    'send_list': 'message',
    'send_media': 'message',
    'wait_reply': 'action',
    'ask_question': 'action',
    'assign_agent': 'action',
    'assign_team': 'action',
    'create_lead': 'action',
    'add_tag': 'action',
    'chat_status': 'action',
    'update_contact': 'action',
    'delay': 'action',
    'api_call': 'action',
    'set_variable': 'action',
    'send_catalog': 'action',
    'send_cta_url': 'action',
    'send_form_link': 'action',
    'send_payment_link': 'action',
    'end': 'action',
}


def _json_loads(value, default=None):
    """Small defensive JSON helper used by the visual builder models."""
    if default is None:
        default = {}
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except Exception:
        return default
    return parsed if parsed is not None else default


def _json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _step_to_node_data(step):
    action_type = step.action_type
    node_type = 'message'
    subtype = 'text'
    config = {}

    if action_type == 'send_text':
        node_type = 'message'
        subtype = 'text'
        config = {'message_mode': 'text', 'message_text': step.message_text}
    elif action_type == 'send_template':
        node_type = 'message'
        subtype = 'template'
        config = {'message_mode': 'template', 'template_id': step.template_id.id if step.template_id else False}
    elif action_type == 'send_media':
        node_type = 'message'
        subtype = 'media'
        config = {'message_mode': 'media', 'media_id': step.media_id.id if step.media_id else False, 'message_text': step.message_text}
    elif action_type == 'send_buttons':
        node_type = 'message'
        subtype = 'buttons'
        config = {
            'message_mode': 'buttons',
            'message_text': step.message_text,
            'button_header_text': step.button_header_text,
            'button_footer_text': step.button_footer_text,
            'save_response': step.save_response,
            'response_variable': step.response_variable or '',
            'options': [{
                'id': button.button_id,
                'title': button.name,
                'description': button.description,
                'button_action': button.button_action,
                'url': button.url,
                'catalog_id': button.catalog_id,
                'product_retailer_id': button.product_retailer_id,
                'next_step_id': button.next_step_id.id if button.next_step_id else False,
            } for button in step.button_ids],
        }
    elif action_type == 'send_list':
        node_type = 'message'
        subtype = 'list'
        config = {
            'message_mode': 'list',
            'message_text': step.message_text,
            'button_header_text': step.button_header_text,
            'button_footer_text': step.button_footer_text,
            'list_button_text': step.list_button_text,
            'list_section_title': step.list_section_title,
            'save_response': step.save_response,
            'response_variable': step.response_variable or '',
            'options': [{
                'id': button.button_id,
                'title': button.name,
                'description': button.description,
                'button_action': button.button_action,
                'url': button.url,
                'catalog_id': button.catalog_id,
                'product_retailer_id': button.product_retailer_id,
                'next_step_id': button.next_step_id.id if button.next_step_id else False,
            } for button in step.button_ids],
        }
    elif action_type == 'send_cta_url':
        node_type = 'action'
        subtype = 'send_cta_url'
        config = {
            'action_kind': 'send_cta_url',
            'message_text': step.message_text,
            'button_header_text': step.button_header_text,
            'button_footer_text': step.button_footer_text,
            'cta_button_text': step.cta_button_text or '',
            'cta_button_url': step.cta_button_url or '',
        }
    elif action_type == 'send_form_link':
        node_type = 'action'
        subtype = 'send_form_link'
        config = {
            'action_kind': 'send_form_link',
            'message_text': step.message_text,
            'form_id': step.form_id.id if step.form_id else False,
        }
    elif action_type == 'send_payment_link':
        node_type = 'action'
        subtype = 'send_payment_link'
        config = {
            'action_kind': 'send_payment_link',
            'message_text': step.message_text,
            'payment_mode': step.payment_mode or 'account_default',
        }
    elif action_type == 'wait_response':
        node_type = 'action'
        subtype = 'wait_reply'
        config = {'action_kind': 'wait_reply', 'save_response': step.save_response, 'response_variable': step.response_variable or step.variable_name or ''}
    elif action_type == 'ask_question':
        node_type = 'action'
        subtype = 'ask_question'
        config = {
            'action_kind': 'ask_question',
            'message_text': step.message_text,
            'input_validation_type': step.input_validation_type or 'text',
            'response_variable': step.response_variable or '',
            'timeout_minutes': step.timeout_minutes or 0,
            'max_attempts': step.max_attempts or 1,
            'invalid_message': step.invalid_message or '',
        }
    elif action_type == 'condition':
        node_type = 'condition'
        subtype = 'if_else'
        config = {
            'condition_type': step.condition_type or 'keyword_match',
            'condition_operator': step.condition_operator or 'contains',
            'condition_source': step.condition_source or 'last_reply',
            'condition_variable': step.condition_variable or '',
            'condition_value': step.condition_value or '',
        }
    elif action_type == 'transfer':
        node_type = 'action'
        subtype = 'assign_agent'
        config = {'action_kind': 'assign_agent', 'assign_user_id': step.assign_user_id.id if step.assign_user_id else False}
    elif action_type == 'assign_team':
        node_type = 'action'
        subtype = 'assign_team'
        config = {
            'action_kind': 'assign_team',
            'assign_team_member_ids': step.assign_team_member_ids.ids,
        }
    elif action_type == 'create_lead':
        node_type = 'action'
        subtype = 'create_lead'
        config = {'action_kind': 'create_lead', 'message_text': step.message_text}
    elif action_type == 'assign_tag':
        node_type = 'action'
        subtype = 'add_label'
        config = {'action_kind': 'add_label', 'assign_tag_id': step.assign_tag_id.id if step.assign_tag_id else False}
    elif action_type == 'chat_status':
        node_type = 'action'
        subtype = 'chat_status'
        config = {'action_kind': 'chat_status', 'chat_status': step.chat_status or 'open'}
    elif action_type == 'update_contact':
        node_type = 'action'
        subtype = 'update_contact'
        config = {
            'action_kind': 'update_contact',
            'contact_attribute_name': step.contact_attribute_name or '',
            'contact_attribute_value': step.contact_attribute_value or '',
        }
    elif action_type == 'http_request':
        node_type = 'action'
        subtype = 'api_call'
        config = {
            'action_kind': 'api_call',
            'http_method': step.http_method or 'POST',
            'http_url': step.http_url or '',
            'http_payload': step.http_payload or '',
            'http_headers': step.http_headers or '',
            'http_query_params': step.http_query_params or '',
            'http_auth_type': step.http_auth_type or 'none',
            'http_auth_token': step.http_auth_token or '',
            'http_username': step.http_username or '',
            'http_password': step.http_password or '',
            'response_variable': step.response_variable or '',
            'http_response_path': step.http_response_path or '',
        }
    elif action_type == 'set_variable':
        node_type = 'action'
        subtype = 'set_variable'
        config = {
            'action_kind': 'set_variable',
            'variable_name': step.variable_name or '',
            'variable_value': step.variable_value or '',
        }
    elif action_type == 'delay':
        node_type = 'action'
        subtype = 'delay'
        config = {'action_kind': 'delay', 'delay_seconds': step.delay_seconds or 0}
    elif action_type == 'send_catalog':
        node_type = 'action'
        subtype = 'send_catalog'
        config = {
            'action_kind': 'send_catalog',
            'message_text': step.message_text,
            'catalog_message_type': step.catalog_message_type or 'single_product',
            'catalog_id': step.catalog_id or '',
            'product_retailer_id': step.product_retailer_id or '',
            'product_retailer_ids': step.product_retailer_ids or '',
            'thumbnail_product_retailer_id': step.thumbnail_product_retailer_id or '',
            'catalog_section_title': step.catalog_section_title or '',
            'button_footer_text': step.button_footer_text or '',
            'button_header_text': step.button_header_text or '',
        }
    elif action_type == 'end':
        node_type = 'action'
        subtype = 'end'
        config = {'action_kind': 'end'}

    return node_type, subtype, config


class WhatsAppBotFlow(models.Model):
    """Advanced WhatsApp Chatbot Flows with multi-step automation"""
    _name = 'whatsapp.bot.flow'
    _description = 'WhatsApp Bot Flow/Automation Sequence'
    _rec_name = 'name'

    name = fields.Char('Flow Name', required=True, help='Internal name used to identify this automation flow.')
    account_id = fields.Many2one(
        'whatsapp.account',
        string='WhatsApp Account',
        required=True,
        ondelete='cascade',
        help='WhatsApp Business account used to send messages from this flow.',
    )
    description = fields.Text('Description', help='Notes for admins about what this flow is meant to do.')
    
    # Flow type
    flow_type = fields.Selection([
        ('greeting', 'Greeting/Welcome'),
        ('support', 'Customer Support'),
        ('sales', 'Sales Funnel'),
        ('survey', 'Survey/Feedback'),
        ('verification', 'Verification/OTP'),
        ('notification', 'Notification'),
        ('custom', 'Custom Flow'),
    ], default='custom', required=True, help='Business purpose of this flow. Used for organization and filtering.')
    
    # Trigger configuration
    trigger_type = fields.Selection([
        ('keyword', 'Keyword Match'),
        ('first_message', 'First Message'),
        ('manual', 'Manual Trigger'),
        ('schedule', 'Scheduled'),
        ('webhook', 'Webhook Event'),
    ], string='Trigger', default='keyword', help='Event that starts this flow.')
    
    keywords = fields.Char('Keywords', help='Comma-separated keywords to trigger this flow')
    webhook_event = fields.Char('Webhook Event', help='Internal webhook event name that should start this flow.')
    schedule_pattern = fields.Char('Schedule Pattern', help='Cron expression used when Trigger is Scheduled.')
    
    # Flow settings
    active = fields.Boolean('Active', default=True, help='Inactive flows are ignored by automatic trigger matching.')
    priority = fields.Integer('Priority', default=10, help='Higher priority flows execute first')
    retry_on_failure = fields.Boolean('Retry on Failure', default=True, help='Retry this flow when a step fails and retry attempts remain.')
    max_retries = fields.Integer('Max Retries', default=3, help='Maximum retry attempts for failed executions.')
    
    # Steps in this flow
    step_ids = fields.One2many(
        'whatsapp.bot.flow.step',
        'flow_id',
        string='Flow Steps',
        help='Executable steps generated from the visual canvas or configured directly.',
    )
    
    # Statistics
    trigger_count = fields.Integer('Times Triggered', readonly=True, default=0)
    success_count = fields.Integer('Successful Executions', readonly=True, default=0)
    failed_count = fields.Integer('Failed Executions', readonly=True, default=0)
    ai_flow_review = fields.Text('AI Flow Review', readonly=True)
    ai_flow_prompt = fields.Text(
        'AI Flow Draft Prompt',
        help='Describe the bot you want. AI creates an inactive draft flow only; admins must review and activate it.',
    )
    ai_generated_from_flow_id = fields.Many2one('whatsapp.bot.flow', string='Generated From Flow', readonly=True)
    ai_draft_job_id = fields.Many2one('elsx.ai.job', string='Last AI Draft Job', readonly=True)
    flow_health_warnings = fields.Text('Flow Health Warnings', compute='_compute_flow_health_warnings')
    
    # Visual Flow Builder data (JSON: node positions, connections)
    canvas_data = fields.Text('Canvas Layout', default='{}',
                              help='JSON data storing the visual flow builder layout')
    node_ids = fields.One2many('whatsapp.bot.node', 'flow_id', string='Visual Nodes')
    edge_ids = fields.One2many('whatsapp.bot.edge', 'flow_id', string='Visual Edges')
    graph_version = fields.Integer('Graph Version', default=1, readonly=True)
    
    # Execution log
    log_ids = fields.One2many('whatsapp.bot.flow.log', 'flow_id', string='Execution Logs', readonly=True)
    step_count = fields.Integer('Steps', compute='_compute_flow_counts')
    button_count = fields.Integer('Buttons', compute='_compute_flow_counts')

    def _compute_flow_counts(self):
        for flow in self:
            steps = flow.step_ids
            flow.step_count = len(steps)
            flow.button_count = len(steps.mapped('button_ids'))

    @api.depends(
        'canvas_data', 'step_ids.node_id', 'step_ids.next_step_id',
        'step_ids.button_ids.next_step_id', 'step_ids.button_ids.button_action',
        'step_ids.fallback_step_id', 'step_ids.form_id', 'step_ids.payment_mode',
        'step_ids.catalog_message_type', 'step_ids.catalog_id',
        'step_ids.product_retailer_id', 'step_ids.product_retailer_ids',
        'step_ids.thumbnail_product_retailer_id', 'account_id.default_form_id',
        'account_id.payment_link_mode', 'account_id.payment_manual_url',
        'account_id.commerce_catalog_id', 'account_id.commerce_default_product_retailer_id',
        'log_ids.status', 'log_ids.started_date',
    )
    def _compute_flow_health_warnings(self):
        for flow in self:
            flow.flow_health_warnings = "\n".join(flow._get_flow_health_warnings())

    def _get_flow_health_warnings(self):
        self.ensure_one()
        warnings = []

        stale_before = fields.Datetime.now() - timedelta(hours=24)
        stale_pending = self.log_ids.filtered(
            lambda log: log.status == 'pending' and log.started_date and log.started_date < stale_before
        )
        if stale_pending:
            warnings.append(f"{len(stale_pending)} pending execution log(s) are older than 24 hours and can block fresh triggers.")

        try:
            raw_graph = json.loads(self.canvas_data or '{}')
        except Exception:
            raw_graph = {}
            if self.canvas_data:
                warnings.append("Canvas JSON is invalid and should be rebuilt from the step list.")

        raw_edges = raw_graph.get('edges')
        if not isinstance(raw_edges, list):
            raw_edges = raw_graph.get('connections') if isinstance(raw_graph.get('connections'), list) else []
        for edge in raw_edges or []:
            if not isinstance(edge, dict):
                continue
            source = edge.get('from') or edge.get('source') or edge.get('source_node_id')
            target = edge.get('to') or edge.get('target') or edge.get('target_node_id')
            if source and target and str(source) == str(target):
                warnings.append(f"Canvas has a self-loop on node {source}.")

        graph = self._normalize_graph_payload(raw_graph)
        nodes = graph.get('nodes') or []
        edges = graph.get('edges') or []
        node_ids = {node.get('id') for node in nodes if isinstance(node, dict)}
        trigger_ids = [
            node.get('id') for node in nodes
            if isinstance(node, dict) and node.get('type') == 'trigger'
        ]
        outgoing = {}
        for edge in edges:
            outgoing.setdefault(edge.get('from'), []).append(edge.get('to'))
        reachable = set(trigger_ids)
        queue = list(trigger_ids)
        while queue:
            current = queue.pop(0)
            for target in outgoing.get(current, []):
                if target and target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        disconnected = [
            node.get('label') or node.get('id')
            for node in nodes
            if isinstance(node, dict)
            and node.get('type') != 'trigger'
            and node.get('id') in node_ids
            and node.get('id') not in reachable
        ]
        if disconnected:
            warnings.append("Disconnected executable node(s): %s." % ", ".join(disconnected[:5]))

        known_node_ids = {node.get('id') for node in nodes if isinstance(node, dict)}
        for step in self.step_ids:
            if step.next_step_id == step:
                warnings.append(f'Step "{step.name}" routes to itself.')
            if step.node_id and known_node_ids and step.node_id not in known_node_ids:
                warnings.append(f'Step "{step.name}" points to missing canvas node {step.node_id}.')
            if step.action_type == 'send_template' and not step.template_id:
                warnings.append(f'Step "{step.name}" needs an approved template.')
            if step.action_type == 'send_media' and not step.media_id:
                warnings.append(f'Step "{step.name}" needs a media record.')
            if step.action_type == 'ask_question':
                if not (step.message_text or '').strip():
                    warnings.append(f'Step "{step.name}" needs a question/prompt.')
                if not step.response_variable:
                    warnings.append(f'Step "{step.name}" needs a response variable.')
                if step.max_attempts <= 0:
                    warnings.append(f'Step "{step.name}" needs max attempts of at least 1.')
                if step.timeout_minutes < 0:
                    warnings.append(f'Step "{step.name}" has a negative timeout.')
            if step.action_type == 'condition':
                if not step.condition_type:
                    warnings.append(f'Step "{step.name}" needs a condition type.')
                if not step.condition_true_step and not step.condition_false_step and not step.condition_branch_ids:
                    warnings.append(f'Step "{step.name}" needs at least one condition route.')
            if step.action_type == 'http_request' and not step.http_url:
                warnings.append(f'Step "{step.name}" needs a request URL.')
            if step.action_type == 'send_cta_url':
                if not (step.cta_button_text or '').strip():
                    warnings.append(f'Step "{step.name}" needs URL button text.')
                url = (step.cta_button_url or step.account_id.commerce_shop_url or '').strip()
                if not url:
                    warnings.append(f'Step "{step.name}" needs a URL button link or account Shop / Catalogue URL.')
                elif not url.startswith(('http://', 'https://')):
                    warnings.append(f'Step "{step.name}" has an invalid URL button link.')
            if step.action_type in ('send_buttons', 'send_list'):
                if not step.button_ids:
                    warnings.append(f'Step "{step.name}" has no option rows.')
                special_buttons = step.button_ids.filtered(lambda btn: btn.button_action in ('url', 'catalog_product'))
                if step.action_type == 'send_buttons' and special_buttons and len(step.button_ids) > 1:
                    warnings.append(f'Step "{step.name}" mixes URL/product buttons with reply buttons.')
                unrouted = step.button_ids.filtered(
                    lambda btn: btn.button_action == 'reply' and not btn.next_step_id and not step.fallback_step_id
                )
                if unrouted:
                    warnings.append(f'Step "{step.name}" has reply option(s) without routes or fallback.')
                for button in step.button_ids:
                    label_limit = 24 if step.action_type == 'send_list' else 20
                    if button.name and len(button.name) > label_limit:
                        warnings.append(f'Button "{button.name}" exceeds the WhatsApp label limit.')
                    if button.button_action == 'url':
                        if not button.url:
                            warnings.append(f'Button "{button.name}" needs a URL.')
                        elif not button.url.startswith(('http://', 'https://')):
                            warnings.append(f'Button "{button.name}" has an invalid URL.')
                    if button.button_action == 'catalog_product':
                        if not button.product_retailer_id:
                            warnings.append(f'Button "{button.name}" needs a Product Retailer ID.')
                        if not (button.catalog_id or step.account_id.commerce_catalog_id):
                            warnings.append(f'Button "{button.name}" needs a Catalog ID or account default Meta Catalog ID.')
            if step.action_type == 'send_form_link' and not step.form_id and not step.account_id.default_form_id:
                warnings.append(f'Step "{step.name}" needs a form or an account default form.')
            if step.action_type == 'send_payment_link':
                if step.account_id.payment_link_mode == 'disabled':
                    warnings.append(f'Step "{step.name}" needs payment links enabled on the WhatsApp account.')
                elif (
                    (step.payment_mode == 'manual_url' or step.account_id.payment_link_mode == 'manual_url')
                    and not step.account_id.payment_manual_url
                ):
                    warnings.append(f'Step "{step.name}" needs a manual payment URL on the WhatsApp account.')
            if step.action_type == 'send_catalog':
                catalog_id = (step.catalog_id or step.account_id.commerce_catalog_id or '').strip()
                product_id = (
                    step.product_retailer_id
                    or step.thumbnail_product_retailer_id
                    or step.account_id.commerce_default_product_retailer_id
                    or ''
                ).strip()
                if step.catalog_message_type == 'single_product' and (not catalog_id or not product_id):
                    warnings.append(f'Step "{step.name}" needs Catalog ID and Product Retailer ID.')
                if step.catalog_message_type == 'multi_product' and (
                    not catalog_id or not (step.product_retailer_ids or step.product_retailer_id or '').strip()
                ):
                    warnings.append(f'Step "{step.name}" needs Catalog ID and product rows for the product list.')
            if step.action_type == 'delay':
                if step.delay_seconds < 0:
                    warnings.append(f'Step "{step.name}" has a negative delay.')
                if step.delay_seconds > 86400:
                    warnings.append(f'Step "{step.name}" has a delay longer than 24 hours.')

        return warnings

    def _flow_placeholder_values(self, partner=False, message=False, variables=None, sample=False):
        variables = variables if isinstance(variables, dict) else {}
        name = ''
        phone = ''
        email = ''
        company = ''
        last_message = ''

        if sample:
            name = 'Customer Name'
            phone = '919999999999'
            email = 'customer@example.com'
            company = 'Customer Company'
            last_message = 'Customer reply'
        if partner:
            name = partner.display_name or partner.name or name
            phone = (
                getattr(partner, 'mobile', False)
                or getattr(partner, 'phone', False)
                or phone
            )
            email = getattr(partner, 'email', False) or email
            company = partner.commercial_company_name or partner.parent_id.display_name or company
        if message:
            phone = message.phone_number or phone
            last_message = message.body or last_message

        values = {
            'name': name,
            'partner_name': name,
            'customer_name': name,
            'phone': phone,
            'phone_number': phone,
            'mobile': phone,
            'email': email,
            'company': company,
            'company_name': company,
            'last_message': last_message,
            'last_reply': variables.get('last_reply') or last_message,
        }
        for key, value in variables.items():
            if key:
                values[str(key)] = value
        return values

    def _render_flow_text(self, text, partner=False, message=False, variables=None, sample=False):
        if not text:
            return ''
        values = self._flow_placeholder_values(
            partner=partner,
            message=message,
            variables=variables,
            sample=sample,
        )

        def replace(match):
            key = match.group(1).strip()
            value = values.get(key)
            if value in (False, None):
                return ''
            return str(value)

        return re.sub(r'\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}', replace, str(text))
    
    @api.model_create_multi
    def create(self, vals_list):
        """Create flow with default first step"""
        records = super().create(vals_list)
        for record in records:
            if not record.step_ids and not self.env.context.get('skip_canvas_sync'):
                self.env['whatsapp.bot.flow.step'].create({
                    'flow_id': record.id,
                    'step_number': 1,
                    'action_type': 'send_text',
                    'name': 'Welcome Message',
                })
            if record.canvas_data:
                record._sync_node_edge_records_from_canvas()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'canvas_data' in vals and not self.env.context.get('skip_canvas_sync'):
            for record in self:
                record._sync_canvas_to_steps()
                record._sync_node_edge_records_from_canvas()
        if vals.get('active') is True and not self.env.context.get('skip_flow_activation_health_check'):
            for record in self:
                record._raise_if_flow_has_activation_warnings()
        return res

    def _raise_if_flow_has_activation_warnings(self):
        self.ensure_one()
        warnings = self._get_flow_health_warnings()
        blocking = [
            warning for warning in warnings
            if any(term in warning.lower() for term in (
                'self-loop',
                'routes to itself',
                'missing',
                'needs',
                'no option rows',
                'without routes',
                'invalid',
                'disabled',
                'exceeds',
                'negative',
                'longer than',
            ))
        ]
        if blocking:
            raise UserError(_(
                "Flow '%(flow)s' is not ready to activate.\n\nFix these items first:\n- %(items)s"
            ) % {
                'flow': self.display_name,
                'items': "\n- ".join(blocking[:12]),
            })
        return True

    def action_validate_for_activation(self):
        for flow in self:
            flow._raise_if_flow_has_activation_warnings()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Flow Ready'),
                'message': _('No blocking flow health issue was found. You can test and activate this flow.'),
                'type': 'success',
            },
        }

    def action_archive_record(self):
        self.write({'active': False})
        return True

    def action_unarchive_record(self):
        self.write({'active': True})
        return True

    def unlink(self):
        if (
            self.env.context.get('force_unlink_flow')
            or self.env.context.get('hard_delete_flow')
            or self.env.context.get('module_uninstall')
            or self.env.context.get('uninstall_mode')
        ):
            return super().unlink()
        self.write({'active': False})
        _logger.info("Archived %s WhatsApp bot flow(s) instead of hard deleting.", len(self))
        return True

    @api.model
    def action_restore_default_flow_blueprints(self):
        account = self.env['whatsapp.account'].sudo()._get_default_account()
        if not account:
            raise UserError(_("Create or select a WhatsApp account before restoring default flows."))

        Flow = self.with_context(
            active_test=False,
            whatsapp_seed_account_id=account.id,
            restore_defaults_inactive=True,
        ).sudo()
        assistant = Flow._seed_fiberafrp_assistant_flow()
        advanced = Flow._seed_fiberafrp_advanced_business_flows()
        restored = advanced
        if assistant:
            restored |= assistant

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Default Flows Ready'),
                'message': _('%s FiberaFRP default flow(s) are available as inactive drafts for review.') % len(restored),
                'type': 'success',
            },
        }

    def action_open_visual_builder(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'elsx_whatsapp_flow_builder',
            'name': f'Visual Flow Builder: {self.name}',
            'target': 'current',
            'params': {
                'flow_id': self.id,
                'flow_name': self.name,
            },
        }

    def action_view_steps(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Steps: {self.name}',
            'res_model': 'whatsapp.bot.flow.step',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('flow_id', '=', self.id)],
            'context': {
                'default_flow_id': self.id,
                'search_default_flow_id': self.id,
            },
            'target': 'current',
        }

    def action_view_buttons(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Buttons: {self.name}',
            'res_model': 'whatsapp.bot.flow.button',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('flow_id', '=', self.id)],
            'context': {
                'default_flow_id': self.id,
                'search_default_flow_id': self.id,
            },
            'target': 'current',
        }

    def _normalize_node_category(self, node):
        node_type = node.get('type') or node.get('node_type') or 'message'
        if node_type in ('trigger', 'message', 'condition', 'action'):
            return node_type
        return LEGACY_NODE_CATEGORIES.get(node_type, 'message')

    def _normalize_graph_payload(self, graph):
        graph = graph if isinstance(graph, dict) else {}
        raw_nodes = graph.get('nodes') if isinstance(graph.get('nodes'), list) else []
        raw_edges = graph.get('edges')
        if not isinstance(raw_edges, list):
            raw_edges = graph.get('connections') if isinstance(graph.get('connections'), list) else []

        nodes = []
        seen_node_ids = set()
        for index, raw_node in enumerate(raw_nodes, start=1):
            if not isinstance(raw_node, dict):
                continue
            node_key = str(raw_node.get('id') or raw_node.get('node_key') or f'node_{index}')
            if node_key in seen_node_ids:
                continue
            seen_node_ids.add(node_key)

            config = raw_node.get('config') if isinstance(raw_node.get('config'), dict) else {}
            category = self._normalize_node_category(raw_node)
            legacy_type = raw_node.get('type') or raw_node.get('node_type') or category
            subtype = raw_node.get('subtype') or raw_node.get('node_subtype') or config.get('subtype') or legacy_type
            nodes.append({
                'id': node_key,
                'type': category,
                'subtype': subtype,
                'legacy_type': legacy_type,
                'label': raw_node.get('label') or raw_node.get('name') or category.title(),
                'x': float(raw_node.get('x') or 0),
                'y': float(raw_node.get('y') or 0),
                'config': config,
            })

        node_ids = {node['id'] for node in nodes}
        edges = []
        seen_edges = set()
        for index, raw_edge in enumerate(raw_edges, start=1):
            if not isinstance(raw_edge, dict):
                continue
            source = raw_edge.get('from') or raw_edge.get('source') or raw_edge.get('source_node_id')
            target = raw_edge.get('to') or raw_edge.get('target') or raw_edge.get('target_node_id')
            source = str(source) if source else ''
            target = str(target) if target else ''
            if not source or not target or source == target or source not in node_ids or target not in node_ids:
                continue
            edge_key = str(raw_edge.get('id') or raw_edge.get('edge_key') or f'{source}--{target}--{index}')
            duplicate_key = (source, target, raw_edge.get('label') or raw_edge.get('condition') or '')
            if duplicate_key in seen_edges:
                continue
            seen_edges.add(duplicate_key)
            config = raw_edge.get('config') if isinstance(raw_edge.get('config'), dict) else {}
            edges.append({
                'id': edge_key,
                'from': source,
                'to': target,
                'label': raw_edge.get('label') or raw_edge.get('condition') or '',
                'config': config,
            })

        next_id = graph.get('nextId') or graph.get('next_id') or (len(nodes) + 1)
        return {
            'nodes': nodes,
            'edges': edges,
            'connections': [{'from': edge['from'], 'to': edge['to'], 'label': edge.get('label', '')} for edge in edges],
            'nextId': next_id,
            'viewport': graph.get('viewport') if isinstance(graph.get('viewport'), dict) else {},
        }

    def _graph_has_step_nodes(self, graph):
        nodes = graph.get('nodes') if isinstance(graph, dict) else []
        return any(
            isinstance(node, dict) and self._normalize_node_category(node) != 'trigger'
            for node in (nodes or [])
        )

    def _sync_node_edge_records_from_canvas(self):
        for flow in self:
            graph = flow._normalize_graph_payload(_json_loads(flow.canvas_data, {}))
            existing_nodes = {node.node_key: node for node in flow.node_ids}
            kept_node_ids = []

            for sequence, node_data in enumerate(graph['nodes'], start=1):
                vals = {
                    'flow_id': flow.id,
                    'node_key': node_data['id'],
                    'name': node_data['label'],
                    'node_type': node_data['type'],
                    'node_subtype': node_data.get('subtype') or node_data['type'],
                    'legacy_type': node_data.get('legacy_type') or node_data['type'],
                    'x_position': node_data['x'],
                    'y_position': node_data['y'],
                    'sequence': sequence,
                    'config_json': _json_dumps(node_data.get('config')),
                }
                node = existing_nodes.get(node_data['id'])
                if node:
                    node.write(vals)
                else:
                    node = self.env['whatsapp.bot.node'].create(vals)
                kept_node_ids.append(node.id)

            stale_nodes = flow.node_ids.filtered(lambda node: node.id not in kept_node_ids)
            if stale_nodes:
                stale_nodes.unlink()

            flow.edge_ids.unlink()
            node_by_key = {node.node_key: node for node in flow.node_ids}
            for sequence, edge_data in enumerate(graph['edges'], start=1):
                source_node = node_by_key.get(edge_data['from'])
                target_node = node_by_key.get(edge_data['to'])
                if not source_node or not target_node:
                    continue
                self.env['whatsapp.bot.edge'].create({
                    'flow_id': flow.id,
                    'edge_key': edge_data['id'],
                    'source_node_id': source_node.id,
                    'target_node_id': target_node.id,
                    'source_key': edge_data['from'],
                    'target_key': edge_data['to'],
                    'label': edge_data.get('label') or False,
                    'sequence': sequence,
                    'config_json': _json_dumps(edge_data.get('config')),
                })

    def _default_visual_graph(self):
        return {
            'nodes': [
                {
                    'id': 'trigger_1',
                    'type': 'trigger',
                    'subtype': 'keyword',
                    'legacy_type': 'trigger',
                    'label': 'Keyword Trigger',
                    'x': 80,
                    'y': 140,
                    'config': {
                        'trigger_type': self.trigger_type or 'keyword',
                        'keywords': self.keywords or '',
                    },
                },
                {
                    'id': 'message_1',
                    'type': 'message',
                    'subtype': 'text',
                    'legacy_type': 'message',
                    'label': 'Welcome Message',
                    'x': 390,
                    'y': 140,
                    'config': {
                        'message_mode': 'text',
                        'message_text': self.step_ids[:1].message_text or '',
                    },
                },
            ],
            'edges': [{'id': 'edge_trigger_1_message_1', 'from': 'trigger_1', 'to': 'message_1', 'label': ''}],
            'connections': [{'from': 'trigger_1', 'to': 'message_1', 'label': ''}],
            'nextId': 2,
            'viewport': {'x': 0, 'y': 0, 'zoom': 1},
        }

    def get_visual_graph(self):
        self.ensure_one()
        graph = self._normalize_graph_payload(_json_loads(self.canvas_data, {}))
        if graph['nodes'] and not self._graph_has_step_nodes(graph) and self.step_ids:
            self._sync_steps_to_canvas()
            graph = self._normalize_graph_payload(_json_loads(self.canvas_data, {}))
        if not graph['nodes'] and self.node_ids:
            nodes = []
            for node in self.node_ids.sorted('sequence'):
                nodes.append({
                    'id': node.node_key,
                    'type': node.node_type,
                    'subtype': node.node_subtype,
                    'legacy_type': node.legacy_type or node.node_type,
                    'label': node.name,
                    'x': node.x_position,
                    'y': node.y_position,
                    'config': _json_loads(node.config_json, {}),
                })
            edges = []
            for edge in self.edge_ids.sorted('sequence'):
                edges.append({
                    'id': edge.edge_key,
                    'from': edge.source_key or edge.source_node_id.node_key,
                    'to': edge.target_key or edge.target_node_id.node_key,
                    'label': edge.label or '',
                    'config': _json_loads(edge.config_json, {}),
                })
            graph = self._normalize_graph_payload({'nodes': nodes, 'edges': edges})
        if not graph['nodes']:
            graph = self._default_visual_graph()
        graph.update({
            'flow': {
                'id': self.id,
                'name': self.name,
                'account_id': self.account_id.id,
                'trigger_type': self.trigger_type,
                'keywords': self.keywords or '',
                'active': self.active,
            },
            'graph_version': self.graph_version,
        })
        return graph

    def save_visual_graph(self, graph):
        self.ensure_one()
        self._check_raw_graph_before_save(graph if isinstance(graph, dict) else {})
        graph = self._normalize_graph_payload(graph)
        self.write({
            'canvas_data': json.dumps(graph, ensure_ascii=False),
            'graph_version': self.graph_version + 1,
        })
        return self.get_visual_graph()

    def _check_raw_graph_before_save(self, graph):
        """Reject graph shapes that would make the runtime ambiguous."""
        raw_edges = graph.get('edges')
        if not isinstance(raw_edges, list):
            raw_edges = graph.get('connections') if isinstance(graph.get('connections'), list) else []
        for edge in raw_edges or []:
            if not isinstance(edge, dict):
                continue
            source = edge.get('from') or edge.get('source') or edge.get('source_node_id')
            target = edge.get('to') or edge.get('target') or edge.get('target_node_id')
            if source and target and str(source) == str(target):
                raise ValidationError(
                    "Flow cannot be saved because a step is connected to itself. "
                    "Remove the self-loop before saving."
                )

    def _sync_canvas_to_steps(self):
        self.ensure_one()
        if not self.canvas_data:
            return
        try:
            data = self._normalize_graph_payload(json.loads(self.canvas_data))
            nodes = data.get('nodes', [])
            connections = data.get('connections', [])

            if not isinstance(nodes, list):
                nodes = []
            if not isinstance(connections, list):
                connections = []

            def _int_or_false(value):
                if value in (False, None, ''):
                    return False
                try:
                    return int(value)
                except Exception:
                    return False

            def _existing_id(model_name, value):
                rec_id = _int_or_false(value)
                if not rec_id:
                    return False
                rec = self.env[model_name].browse(rec_id)
                return rec.id if rec.exists() else False

            nodes_by_id = {
                node.get('id'): node
                for node in nodes
                if node.get('id')
            }
            outgoing = {}
            conn_labels = {}
            for conn in connections:
                from_id = conn.get('from')
                to_id = conn.get('to')
                label = conn.get('label') or ''
                if not from_id or not to_id:
                    continue
                outgoing.setdefault(from_id, []).append(to_id)
                conn_labels[(from_id, to_id)] = label.strip()

            trigger_nodes = [node_id for node_id, node in nodes_by_id.items() if node.get('type') == 'trigger']
            if trigger_nodes:
                trigger_cfg = nodes_by_id.get(trigger_nodes[0], {}).get('config')
                trigger_cfg = trigger_cfg if isinstance(trigger_cfg, dict) else {}
                trigger_update_vals = {}
                allowed_triggers = {
                    value for value, _label in self._fields['trigger_type'].selection
                }
                if trigger_cfg.get('trigger_type') in allowed_triggers:
                    trigger_update_vals['trigger_type'] = trigger_cfg.get('trigger_type')
                if 'keywords' in trigger_cfg:
                    trigger_update_vals['keywords'] = trigger_cfg.get('keywords') or False
                if 'webhook_event' in trigger_cfg:
                    trigger_update_vals['webhook_event'] = trigger_cfg.get('webhook_event') or False
                if 'schedule_pattern' in trigger_cfg:
                    trigger_update_vals['schedule_pattern'] = trigger_cfg.get('schedule_pattern') or False
                if trigger_update_vals:
                    self.with_context(skip_canvas_sync=True).write(trigger_update_vals)

            ordered_node_ids = []
            queue = []
            for trigger_id in trigger_nodes:
                queue.extend(outgoing.get(trigger_id, []))

            while queue:
                node_id = queue.pop(0)
                if node_id in ordered_node_ids or node_id not in nodes_by_id:
                    continue
                ordered_node_ids.append(node_id)
                queue.extend(outgoing.get(node_id, []))

            remaining = [
                node_id for node_id, node in nodes_by_id.items()
                if node_id not in ordered_node_ids and node.get('type') != 'trigger'
            ]
            remaining.sort(key=lambda node_id: (
                nodes_by_id[node_id].get('y', 0),
                nodes_by_id[node_id].get('x', 0),
                node_id,
            ))
            ordered_node_ids.extend(remaining)

            existing_steps = {step.node_id: step for step in self.step_ids if step.node_id}
            step_model = self.env['whatsapp.bot.flow.step'].with_context(skip_flow_step_validation=True, skip_canvas_sync=True)
            node_id_to_step = {}
            new_step_ids = []
            step_number = 1
            valid_actions = {
                value for value, _label in self.env['whatsapp.bot.flow.step']._fields['action_type'].selection
            }

            def _node_action_type(node):
                node_type = node.get('type', 'send_text')
                config = node.get('config') if isinstance(node.get('config'), dict) else {}
                if node_type == 'trigger':
                    return False
                if node_type == 'message':
                    message_mode = config.get('message_mode') or config.get('subtype') or node.get('subtype') or 'text'
                    return MESSAGE_NODE_ACTIONS.get(message_mode, 'send_text')
                if node_type == 'action':
                    action_kind = config.get('action_kind') or config.get('action_type') or config.get('subtype') or node.get('subtype') or 'assign_agent'
                    return ACTION_NODE_ACTIONS.get(action_kind, 'transfer')
                return CANVAS_ACTION_MAP.get(node_type, node_type)

            executable_node_ids = [
                node_id for node_id in ordered_node_ids
                if _node_action_type(nodes_by_id.get(node_id) or {}) in valid_actions
            ]
            if not executable_node_ids:
                _logger.warning(
                    "Skipping step synchronization for flow %s because the canvas has no executable step nodes. Existing steps are preserved.",
                    self.id,
                )
                return
            ordered_node_ids = executable_node_ids

            for node_id in ordered_node_ids:
                node = nodes_by_id.get(node_id) or {}
                config = node.get('config') if isinstance(node.get('config'), dict) else {}
                action_type = _node_action_type(node)
                if not action_type:
                    continue

                if action_type not in valid_actions:
                    _logger.warning("Unsupported node type '%s' in flow %s", node.get('type'), self.id)
                    continue

                step_vals = {
                    'name': node.get('label', 'Unnamed Step'),
                    'action_type': action_type,
                    'step_number': step_number,
                    'node_id': node_id,
                }

                if 'message_text' in config or 'text' in config:
                    step_vals['message_text'] = config.get('message_text') or config.get('text') or False
                if 'condition_type' in config:
                    step_vals['condition_type'] = config.get('condition_type') or False
                if 'condition_operator' in config:
                    step_vals['condition_operator'] = config.get('condition_operator') or 'contains'
                if 'condition_source' in config:
                    step_vals['condition_source'] = config.get('condition_source') or 'last_reply'
                if 'condition_variable' in config:
                    step_vals['condition_variable'] = config.get('condition_variable') or False
                if 'condition_value' in config:
                    step_vals['condition_value'] = config.get('condition_value') or False
                if 'input_validation_type' in config:
                    step_vals['input_validation_type'] = config.get('input_validation_type') or 'text'
                if 'invalid_message' in config:
                    step_vals['invalid_message'] = config.get('invalid_message') or False
                if 'timeout_minutes' in config:
                    step_vals['timeout_minutes'] = _int_or_false(config.get('timeout_minutes')) or 0
                if 'max_attempts' in config:
                    step_vals['max_attempts'] = _int_or_false(config.get('max_attempts')) or 1
                if 'delay_seconds' in config:
                    step_vals['delay_seconds'] = _int_or_false(config.get('delay_seconds')) or 0
                if 'http_method' in config:
                    step_vals['http_method'] = config.get('http_method') or 'POST'
                if 'http_url' in config:
                    step_vals['http_url'] = config.get('http_url') or False
                if 'http_payload' in config:
                    step_vals['http_payload'] = config.get('http_payload') or False
                if 'http_headers' in config:
                    step_vals['http_headers'] = config.get('http_headers') or False
                if 'http_query_params' in config:
                    step_vals['http_query_params'] = config.get('http_query_params') or False
                if 'http_auth_type' in config:
                    step_vals['http_auth_type'] = config.get('http_auth_type') or 'none'
                if 'http_auth_token' in config:
                    step_vals['http_auth_token'] = config.get('http_auth_token') or False
                if 'http_username' in config:
                    step_vals['http_username'] = config.get('http_username') or False
                if 'http_password' in config:
                    step_vals['http_password'] = config.get('http_password') or False
                if 'http_response_path' in config:
                    step_vals['http_response_path'] = config.get('http_response_path') or False
                if 'variable_name' in config:
                    step_vals['variable_name'] = config.get('variable_name') or False
                if 'variable_value' in config:
                    step_vals['variable_value'] = config.get('variable_value') or False
                if 'response_variable' in config:
                    step_vals['response_variable'] = config.get('response_variable') or False
                elif 'variable_name' in config and action_type == 'wait_response':
                    step_vals['response_variable'] = config.get('variable_name') or False
                if 'save_response' in config:
                    step_vals['save_response'] = bool(config.get('save_response'))
                elif action_type == 'wait_response':
                    step_vals['save_response'] = bool(config.get('variable_name') or config.get('response_variable'))
                if 'button_header_text' in config:
                    step_vals['button_header_text'] = config.get('button_header_text') or False
                if 'button_footer_text' in config:
                    step_vals['button_footer_text'] = config.get('button_footer_text') or False
                if 'cta_button_text' in config:
                    step_vals['cta_button_text'] = config.get('cta_button_text') or False
                if 'cta_button_url' in config:
                    step_vals['cta_button_url'] = config.get('cta_button_url') or False
                if 'list_button_text' in config:
                    step_vals['list_button_text'] = config.get('list_button_text') or 'Choose'
                if 'list_section_title' in config:
                    step_vals['list_section_title'] = config.get('list_section_title') or 'Options'
                if 'template_id' in config:
                    step_vals['template_id'] = _existing_id('whatsapp.template', config.get('template_id'))
                if 'media_id' in config:
                    step_vals['media_id'] = _existing_id('whatsapp.media.library', config.get('media_id'))
                if 'form_id' in config:
                    step_vals['form_id'] = _existing_id('whatsapp.form', config.get('form_id'))
                if 'payment_mode' in config:
                    step_vals['payment_mode'] = config.get('payment_mode') or 'account_default'
                if 'assign_user_id' in config:
                    step_vals['assign_user_id'] = _existing_id('res.users', config.get('assign_user_id'))
                if 'assign_tag_id' in config:
                    step_vals['assign_tag_id'] = _existing_id('res.partner.category', config.get('assign_tag_id'))
                if 'assign_team_member_ids' in config:
                    raw_ids = config.get('assign_team_member_ids') or []
                    if isinstance(raw_ids, str):
                        raw_ids = [part.strip() for part in raw_ids.split(',') if part.strip()]
                    if not isinstance(raw_ids, list):
                        raw_ids = [raw_ids]
                    member_ids = [
                        _existing_id('whatsapp.team.member', value)
                        for value in raw_ids
                    ]
                    step_vals['assign_team_member_ids'] = [(6, 0, [mid for mid in member_ids if mid])]
                if 'chat_status' in config:
                    step_vals['chat_status'] = config.get('chat_status') or 'open'
                if 'contact_attribute_name' in config:
                    step_vals['contact_attribute_name'] = config.get('contact_attribute_name') or False
                if 'contact_attribute_value' in config:
                    step_vals['contact_attribute_value'] = config.get('contact_attribute_value') or False
                if 'catalog_id' in config:
                    step_vals['catalog_id'] = config.get('catalog_id') or False
                if 'catalog_message_type' in config:
                    step_vals['catalog_message_type'] = config.get('catalog_message_type') or 'single_product'
                if 'product_retailer_id' in config:
                    step_vals['product_retailer_id'] = config.get('product_retailer_id') or False
                if 'product_retailer_ids' in config:
                    step_vals['product_retailer_ids'] = config.get('product_retailer_ids') or False
                if 'thumbnail_product_retailer_id' in config:
                    step_vals['thumbnail_product_retailer_id'] = config.get('thumbnail_product_retailer_id') or False
                if 'catalog_section_title' in config:
                    step_vals['catalog_section_title'] = config.get('catalog_section_title') or False

                step = existing_steps.get(node_id)
                if step:
                    step.with_context(skip_flow_step_validation=True, skip_canvas_sync=True).write(step_vals)
                else:
                    step = step_model.create(dict(step_vals, flow_id=self.id))

                node_id_to_step[node_id] = step
                new_step_ids.append(step.id)
                step_number += 1

            for node_id, step in node_id_to_step.items():
                target_ids = [
                    target_id for target_id in outgoing.get(node_id, [])
                    if target_id in node_id_to_step
                ]
                next_step = node_id_to_step.get(target_ids[0]) if target_ids else False
                write_vals = {'next_step_id': next_step.id if next_step else False}
                config = nodes_by_id.get(node_id, {}).get('config')
                config = config if isinstance(config, dict) else {}

                for config_key, field_name in (
                    ('invalid_node_id', 'invalid_step_id'),
                    ('timeout_node_id', 'timeout_step_id'),
                    ('fallback_node_id', 'fallback_step_id'),
                    ('http_success_node_id', 'http_success_step_id'),
                    ('http_failure_node_id', 'http_failure_step_id'),
                ):
                    target_node_id = config.get(config_key)
                    if target_node_id in node_id_to_step:
                        write_vals[field_name] = node_id_to_step[target_node_id].id
                    elif config_key in config:
                        write_vals[field_name] = False
                if step.action_type == 'condition':
                    true_step = False
                    false_step = False
                    configured_true = config.get('condition_true_node_id')
                    configured_false = config.get('condition_false_node_id')
                    if configured_true in node_id_to_step:
                        true_step = node_id_to_step[configured_true]
                    if configured_false in node_id_to_step:
                        false_step = node_id_to_step[configured_false]
                    for target_id in target_ids:
                        lbl = conn_labels.get((node_id, target_id), '').lower()
                        if lbl == 'true' and not true_step:
                            true_step = node_id_to_step[target_id]
                        elif lbl == 'false' and not false_step:
                            false_step = node_id_to_step[target_id]

                    if not true_step and len(target_ids) > 0:
                        true_step = node_id_to_step[target_ids[0]]
                    if not false_step and len(target_ids) > 1:
                        if len(target_ids) == 2 and target_ids[1] != target_ids[0]:
                            false_step = node_id_to_step[target_ids[1]]
                        elif len(target_ids) > 1:
                            false_step = node_id_to_step[target_ids[1]]
                    write_vals.update({
                        'condition_true_step': true_step.id if true_step else False,
                        'condition_false_step': false_step.id if false_step else False,
                    })
                step.with_context(skip_flow_step_validation=True, skip_canvas_sync=True).write(write_vals)

                if step.action_type == 'condition':
                    has_branch_config = 'condition_branches' in config
                    raw_branches = config.get('condition_branches') if isinstance(config.get('condition_branches'), list) else []
                    branch_vals = []
                    for index, branch in enumerate(raw_branches):
                        if not isinstance(branch, dict):
                            continue
                        target_step = node_id_to_step.get(branch.get('next_node_id')) if branch.get('next_node_id') else False
                        if not target_step:
                            continue
                        branch_vals.append({
                            'step_id': step.id,
                            'sequence': branch.get('sequence') or ((index + 1) * 10),
                            'name': branch.get('name') or f'Branch {index + 1}',
                            'operator': branch.get('operator') or 'contains',
                            'value': branch.get('value') or '',
                            'next_step_id': target_step.id,
                        })
                    if has_branch_config:
                        step.condition_branch_ids.with_context(skip_canvas_sync=True).unlink()
                        for vals in branch_vals:
                            self.env['whatsapp.bot.flow.branch'].with_context(skip_canvas_sync=True).create(vals)

                if step.action_type in ('send_buttons', 'send_list'):
                    existing_buttons = step.button_ids.sorted('id')
                    option_defs = []
                    raw_options = config.get('options')
                    if isinstance(raw_options, list):
                        for index, opt in enumerate(raw_options[:10]):
                            if not isinstance(opt, dict):
                                continue
                            target_step = node_id_to_step.get(opt.get('next_node_id')) if opt.get('next_node_id') else False
                            option_defs.append({
                                'name': opt.get('title') or opt.get('name') or f'Option {index + 1}',
                                'button_id': opt.get('id') or opt.get('button_id') or f'flow_{self.id}_{step.id}_{index + 1}',
                                'description': opt.get('description') or False,
                                'button_action': opt.get('button_action') or 'reply',
                                'url': opt.get('url') or False,
                                'catalog_id': opt.get('catalog_id') or False,
                                'product_retailer_id': opt.get('product_retailer_id') or False,
                                'next_step_id': target_step.id if target_step else False,
                            })
                    if not option_defs:
                        for index, target_id in enumerate(target_ids):
                            target_step = node_id_to_step[target_id]
                            conn_lbl = conn_labels.get((node_id, target_id), '')
                            button_name = conn_lbl or target_step.name or f'Option {index + 1}'
                            option_defs.append({
                                'name': button_name,
                                'button_id': f'flow_{self.id}_{step.id}_{index + 1}',
                                'description': False,
                                'button_action': 'reply',
                                'url': False,
                                'catalog_id': False,
                                'product_retailer_id': False,
                                'next_step_id': target_step.id,
                            })

                    if not option_defs:
                        if existing_buttons:
                            existing_buttons.with_context(skip_canvas_sync=True).unlink()
                        continue

                    if step.action_type == 'send_buttons':
                        special_options = [
                            option for option in option_defs
                            if option.get('button_action') in ('url', 'catalog_product')
                        ]
                        if special_options and len(option_defs) > 1:
                            raise ValidationError(
                                f'Step "{step.name}" can send either quick replies or one URL/product action button, not both.'
                            )

                    limit = 3 if step.action_type == 'send_buttons' else 10
                    for index, option_vals in enumerate(option_defs[:limit]):
                        if index < len(existing_buttons):
                            existing_buttons[index].with_context(skip_canvas_sync=True).write({
                                'name': option_vals['name'],
                                'button_id': option_vals['button_id'],
                                'description': option_vals.get('description'),
                                'button_action': option_vals.get('button_action') or 'reply',
                                'url': option_vals.get('url') or False,
                                'catalog_id': option_vals.get('catalog_id') or False,
                                'product_retailer_id': option_vals.get('product_retailer_id') or False,
                                'next_step_id': option_vals.get('next_step_id') or False,
                            })
                        else:
                            self.env['whatsapp.bot.flow.button'].with_context(skip_canvas_sync=True).create({
                                'step_id': step.id,
                                'name': option_vals['name'],
                                'button_id': option_vals['button_id'],
                                'description': option_vals.get('description'),
                                'button_action': option_vals.get('button_action') or 'reply',
                                'url': option_vals.get('url') or False,
                                'catalog_id': option_vals.get('catalog_id') or False,
                                'product_retailer_id': option_vals.get('product_retailer_id') or False,
                                'next_step_id': option_vals.get('next_step_id') or False,
                            })

                    if len(existing_buttons) > len(option_defs[:limit]):
                        existing_buttons[len(option_defs[:limit]):].with_context(skip_canvas_sync=True).unlink()

            steps_to_unlink = self.step_ids.filtered(lambda s: s.id not in new_step_ids)
            if steps_to_unlink:
                steps_to_unlink.with_context(skip_canvas_sync=True).unlink()

        except Exception as e:
            _logger.exception("Failed to sync canvas to steps for flow %s", self.id)
            raise ValidationError(f"Could not synchronize the visual flow with executable steps: {e}")

    def _sync_steps_to_canvas(self):
        for flow in self:
            canvas = _json_loads(flow.canvas_data, {})
            nodes = canvas.get('nodes', [])
            edges = canvas.get('edges', [])
            connections = canvas.get('connections', [])
            viewport = canvas.get('viewport', {'x': 32, 'y': 32, 'zoom': 1})
            next_id = canvas.get('nextId', len(nodes) + 1)

            trigger_node = None
            for node in nodes:
                if node.get('type') == 'trigger':
                    trigger_node = node
                    break

            if not trigger_node:
                trigger_node = {
                    'id': f'trigger_{next_id}',
                    'type': 'trigger',
                    'subtype': 'keyword',
                    'legacy_type': 'trigger',
                    'label': 'Keyword Trigger',
                    'x': 80,
                    'y': 180,
                    'config': {
                        'trigger_type': flow.trigger_type or 'keyword',
                        'keywords': flow.keywords or '',
                        'webhook_event': flow.webhook_event or '',
                        'schedule_pattern': flow.schedule_pattern or '',
                    }
                }
                nodes.insert(0, trigger_node)
                next_id += 1
            else:
                trigger_node['config'] = {
                    'trigger_type': flow.trigger_type or 'keyword',
                    'keywords': flow.keywords or '',
                    'webhook_event': flow.webhook_event or '',
                    'schedule_pattern': flow.schedule_pattern or '',
                }

            steps = flow.step_ids.sorted('step_number')
            step_nodes = []
            max_x = max([node.get('x', 0) for node in nodes] or [80])
            new_node_x_offset = max_x + 300
            nodes_by_id = {node['id']: node for node in nodes}
            step_to_node_id = {}
            steps_needing_node_id = []

            for step in steps:
                node_id = step.node_id
                node_type, subtype, config = _step_to_node_data(step)
                if node_id and node_id in nodes_by_id:
                    node = nodes_by_id[node_id]
                    node['type'] = node_type
                    node['subtype'] = subtype
                    node['label'] = step.name
                    node['config'] = config
                    step_nodes.append(node)
                    step_to_node_id[step.id] = node['id']
                else:
                    steps_needing_node_id.append((step, node_type, subtype, config))

            for step, node_type, subtype, config in steps_needing_node_id:
                new_id = f'{subtype}_{next_id}'
                next_id += 1
                node = {
                    'id': new_id,
                    'type': node_type,
                    'subtype': subtype,
                    'legacy_type': node_type,
                    'label': step.name,
                    'x': new_node_x_offset,
                    'y': 180,
                    'config': config
                }
                new_node_x_offset += 300
                nodes.append(node)
                step_nodes.append(node)
                step_to_node_id[step.id] = new_id
                step.with_context(skip_canvas_sync=True).write({'node_id': new_id})

            for step in steps:
                from_node_id = step_to_node_id.get(step.id)
                if not from_node_id:
                    continue
                node = next((candidate for candidate in step_nodes if candidate.get('id') == from_node_id), False)
                if not node:
                    continue
                config = node.get('config') if isinstance(node.get('config'), dict) else {}

                def _node_id_for(step_record):
                    return step_to_node_id.get(step_record.id) if step_record and step_record.id in step_to_node_id else False

                config['invalid_node_id'] = _node_id_for(step.invalid_step_id)
                config['timeout_node_id'] = _node_id_for(step.timeout_step_id)
                config['fallback_node_id'] = _node_id_for(step.fallback_step_id)
                config['http_success_node_id'] = _node_id_for(step.http_success_step_id)
                config['http_failure_node_id'] = _node_id_for(step.http_failure_step_id)
                if step.action_type == 'condition':
                    config['condition_true_node_id'] = _node_id_for(step.condition_true_step)
                    config['condition_false_node_id'] = _node_id_for(step.condition_false_step)
                    config['condition_branches'] = [{
                        'sequence': branch.sequence,
                        'name': branch.name,
                        'operator': branch.operator or 'contains',
                        'value': branch.value or '',
                        'next_node_id': _node_id_for(branch.next_step_id),
                    } for branch in step.condition_branch_ids.sorted('sequence')]
                    node['config'] = config
                    continue

                if step.action_type not in ('send_buttons', 'send_list'):
                    node['config'] = config
                    continue

                options = config.get('options') if isinstance(config.get('options'), list) else []
                option_by_id = {
                    (option.get('id') or option.get('button_id')): option
                    for option in options
                    if isinstance(option, dict)
                }
                enriched_options = []
                for index, button in enumerate(step.button_ids.sorted('id')):
                    button_key = button.button_id or f'flow_{flow.id}_{step.id}_{index + 1}'
                    option = dict(option_by_id.get(button_key) or {})
                    option.update({
                        'title': option.get('title') or option.get('name') or button.name,
                        'id': button_key,
                        'description': option.get('description') or button.description or '',
                        'button_action': button.button_action or 'reply',
                        'url': button.url or '',
                        'catalog_id': button.catalog_id or '',
                        'product_retailer_id': button.product_retailer_id or '',
                        'next_node_id': step_to_node_id.get(button.next_step_id.id) if button.next_step_id else False,
                    })
                    enriched_options.append(option)
                config['options'] = enriched_options[:3 if step.action_type == 'send_buttons' else 10]
                node['config'] = config

            final_nodes = [trigger_node] + step_nodes
            new_edges = []
            new_connections = []

            first_step = flow._get_first_step()
            if first_step and first_step.id in step_to_node_id:
                to_node_id = step_to_node_id[first_step.id]
                edge_id = f'edge_{trigger_node["id"]}_{to_node_id}_{int(time.time())}'
                new_edges.append({
                    'id': edge_id,
                    'from': trigger_node['id'],
                    'to': to_node_id,
                    'label': '',
                    'config': {}
                })
                new_connections.append({
                    'from': trigger_node['id'],
                    'to': to_node_id,
                    'label': ''
                })

            for step in steps:
                from_node_id = step_to_node_id.get(step.id)
                if not from_node_id:
                    continue
                if step.action_type == 'condition':
                    if step.condition_true_step and step.condition_true_step.id in step_to_node_id:
                        to_node_id = step_to_node_id[step.condition_true_step.id]
                        edge_id = f'edge_{from_node_id}_{to_node_id}_true'
                        new_edges.append({
                            'id': edge_id,
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'true',
                            'config': {}
                        })
                        new_connections.append({
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'true'
                        })
                    if step.condition_false_step and step.condition_false_step.id in step_to_node_id:
                        to_node_id = step_to_node_id[step.condition_false_step.id]
                        edge_id = f'edge_{from_node_id}_{to_node_id}_false'
                        new_edges.append({
                            'id': edge_id,
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'false',
                            'config': {}
                        })
                        new_connections.append({
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'false'
                        })
                elif step.action_type in ('send_buttons', 'send_list'):
                    for index, button in enumerate(step.button_ids):
                        if button.next_step_id and button.next_step_id.id in step_to_node_id:
                            to_node_id = step_to_node_id[button.next_step_id.id]
                            btn_label = button.name or f'Option {index + 1}'
                            edge_id = f'edge_{from_node_id}_{to_node_id}_{button.id}'
                            new_edges.append({
                                'id': edge_id,
                                'from': from_node_id,
                                'to': to_node_id,
                                'label': btn_label,
                                'config': {}
                            })
                            new_connections.append({
                                'from': from_node_id,
                                'to': to_node_id,
                                'label': btn_label
                            })
                else:
                    if step.next_step_id and step.next_step_id.id in step_to_node_id:
                        to_node_id = step_to_node_id[step.next_step_id.id]
                        edge_id = f'edge_{from_node_id}_{to_node_id}_{int(time.time())}'
                        new_edges.append({
                            'id': edge_id,
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': '',
                            'config': {}
                        })
                        new_connections.append({
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': ''
                        })

            new_canvas = {
                'nodes': final_nodes,
                'edges': new_edges,
                'connections': new_connections,
                'nextId': next_id,
                'viewport': viewport,
            }
            flow.with_context(skip_canvas_sync=True).write({
                'canvas_data': json.dumps(new_canvas, ensure_ascii=False)
            })
            flow._sync_node_edge_records_from_canvas()
    
    def action_test_flow(self):
        """Test this flow by manually triggering it"""
        for flow in self:
            flow._raise_if_flow_has_activation_warnings()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Test Flow',
            'res_model': 'whatsapp.bot.flow.test.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_flow_id': self.id,
            }
        }

    def action_generate_ai_flow_review(self):
        """Create an auditable flow review draft. Does not activate or change steps."""
        self.ensure_one()
        if not self.env['elsx.ai.provider']._whatsapp_draft_enabled():
            raise UserError(_("WhatsApp AI drafts are disabled in Settings."))
        step_summary = "\n".join(
            "%s. %s (%s)" % (step.step_number, step.name, step.action_type)
            for step in self.step_ids.sorted('step_number')
        )
        job = self.env['elsx.ai.job'].create_job(
            'custom',
            'AI flow review for %s' % self.name,
            origin=self,
            input_text=(
                "Review this WhatsApp bot flow for missing routes, confusing user paths, missing fallback/no-reply handling, "
                "and useful next steps. Do not modify the flow.\n\nFlow: %s\nType: %s\nSteps:\n%s"
            ) % (self.name, self.flow_type, step_summary or 'No steps configured.'),
            prompt_code='whatsapp_flow_review_default',
        )
        job.action_run()
        self.ai_flow_review = job.response_text or job.response_json or ''
        return {
            'type': 'ir.actions.act_window',
            'name': 'AI Flow Review Job',
            'res_model': 'elsx.ai.job',
            'res_id': job.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _extract_ai_flow_payload(self, raw_value):
        """Return a safe AI flow payload if the provider produced valid JSON."""
        if not raw_value:
            return False
        if isinstance(raw_value, dict):
            payload = raw_value
        else:
            text = str(raw_value).strip()
            if text.startswith('```'):
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
            try:
                payload = json.loads(text)
            except Exception:
                match = re.search(r'\{.*\}', text, flags=re.S)
                if not match:
                    return False
                try:
                    payload = json.loads(match.group(0))
                except Exception:
                    return False
        if isinstance(payload, dict) and isinstance(payload.get('flow'), dict):
            payload = payload['flow']
        nodes = payload.get('nodes') if isinstance(payload, dict) else False
        if not isinstance(nodes, list) or not nodes:
            return False
        return payload

    def _create_ai_json_flow_draft(self, payload, job, prompt):
        """Create an inactive draft directly from sanitized AI JSON."""
        self.ensure_one()
        allowed_types = {
            'send_text', 'send_template', 'send_buttons', 'send_list', 'send_media',
            'wait_reply', 'ask_question', 'condition', 'assign_agent', 'assign_team',
            'add_tag', 'create_lead', 'chat_status', 'update_contact', 'set_variable',
            'send_cta_url', 'send_catalog', 'send_form_link', 'send_payment_link',
            'delay', 'api_call', 'end',
        }

        def clean_id(value, fallback):
            value = re.sub(r'[^a-zA-Z0-9_]+', '_', str(value or fallback)).strip('_')
            return value or fallback

        def clean_config(node_type, node):
            config = node.get('config') if isinstance(node.get('config'), dict) else {}
            config = dict(config)
            for key in (
                'message_text', 'template_id', 'media_id', 'form_id', 'catalog_id',
                'product_retailer_id', 'product_retailer_ids', 'thumbnail_product_retailer_id',
                'catalog_message_type', 'catalog_section_title', 'button_header_text',
                'button_footer_text', 'cta_button_text', 'cta_button_url', 'response_variable',
                'input_validation_type', 'invalid_message', 'max_attempts', 'timeout_minutes',
                'condition_type', 'condition_source', 'condition_operator', 'condition_value',
                'delay_seconds', 'http_method', 'http_url', 'http_payload', 'http_headers',
                'http_query_params', 'http_auth_type', 'http_response_path', 'variable_name',
                'variable_value', 'chat_status', 'contact_attribute_name', 'contact_attribute_value',
                'fallback_node_id', 'invalid_node_id', 'timeout_node_id', 'http_success_node_id',
                'http_failure_node_id',
            ):
                if key in node and key not in config:
                    config[key] = node.get(key)
            if node_type == 'send_text':
                config.setdefault('message_mode', 'text')
                config.setdefault('message_text', node.get('text') or node.get('body') or 'Hi {{name}}, how can we help today?')
            elif node_type == 'send_buttons':
                config.setdefault('message_mode', 'buttons')
                config['options'] = config.get('options') if isinstance(config.get('options'), list) else node.get('options') or []
                config['options'] = config['options'][:3]
            elif node_type == 'send_list':
                config.setdefault('message_mode', 'list')
                config.setdefault('list_button_text', 'Choose')
                config.setdefault('list_section_title', 'Options')
                config['options'] = config.get('options') if isinstance(config.get('options'), list) else node.get('options') or []
                config['options'] = config['options'][:10]
            elif node_type == 'send_form_link':
                config.setdefault('action_kind', 'send_form_link')
                config.setdefault('message_text', 'Please fill this short form so our team can help you faster: {{form_url}}')
            elif node_type == 'send_payment_link':
                config.setdefault('action_kind', 'send_payment_link')
                config.setdefault('message_text', 'Here is your payment link: {{payment_url}}')
            elif node_type == 'send_catalog':
                config.setdefault('action_kind', 'send_catalog')
                config.setdefault('catalog_message_type', 'single_product')
            elif node_type == 'send_cta_url':
                config.setdefault('action_kind', 'send_cta_url')
                config.setdefault('cta_button_text', 'Open')
            elif node_type == 'api_call':
                config.setdefault('action_kind', 'api_call')
                config.setdefault('http_method', 'POST')
            elif node_type == 'condition':
                config.setdefault('condition_operator', 'contains')
                config.setdefault('condition_source', 'last_reply')
            else:
                config.setdefault('action_kind', node_type)
            return config

        canvas_nodes = [{
            'id': 'trigger_ai',
            'type': 'trigger',
            'subtype': 'keyword',
            'legacy_type': 'trigger',
            'label': 'Manual Trigger',
            'x': 80,
            'y': 180,
            'config': {'trigger_type': 'manual', 'keywords': ''},
        }]
        node_ids = set(['trigger_ai'])
        incoming_nodes = payload.get('nodes') or []
        for index, node in enumerate(incoming_nodes[:25], start=1):
            if not isinstance(node, dict):
                continue
            node_type = node.get('type') or node.get('action_type') or node.get('kind') or 'send_text'
            node_type = {
                'text': 'send_text',
                'buttons': 'send_buttons',
                'list': 'send_list',
                'media': 'send_media',
                'template': 'send_template',
                'http_request': 'api_call',
                'wait_response': 'wait_reply',
            }.get(node_type, node_type)
            if node_type not in allowed_types:
                node_type = 'send_text'
            node_id = clean_id(node.get('id') or node.get('node_id'), 'ai_node_%s' % index)
            while node_id in node_ids:
                node_id = '%s_%s' % (node_id, index)
            node_ids.add(node_id)
            canvas_nodes.append({
                'id': node_id,
                'type': node_type,
                'legacy_type': node_type,
                'label': node.get('label') or node.get('name') or node_type.replace('_', ' ').title(),
                'x': int(node.get('x') or (360 + ((index - 1) % 3) * 280)),
                'y': int(node.get('y') or (120 + ((index - 1) // 3) * 180)),
                'config': clean_config(node_type, node),
            })

        if len(canvas_nodes) <= 1:
            return False

        valid_ids = {node['id'] for node in canvas_nodes}
        raw_edges = payload.get('edges') or payload.get('connections') or []
        connections = []
        for index, edge in enumerate(raw_edges[:40], start=1):
            if not isinstance(edge, dict):
                continue
            source = clean_id(edge.get('from') or edge.get('source') or edge.get('source_node_id'), '')
            target = clean_id(edge.get('to') or edge.get('target') or edge.get('target_node_id'), '')
            if source in valid_ids and target in valid_ids and source != target:
                connections.append({
                    'from': source,
                    'to': target,
                    'label': edge.get('label') or edge.get('name') or '',
                })
        if not connections:
            connections.append({'from': 'trigger_ai', 'to': canvas_nodes[1]['id'], 'label': ''})
            for index in range(1, len(canvas_nodes) - 1):
                connections.append({'from': canvas_nodes[index]['id'], 'to': canvas_nodes[index + 1]['id'], 'label': ''})

        canvas = {
            'nodes': canvas_nodes,
            'connections': connections,
            'edges': [
                {'id': 'edge_%s_%s_%s' % (conn['from'], conn['to'], idx), **conn, 'config': {}}
                for idx, conn in enumerate(connections, start=1)
            ],
            'nextId': len(canvas_nodes) + 1,
            'viewport': {'x': 32, 'y': 32, 'zoom': 1},
        }

        draft_name = _('%s - AI JSON Draft') % self.name
        existing_count = self.search_count([('name', '=like', draft_name + '%')])
        if existing_count:
            draft_name = '%s %s' % (draft_name, existing_count + 1)
        draft = self.with_context(skip_canvas_sync=True).create({
            'name': draft_name,
            'account_id': self.account_id.id,
            'flow_type': self.flow_type or 'custom',
            'trigger_type': 'manual',
            'keywords': False,
            'active': False,
            'priority': self.priority or 10,
            'description': _('Inactive AI JSON draft generated from prompt. Review every step before activation.\n\nPrompt: %s') % prompt,
            'ai_generated_from_flow_id': self.id,
            'ai_draft_job_id': job.id,
            'ai_flow_review': job.response_text or job.response_json or '',
            'canvas_data': json.dumps(canvas, ensure_ascii=False),
        })
        draft._sync_canvas_to_steps()
        draft._sync_node_edge_records_from_canvas()
        if not draft.step_ids:
            return False
        return draft

    def action_generate_ai_flow_draft(self):
        """Create an inactive, reviewable flow draft from the admin prompt."""
        self.ensure_one()
        prompt = (self.ai_flow_prompt or self.description or '').strip()
        if not prompt:
            raise UserError(_("Add an AI Flow Draft Prompt before generating a draft."))

        job = self.env['elsx.ai.job'].create_job(
            'custom',
            _('AI flow draft for %s') % self.name,
            origin=self,
            input_text=(
                "Create a safe WhatsApp bot draft for this business need. "
                "Return only JSON with keys nodes and edges. "
                "Allowed node types: send_text, send_buttons, send_list, ask_question, condition, assign_agent, "
                "assign_team, add_tag, create_lead, send_cta_url, send_catalog, send_form_link, send_payment_link, "
                "api_call, delay, end. "
                "Each node may include id, type, label, message_text, options, config. "
                "Edges use from/to/label. The draft must be inactive and editable.\n\n%s"
            ) % prompt,
            input_payload={
                'flow_name': self.name,
                'flow_type': self.flow_type,
                'account_id': self.account_id.id,
                'active': False,
            },
            prompt_code='whatsapp_flow_draft_default',
        )
        try:
            if self.env['elsx.ai.provider']._ai_enabled():
                job.action_run()
            else:
                job.write({
                    'state': 'completed',
                    'response_text': _(
                        'AI provider is disabled, so a deterministic inactive draft was generated from the prompt.'
                    ),
                })
                job._log('info', job.response_text)
        except UserError as exc:
            job.write({'state': 'failed', 'error_message': str(exc)})
            job._log('warning', str(exc))

        payload = self._extract_ai_flow_payload(job.response_text or job.response_json)
        if payload:
            try:
                draft = self._create_ai_json_flow_draft(payload, job, prompt)
                if draft:
                    return {
                        'type': 'ir.actions.act_window',
                        'name': _('Review AI Flow Draft'),
                        'res_model': 'whatsapp.bot.flow',
                        'res_id': draft.id,
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                        'target': 'current',
                    }
            except Exception as exc:
                job._log('warning', _('AI JSON draft could not be created, using safe fallback: %s') % exc)

        draft_name = _('%s - AI Draft') % self.name
        existing_count = self.search_count([('name', '=like', draft_name + '%')])
        if existing_count:
            draft_name = '%s %s' % (draft_name, existing_count + 1)

        draft = self.with_context(skip_canvas_sync=True).create({
            'name': draft_name,
            'account_id': self.account_id.id,
            'flow_type': self.flow_type or 'custom',
            'trigger_type': 'manual',
            'keywords': False,
            'active': False,
            'priority': self.priority or 10,
            'description': _(
                'Inactive AI draft generated from "%s". Review every step, routes, templates, forms, and payment settings before activation.'
            ) % self.name,
            'ai_generated_from_flow_id': self.id,
            'ai_draft_job_id': job.id,
            'ai_flow_review': job.response_text or job.response_json or '',
        })

        Step = self.env['whatsapp.bot.flow.step'].with_context(
            skip_canvas_sync=True,
            skip_flow_step_validation=True,
        )
        Button = self.env['whatsapp.bot.flow.button'].with_context(skip_canvas_sync=True)
        default_form = self.account_id.default_form_id
        shop_url = self.account_id.commerce_shop_url
        payment_enabled = self.account_id.payment_link_mode != 'disabled'

        welcome = Step.create({
            'flow_id': draft.id,
            'step_number': 1,
            'name': _('Welcome Menu'),
            'action_type': 'send_buttons',
            'message_text': _(
                'Hi {{name}}, thanks for contacting us. Please choose what you need.'
            ),
            'node_id': 'ai_welcome',
        })
        catalogue = Step.create({
            'flow_id': draft.id,
            'step_number': 2,
            'name': _('Share Catalogue / Shop'),
            'action_type': 'send_cta_url' if shop_url else 'send_text',
            'message_text': _(
                'Please review our catalogue/shop. If you need a specific size or load rating, reply with details.'
            ),
            'cta_button_text': _('Open Shop'),
            'cta_button_url': shop_url or False,
            'node_id': 'ai_catalogue',
        })
        requirement = Step.create({
            'flow_id': draft.id,
            'step_number': 3,
            'name': _('Collect Requirement'),
            'action_type': 'ask_question',
            'message_text': _(
                'Please share product type, size, load capacity, quantity, and delivery city.'
            ),
            'response_variable': 'customer_requirement',
            'input_validation_type': 'text',
            'max_attempts': 2,
            'node_id': 'ai_requirement',
        })
        lead = Step.create({
            'flow_id': draft.id,
            'step_number': 4,
            'name': _('Create Sales Lead'),
            'action_type': 'create_lead',
            'message_text': _('Requirement captured from WhatsApp flow: {{customer_requirement}}'),
            'node_id': 'ai_lead',
        })
        support = Step.create({
            'flow_id': draft.id,
            'step_number': 5,
            'name': _('Assign Support'),
            'action_type': 'assign_team',
            'message_text': False,
            'node_id': 'ai_support',
        })
        form_step = Step.create({
            'flow_id': draft.id,
            'step_number': 6,
            'name': _('Send Form Link'),
            'action_type': 'send_form_link' if default_form else 'send_text',
            'message_text': _(
                'Please fill this short form so our team has the right details: {{form_url}}'
            ) if default_form else _('No default form is configured yet. Please create/select a WhatsApp form first.'),
            'form_id': default_form.id if default_form else False,
            'node_id': 'ai_form',
        })
        payment_step = Step.create({
            'flow_id': draft.id,
            'step_number': 7,
            'name': _('Send Payment Link'),
            'action_type': 'send_payment_link' if payment_enabled else 'send_text',
            'message_text': _(
                'Here is your payment link: {{payment_url}}'
            ) if payment_enabled else _('Payment links are disabled on this WhatsApp account.'),
            'node_id': 'ai_payment',
        })
        end_step = Step.create({
            'flow_id': draft.id,
            'step_number': 8,
            'name': _('End'),
            'action_type': 'end',
            'node_id': 'ai_end',
        })

        Button.create([
            {
                'step_id': welcome.id,
                'name': _('Catalogue'),
                'button_id': 'catalogue',
                'next_step_id': catalogue.id,
            },
            {
                'step_id': welcome.id,
                'name': _('Price / Quote'),
                'button_id': 'price_quote',
                'next_step_id': requirement.id,
            },
            {
                'step_id': welcome.id,
                'name': _('Support'),
                'button_id': 'support',
                'next_step_id': support.id,
            },
        ])
        catalogue.next_step_id = end_step
        requirement.next_step_id = lead
        lead.next_step_id = form_step if default_form else end_step
        form_step.next_step_id = payment_step if payment_enabled else end_step
        payment_step.next_step_id = end_step
        support.next_step_id = end_step

        draft._sync_steps_to_canvas()
        draft._sync_node_edge_records_from_canvas()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Review AI Flow Draft'),
            'res_model': 'whatsapp.bot.flow',
            'res_id': draft.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
    
    def action_view_logs(self):
        """View execution logs for this flow"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Execution Logs',
            'res_model': 'whatsapp.bot.flow.log',
            'view_mode': 'tree,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('flow_id', '=', self.id)],
            'target': 'current',
        }

    @api.model
    def _seed_fiberafrp_assistant_flow(self):
        """Create a practical default sales/support assistant for FiberaFRP."""
        def repair_flow(flow):
            default_steps = flow.step_ids.filtered(
                lambda step: step.name == 'Welcome Message'
                and step.action_type == 'send_text'
                and step.step_number == 1
                and not step.message_text
            )
            if default_steps:
                default_steps.with_context(skip_canvas_sync=True).unlink()
                flow._sync_steps_to_canvas()
                flow._sync_node_edge_records_from_canvas()

        account = self.env['whatsapp.account']._get_default_account()
        if not account:
            _logger.info("Skipping FiberaFRP assistant flow seed because no WhatsApp account exists.")
            return False

        existing = self.with_context(active_test=False).search([
            ('account_id', '=', account.id),
            ('name', '=', 'FiberaFRP Sales & Support Assistant'),
        ], limit=1)
        if existing:
            repair_flow(existing)
            return existing

        Tag = self.env['res.partner.category'].sudo()
        catalogue_tag = Tag.search([('name', '=', 'Catalogue Requested')], limit=1) or Tag.create({
            'name': 'Catalogue Requested',
        })
        price_tag = Tag.search([('name', '=', 'Price Enquiry')], limit=1) or Tag.create({
            'name': 'Price Enquiry',
        })

        team_member = self.env['whatsapp.team.member'].sudo().search([
            ('account_id', '=', account.id),
            ('user_id', '!=', False),
            ('can_send_messages', '=', True),
        ], limit=1)
        assign_user = team_member.user_id or self.env.user

        flow = self.with_context(skip_canvas_sync=True).create({
            'name': 'FiberaFRP Sales & Support Assistant',
            'account_id': account.id,
            'description': (
                'Useful starter bot for product catalogue requests, price enquiries, '
                'support routing, CRM lead creation, and human handoff.'
            ),
            'flow_type': 'sales',
            'trigger_type': 'keyword',
            'keywords': 'hi, hello, start, catalogue, catalog, price, quote, support, help',
            'priority': 80,
            'active': False if self.env.context.get('restore_defaults_inactive') else True,
            'retry_on_failure': True,
            'max_retries': 2,
        })

        Step = self.env['whatsapp.bot.flow.step'].with_context(
            skip_flow_step_validation=True,
            skip_canvas_sync=True,
        )
        welcome = Step.create({
            'flow_id': flow.id,
            'step_number': 1,
            'name': 'Welcome Menu',
            'action_type': 'send_buttons',
            'message_text': (
                'Hi {{name}}, welcome to FiberaFRP.\n\n'
                'Please choose what you need:'
            ),
        })
        tag_catalogue = Step.create({
            'flow_id': flow.id,
            'step_number': 10,
            'name': 'Tag Catalogue Lead',
            'action_type': 'assign_tag',
            'assign_tag_id': catalogue_tag.id,
        })
        catalogue_reply = Step.create({
            'flow_id': flow.id,
            'step_number': 11,
            'name': 'Catalogue Reply',
            'action_type': 'send_text',
            'message_text': (
                'Thanks {{name}}. Our team will share the latest FiberaFRP catalogue shortly.\n\n'
                'We manufacture manhole covers, tank covers, gratings, gully covers, recess covers, '
                'and drainage products in FRP/GRP.'
            ),
        })
        tag_price = Step.create({
            'flow_id': flow.id,
            'step_number': 20,
            'name': 'Tag Price Enquiry',
            'action_type': 'assign_tag',
            'assign_tag_id': price_tag.id,
        })
        create_lead = Step.create({
            'flow_id': flow.id,
            'step_number': 21,
            'name': 'Create CRM Lead',
            'action_type': 'create_lead',
            'message_text': (
                'Customer requested pricing/quotation from WhatsApp.\n'
                'Phone: {{phone}}\n'
                'Last message: {{last_message}}'
            ),
        })
        price_reply = Step.create({
            'flow_id': flow.id,
            'step_number': 22,
            'name': 'Price Reply',
            'action_type': 'send_text',
            'message_text': (
                'Got it. I have created a sales enquiry for you.\n\n'
                'Please reply with product type, size, load capacity, quantity, and delivery city. '
                'A sales executive will help with pricing.'
            ),
        })
        support_transfer = Step.create({
            'flow_id': flow.id,
            'step_number': 30,
            'name': 'Assign Support Agent',
            'action_type': 'transfer',
            'assign_user_id': assign_user.id,
        })
        support_reply = Step.create({
            'flow_id': flow.id,
            'step_number': 31,
            'name': 'Support Reply',
            'action_type': 'send_text',
            'message_text': (
                'I have assigned this chat to our team.\n\n'
                'Please share your order number, invoice number, or issue details so we can help faster.'
            ),
        })
        human_transfer = Step.create({
            'flow_id': flow.id,
            'step_number': 40,
            'name': 'Human Handoff',
            'action_type': 'transfer',
            'assign_user_id': assign_user.id,
        })
        human_reply = Step.create({
            'flow_id': flow.id,
            'step_number': 41,
            'name': 'Human Handoff Reply',
            'action_type': 'send_text',
            'message_text': 'Sure. I have handed this chat to a team member.',
        })

        tag_catalogue.next_step_id = catalogue_reply.id
        tag_price.next_step_id = create_lead.id
        create_lead.next_step_id = price_reply.id
        support_transfer.next_step_id = support_reply.id
        human_transfer.next_step_id = human_reply.id

        Button = self.env['whatsapp.bot.flow.button'].with_context(skip_canvas_sync=True)
        Button.create([
            {
                'step_id': welcome.id,
                'name': 'Catalogue',
                'button_id': 'fibera_catalogue',
                'next_step_id': tag_catalogue.id,
            },
            {
                'step_id': welcome.id,
                'name': 'Price / Quote',
                'button_id': 'fibera_price',
                'next_step_id': tag_price.id,
            },
            {
                'step_id': welcome.id,
                'name': 'Support / Agent',
                'button_id': 'fibera_support',
                'next_step_id': support_transfer.id,
            },
        ])

        flow._sync_steps_to_canvas()
        flow._sync_node_edge_records_from_canvas()
        repair_flow(flow)
        _logger.info("Created FiberaFRP Sales & Support Assistant bot flow %s.", flow.id)
        return flow

    @api.model
    def _seed_fiberafrp_advanced_business_flows(self):
        """Create inactive business-flow blueprints that admins can review and activate."""
        account = self.env['whatsapp.account'].sudo()._get_default_account()
        if not account:
            _logger.info("Skipping advanced business flow blueprints because no WhatsApp account exists.")
            return self.browse()

        forms = {
            form.name: form
            for form in self.env['whatsapp.form'].sudo().search([
                ('name', 'in', ['Lead Enquiry', 'Support Ticket', 'Catalogue Request', 'Quote Request', 'Feedback'])
            ])
        }
        if 'Quote Request' not in forms:
            self.env['whatsapp.form'].sudo()._seed_fiberafrp_production_forms()
            forms = {
                form.name: form
                for form in self.env['whatsapp.form'].sudo().search([
                    ('name', 'in', ['Lead Enquiry', 'Support Ticket', 'Catalogue Request', 'Quote Request', 'Feedback'])
                ])
            }

        Tag = self.env['res.partner.category'].sudo()
        tag_names = [
            'Catalogue Requested',
            'Quote Requested',
            'Support Required',
            'Payment Follow-up',
            'Dealer / Project Lead',
            'Feedback Received',
            'Business Concierge',
            'Website Shared',
            'Quote Qualified',
            'Agent Requested',
            'Order Help',
            'Invoice Help',
            'Warranty Requested',
            'Product Issue',
            'Forms Shared',
        ]
        tags = {
            name: Tag.search([('name', '=', name)], limit=1) or Tag.create({'name': name})
            for name in tag_names
        }

        team_member = self.env['whatsapp.team.member'].sudo().search([
            ('account_id', '=', account.id),
            ('user_id', '!=', False),
            ('can_send_messages', '=', True),
        ], limit=1)
        assign_user = team_member.user_id or self.env.user

        Flow = self.with_context(skip_canvas_sync=True)
        Step = self.env['whatsapp.bot.flow.step'].with_context(
            skip_flow_step_validation=True,
            skip_canvas_sync=True,
        )
        Button = self.env['whatsapp.bot.flow.button'].with_context(skip_canvas_sync=True)
        Branch = self.env['whatsapp.bot.flow.branch'].with_context(skip_canvas_sync=True)
        created = self.browse()

        def create_flow(name, flow_type, keywords, description, priority=40):
            existing = self.with_context(active_test=False).search([
                ('account_id', '=', account.id),
                ('name', '=', name),
            ], limit=1)
            if existing:
                return existing, False
            flow = Flow.create({
                'name': name,
                'account_id': account.id,
                'description': description,
                'flow_type': flow_type,
                'trigger_type': 'keyword',
                'keywords': keywords,
                'priority': priority,
                'active': False,
                'retry_on_failure': True,
                'max_retries': 2,
            })
            return flow, True

        def create_step(flow, number, name, action, **vals):
            vals.update({
                'flow_id': flow.id,
                'step_number': number,
                'name': name,
                'action_type': action,
            })
            return Step.create(vals)

        def route(source, target):
            if source and target:
                source.with_context(skip_canvas_sync=True).write({'next_step_id': target.id})

        def add_buttons(step, button_defs):
            Button.create([
                {
                    'step_id': step.id,
                    'name': label,
                    'button_id': button_id,
                    'description': description or False,
                    'next_step_id': target.id if target else False,
                }
                for label, button_id, description, target in button_defs
            ])

        def add_branches(step, branch_defs):
            Branch.create([
                {
                    'step_id': step.id,
                    'sequence': sequence,
                    'name': label,
                    'operator': operator,
                    'value': value,
                    'next_step_id': target.id,
                }
                for sequence, label, operator, value, target in branch_defs
                if target
            ])

        def finish(flow):
            flow._sync_steps_to_canvas()
            flow._sync_node_edge_records_from_canvas()
            return flow

        shop_url = (
            account.commerce_shop_url
            or (account.business_websites.split(',')[0].strip() if account.business_websites else '')
            or 'https://fiberafrp.com'
        )
        has_catalog_config = bool(
            account.commerce_catalog_id
            and (
                account.commerce_default_product_retailer_id
                or account.commerce_shop_url
            )
        )
        payment_enabled = account.payment_link_mode == 'manual_url' and bool(account.payment_manual_url)

        flow, is_new = create_flow(
            'Fibera Composite India Business Concierge - Blueprint',
            'custom',
            (
                'hi, hello, start, menu, fibera, fibera composite, catalogue, catalog, website, '
                'price, quote, quotation, support, warranty, dealer, project, payment, invoice, agent'
            ),
            (
                'Inactive enterprise concierge for Fibera Composite India Pvt Ltd. Routes customers through '
                'catalogue/website, quote qualification, dealer/project enquiries, support/warranty, order/payment, '
                'forms/uploads, feedback, and human handoff.'
            ),
            priority=95,
        )
        if is_new:
            main_menu = create_step(
                flow, 10, 'Business Concierge Menu', 'send_list',
                message_text=(
                    'Hi {{name}}, welcome to Fibera Composite India Pvt Ltd.\n\n'
                    'Please choose how we can help you today.'
                ),
                button_header_text='Fibera Composite',
                button_footer_text='You can also type your requirement.',
                list_button_text='Choose help',
                list_section_title='Business Desk',
            )
            business_tag = create_step(flow, 1, 'Tag Business Concierge', 'assign_tag', assign_tag_id=tags['Business Concierge'].id)
            free_text_router = create_step(
                flow, 20, 'Free Text Intent Router', 'condition',
                condition_type='keyword_match',
                condition_source='incoming_text',
                condition_operator='regex',
                condition_value='price|quote|quotation|rate|cost',
            )

            catalogue_tag = create_step(flow, 100, 'Tag Catalogue / Website Interest', 'assign_tag', assign_tag_id=tags['Catalogue Requested'].id)
            website_tag = create_step(flow, 105, 'Tag Website Shared', 'assign_tag', assign_tag_id=tags['Website Shared'].id)
            website_link = create_step(
                flow, 110, 'Open Catalogue / Website', 'send_cta_url',
                message_text=(
                    'Please open our catalogue/website for Fibera Composite India Pvt Ltd products. '
                    'Reply here if you want pricing, technical details, or dealer support.'
                ),
                cta_button_text='Open Catalogue',
                cta_button_url=shop_url,
                button_footer_text='FRP manhole covers, drain covers, gratings, tank covers, and project products.',
            )
            if has_catalog_config:
                catalog_message = create_step(
                    flow, 115, 'Send Meta Catalog Message', 'send_catalog',
                    message_text='You can also browse available product cards here.',
                    catalog_message_type='catalog_message',
                    thumbnail_product_retailer_id=account.commerce_default_product_retailer_id,
                    button_footer_text='Tap the catalogue card to view product details.',
                )
            else:
                catalog_message = False
            catalogue_form = create_step(
                flow, 120, 'Send Catalogue Request Form', 'send_form_link',
                message_text='If you want a specific catalogue range, please fill this quick request form: {{form_url}}',
                form_id=forms.get('Catalogue Request').id if forms.get('Catalogue Request') else False,
            )
            catalogue_question = create_step(
                flow, 130, 'Ask Catalogue Requirement', 'ask_question',
                message_text='Which product range do you want to discuss? Example: manhole cover, drain cover, FRP grating, tank cover.',
                input_validation_type='text',
                save_response=True,
                response_variable='catalogue_product_interest',
                max_attempts=2,
            )
            catalogue_city = create_step(
                flow, 140, 'Ask Catalogue City', 'ask_question',
                message_text='Which city or project location should our team consider?',
                input_validation_type='text',
                save_response=True,
                response_variable='catalogue_city',
                max_attempts=2,
            )
            catalogue_lead = create_step(
                flow, 150, 'Create Catalogue Lead', 'create_lead',
                message_text=(
                    'Catalogue/website lead from WhatsApp.\n'
                    'Product interest: {{catalogue_product_interest}}\n'
                    'City: {{catalogue_city}}\n'
                    'Phone: {{phone}}'
                ),
            )

            quote_tag = create_step(flow, 200, 'Tag Quote Requested', 'assign_tag', assign_tag_id=tags['Quote Requested'].id)
            quote_product = create_step(
                flow, 210, 'Ask Quote Product', 'ask_question',
                message_text='Which product do you need? Example: FRP manhole cover, gully cover, drain cover, grating, tank cover.',
                input_validation_type='text',
                save_response=True,
                response_variable='quote_product',
                max_attempts=2,
            )
            quote_size = create_step(
                flow, 220, 'Ask Size / Load', 'ask_question',
                message_text='Please share size and load rating. Example: 600x600 heavy duty, 10T, 25T, custom size.',
                input_validation_type='text',
                save_response=True,
                response_variable='quote_size_load',
                max_attempts=2,
            )
            quote_qty = create_step(
                flow, 230, 'Ask Quantity', 'ask_question',
                message_text='How many pieces or approximate quantity do you require?',
                input_validation_type='number',
                save_response=True,
                response_variable='quote_quantity',
                max_attempts=2,
            )
            quote_city = create_step(
                flow, 240, 'Ask Delivery City', 'ask_question',
                message_text='Which delivery city or site location should we quote for?',
                input_validation_type='text',
                save_response=True,
                response_variable='quote_city',
                max_attempts=2,
            )
            quote_timeline = create_step(
                flow, 250, 'Ask Timeline / Notes', 'ask_question',
                message_text='Please share timeline, project name, drawings/BOQ note, or any special requirement.',
                input_validation_type='text',
                save_response=True,
                response_variable='quote_notes',
                max_attempts=2,
            )
            quote_contact_update = create_step(
                flow, 260, 'Save Product Interest', 'update_contact',
                contact_attribute_name='fibera_last_quote_interest',
                contact_attribute_value='{{quote_product}} | {{quote_size_load}} | Qty {{quote_quantity}} | {{quote_city}}',
            )
            quote_lead = create_step(
                flow, 270, 'Create Qualified Quote Lead', 'create_lead',
                message_text=(
                    'Qualified WhatsApp quotation request for Fibera Composite India Pvt Ltd.\n'
                    'Product: {{quote_product}}\n'
                    'Size/load: {{quote_size_load}}\n'
                    'Quantity: {{quote_quantity}}\n'
                    'City: {{quote_city}}\n'
                    'Notes: {{quote_notes}}\n'
                    'Phone: {{phone}}'
                ),
            )
            quote_qualified = create_step(flow, 275, 'Tag Quote Qualified', 'assign_tag', assign_tag_id=tags['Quote Qualified'].id)
            quote_form = create_step(
                flow, 280, 'Send Quote Request Form', 'send_form_link',
                message_text='For drawings, BOQ, GST/company details, or exact specs, please use this quote form: {{form_url}}',
                form_id=forms.get('Quote Request').id if forms.get('Quote Request') else False,
            )

            dealer_tag = create_step(flow, 300, 'Tag Dealer / Project Lead', 'assign_tag', assign_tag_id=tags['Dealer / Project Lead'].id)
            dealer_type = create_step(
                flow, 310, 'Ask Dealer / Project Type', 'ask_question',
                message_text='Is this for dealership, distribution, project supply, tender, contractor work, or resale?',
                input_validation_type='text',
                save_response=True,
                response_variable='dealer_project_type',
                max_attempts=2,
            )
            dealer_city = create_step(
                flow, 320, 'Ask Dealer Area', 'ask_question',
                message_text='Which city/state/territory are you covering or supplying to?',
                input_validation_type='text',
                save_response=True,
                response_variable='dealer_city',
                max_attempts=2,
            )
            dealer_requirement = create_step(
                flow, 330, 'Ask Dealer Requirement', 'ask_question',
                message_text='Please share expected product range, monthly volume, project size, or tender details.',
                input_validation_type='text',
                save_response=True,
                response_variable='dealer_requirement',
                max_attempts=2,
            )
            dealer_form = create_step(
                flow, 340, 'Send Lead Enquiry Form', 'send_form_link',
                message_text='Please complete this lead enquiry form so our business team has full details: {{form_url}}',
                form_id=forms.get('Lead Enquiry').id if forms.get('Lead Enquiry') else False,
            )
            dealer_lead = create_step(
                flow, 350, 'Create Dealer / Project Lead', 'create_lead',
                message_text=(
                    'Dealer/project enquiry from WhatsApp.\n'
                    'Type: {{dealer_project_type}}\n'
                    'City/territory: {{dealer_city}}\n'
                    'Requirement: {{dealer_requirement}}\n'
                    'Phone: {{phone}}'
                ),
            )

            order_menu = create_step(
                flow, 400, 'Order / Payment Menu', 'send_buttons',
                message_text='Choose what you need for order, invoice, or payment help.',
                button_header_text='Order Desk',
            )
            payment_step = create_step(
                flow, 410, 'Send Payment Link Or Guidance',
                'send_payment_link' if payment_enabled else 'send_text',
                message_text=(
                    'Please use this secure payment link: {{payment_url}}'
                    if payment_enabled
                    else 'Payment links are handled by our accounts team. Please share invoice/order reference and we will assist.'
                ),
                payment_mode='account_default',
            )
            order_ref = create_step(
                flow, 420, 'Ask Order Reference', 'ask_question',
                message_text='Please share your order number, quotation number, invoice number, or payment reference.',
                input_validation_type='text',
                save_response=True,
                response_variable='order_reference',
                max_attempts=2,
            )
            invoice_tag = create_step(flow, 430, 'Tag Invoice Help', 'assign_tag', assign_tag_id=tags['Invoice Help'].id)
            order_tag = create_step(flow, 440, 'Tag Order Help', 'assign_tag', assign_tag_id=tags['Order Help'].id)
            payment_tag = create_step(flow, 450, 'Tag Payment Follow-Up', 'assign_tag', assign_tag_id=tags['Payment Follow-up'].id)

            support_menu = create_step(
                flow, 500, 'Support / Warranty Menu', 'send_list',
                message_text='Please choose the closest support topic.',
                button_header_text='Support Desk',
                list_button_text='Select issue',
                list_section_title='Support Topics',
            )
            support_ref = create_step(
                flow, 510, 'Ask Support Reference', 'ask_question',
                message_text='Please share order, invoice, delivery, or project reference if available.',
                input_validation_type='text',
                save_response=True,
                response_variable='support_reference',
                max_attempts=2,
            )
            support_details = create_step(
                flow, 520, 'Ask Support Details', 'ask_question',
                message_text='Describe the issue clearly. Mention product, size, site, date, and what happened.',
                input_validation_type='text',
                save_response=True,
                response_variable='support_details',
                max_attempts=2,
            )
            support_form = create_step(
                flow, 530, 'Send Support Ticket Form', 'send_form_link',
                message_text='Please upload photos, invoice, delivery proof, or documents in this support form: {{form_url}}',
                form_id=forms.get('Support Ticket').id if forms.get('Support Ticket') else False,
            )
            support_tag = create_step(flow, 540, 'Tag Support Required', 'assign_tag', assign_tag_id=tags['Support Required'].id)
            warranty_tag = create_step(flow, 545, 'Tag Warranty Requested', 'assign_tag', assign_tag_id=tags['Warranty Requested'].id)
            product_issue_tag = create_step(flow, 550, 'Tag Product Issue', 'assign_tag', assign_tag_id=tags['Product Issue'].id)

            forms_menu = create_step(
                flow, 600, 'Forms / Upload Menu', 'send_list',
                message_text='Choose the form you want to open.',
                list_button_text='Choose form',
                list_section_title='Forms',
            )
            forms_tag = create_step(flow, 605, 'Tag Forms Shared', 'assign_tag', assign_tag_id=tags['Forms Shared'].id)
            form_quote = create_step(flow, 610, 'Open Quote Form', 'send_form_link',
                                     message_text='Quote request form: {{form_url}}',
                                     form_id=forms.get('Quote Request').id if forms.get('Quote Request') else False)
            form_support = create_step(flow, 620, 'Open Support Form', 'send_form_link',
                                       message_text='Support ticket form: {{form_url}}',
                                       form_id=forms.get('Support Ticket').id if forms.get('Support Ticket') else False)
            form_lead = create_step(flow, 630, 'Open Lead Form', 'send_form_link',
                                    message_text='Lead enquiry form: {{form_url}}',
                                    form_id=forms.get('Lead Enquiry').id if forms.get('Lead Enquiry') else False)
            form_catalogue = create_step(flow, 640, 'Open Catalogue Form', 'send_form_link',
                                         message_text='Catalogue request form: {{form_url}}',
                                         form_id=forms.get('Catalogue Request').id if forms.get('Catalogue Request') else False)
            form_feedback = create_step(flow, 650, 'Open Feedback Form', 'send_form_link',
                                        message_text='Feedback form: {{form_url}}',
                                        form_id=forms.get('Feedback').id if forms.get('Feedback') else False)

            feedback_prompt = create_step(
                flow, 700, 'Feedback Rating Menu', 'send_buttons',
                message_text='How was your experience with Fibera Composite India Pvt Ltd?',
                button_header_text='Feedback',
            )
            feedback_form = create_step(
                flow, 710, 'Send Feedback Form', 'send_form_link',
                message_text='Thank you. Please share details here: {{form_url}}',
                form_id=forms.get('Feedback').id if forms.get('Feedback') else False,
            )
            feedback_tag = create_step(flow, 720, 'Tag Feedback Received', 'assign_tag', assign_tag_id=tags['Feedback Received'].id)

            company_info = create_step(
                flow, 800, 'Company Info Reply', 'send_text',
                message_text=(
                    'Fibera Composite India Pvt Ltd manufactures FRP/composite products for infrastructure and project supply, '
                    'including manhole covers, drain/gully covers, FRP gratings, tank covers, and custom composite requirements.'
                ),
            )
            company_website = create_step(
                flow, 810, 'Company Website CTA', 'send_cta_url',
                message_text='Open our website/catalogue page for product information.',
                cta_button_text='Open Website',
                cta_button_url=shop_url,
            )

            agent_tag = create_step(flow, 900, 'Tag Agent Requested', 'assign_tag', assign_tag_id=tags['Agent Requested'].id)
            assign_team_step = create_step(flow, 910, 'Assign Available Team', 'assign_team')
            assign_fallback = create_step(flow, 920, 'Assign Fallback Agent', 'transfer', assign_user_id=assign_user.id)
            open_chat = create_step(flow, 930, 'Keep Chat Open', 'chat_status', chat_status='open')
            agent_confirm = create_step(
                flow, 940, 'Agent Handoff Confirmation', 'send_text',
                message_text='Thanks {{name}}. I have handed this chat to our team. A person will reply here shortly.',
            )
            end = create_step(flow, 999, 'End', 'end')

            route(business_tag, main_menu)
            route(catalogue_tag, website_tag)
            route(website_tag, website_link)
            route(website_link, catalog_message or catalogue_form)
            if catalog_message:
                route(catalog_message, catalogue_form)
            route(catalogue_form, catalogue_question)
            route(catalogue_question, catalogue_city)
            route(catalogue_city, catalogue_lead)
            route(catalogue_lead, assign_team_step)

            route(quote_tag, quote_product)
            route(quote_product, quote_size)
            route(quote_size, quote_qty)
            route(quote_qty, quote_city)
            route(quote_city, quote_timeline)
            route(quote_timeline, quote_contact_update)
            route(quote_contact_update, quote_lead)
            route(quote_lead, quote_qualified)
            route(quote_qualified, quote_form)
            route(quote_form, assign_team_step)

            route(dealer_tag, dealer_type)
            route(dealer_type, dealer_city)
            route(dealer_city, dealer_requirement)
            route(dealer_requirement, dealer_form)
            route(dealer_form, dealer_lead)
            route(dealer_lead, assign_team_step)

            route(payment_step, payment_tag)
            route(payment_tag, assign_team_step)
            route(order_ref, order_tag)
            route(order_tag, assign_team_step)
            route(invoice_tag, order_ref)

            route(support_ref, support_details)
            route(support_details, support_form)
            route(support_form, support_tag)
            route(support_tag, assign_team_step)
            route(warranty_tag, support_ref)
            route(product_issue_tag, support_ref)

            route(forms_tag, forms_menu)
            route(form_quote, assign_team_step)
            route(form_support, assign_team_step)
            route(form_lead, assign_team_step)
            route(form_catalogue, assign_team_step)
            route(form_feedback, end)

            route(feedback_form, feedback_tag)
            route(feedback_tag, end)
            route(company_info, company_website)
            route(company_website, end)
            route(agent_tag, assign_team_step)
            route(assign_team_step, assign_fallback)
            route(assign_fallback, open_chat)
            route(open_chat, agent_confirm)
            route(agent_confirm, end)

            main_menu.with_context(skip_canvas_sync=True).write({'fallback_step_id': free_text_router.id})
            free_text_router.with_context(skip_canvas_sync=True).write({
                'condition_true_step': quote_tag.id,
                'condition_false_step': agent_tag.id,
            })
            add_branches(free_text_router, [
                (10, 'Catalogue / Website', 'regex', 'catalog|catalogue|website|brochure|product', catalogue_tag),
                (20, 'Quote / Price', 'regex', 'price|quote|quotation|rate|cost', quote_tag),
                (30, 'Dealer / Project', 'regex', 'dealer|distributor|project|tender|bulk|contractor', dealer_tag),
                (40, 'Order / Payment', 'regex', 'payment|pay|invoice|order|delivery|tracking', order_menu),
                (50, 'Support / Warranty', 'regex', 'support|issue|warranty|complaint|problem|replacement', support_menu),
                (60, 'Feedback', 'regex', 'feedback|review|rating|experience', feedback_prompt),
            ])

            add_buttons(main_menu, [
                ('Catalogue / Website', 'fci_catalogue', 'Catalogue, shop, and website link', catalogue_tag),
                ('Quote / Price', 'fci_quote', 'Collect product, size, quantity, city', quote_tag),
                ('Dealer / Project', 'fci_dealer', 'Dealer, project, tender, bulk enquiry', dealer_tag),
                ('Order / Payment', 'fci_order', 'Invoice, payment, order reference', order_menu),
                ('Support / Warranty', 'fci_support', 'Support ticket, warranty, product issue', support_menu),
                ('Talk to Agent', 'fci_agent', 'Assign a human team member', agent_tag),
                ('Forms / Upload', 'fci_forms', 'Quote, support, catalogue, feedback forms', forms_tag),
                ('Feedback', 'fci_feedback', 'Share customer experience', feedback_prompt),
                ('Company Info', 'fci_company', 'About Fibera Composite India Pvt Ltd', company_info),
            ])
            add_buttons(order_menu, [
                ('Pay Now', 'fci_pay_now', 'Send payment link if configured', payment_step),
                ('Order Status', 'fci_order_status', 'Share order/delivery reference', order_ref),
                ('Invoice Help', 'fci_invoice_help', 'Invoice, payment, accounts support', invoice_tag),
            ])
            add_buttons(support_menu, [
                ('Product Issue', 'fci_product_issue', 'Quality, damage, fitment, technical concern', product_issue_tag),
                ('Delivery Issue', 'fci_delivery_issue', 'Dispatch, delivery, shortage, delay', support_ref),
                ('Warranty', 'fci_warranty', 'Warranty or replacement request', warranty_tag),
                ('Payment / Invoice', 'fci_support_invoice', 'Accounts or invoice-related support', invoice_tag),
                ('Talk to Agent', 'fci_support_agent', 'Human support handoff', agent_tag),
            ])
            add_buttons(forms_menu, [
                ('Quote Form', 'fci_form_quote', 'Detailed quotation request', form_quote),
                ('Support Form', 'fci_form_support', 'Issue details and uploads', form_support),
                ('Lead Form', 'fci_form_lead', 'Dealer/project/customer enquiry', form_lead),
                ('Catalogue Form', 'fci_form_catalogue', 'Specific catalogue request', form_catalogue),
                ('Feedback Form', 'fci_form_feedback', 'Rating and comments', form_feedback),
            ])
            add_buttons(feedback_prompt, [
                ('Good', 'fci_feedback_good', 'Positive feedback', feedback_form),
                ('Average', 'fci_feedback_average', 'Neutral feedback', feedback_form),
                ('Poor', 'fci_feedback_poor', 'Needs follow-up', feedback_form),
            ])
            created |= finish(flow)

        flow, is_new = create_flow(
            'FiberaFRP Full Business Assistant - Blueprint',
            'custom',
            'menu, business, fibera, hi, hello, start',
            'Inactive master bot covering catalogue, quotation, support, order/payment, dealer/project, and human handoff.',
            priority=65,
        )
        if is_new:
            menu = create_step(flow, 1, 'Main Business Menu', 'send_list',
                               message_text='Hi {{name}}, welcome to FiberaFRP. What would you like help with today?',
                               list_button_text='Choose option', list_section_title='Business Services')
            catalogue = create_step(flow, 10, 'Send Catalogue / Shop Link', 'send_cta_url',
                                    message_text='Please review our catalogue/shop. Reply with your requirement if you need pricing.',
                                    cta_button_text='Open Catalogue',
                                    cta_button_url=account.commerce_shop_url or 'https://fiberafrp.com')
            catalogue_tag = create_step(flow, 11, 'Tag Catalogue Interest', 'assign_tag', assign_tag_id=tags['Catalogue Requested'].id)
            quote_intro = create_step(flow, 20, 'Quote Intro', 'send_text',
                                      message_text='Sure. I will collect a few details so sales can prepare an accurate quotation.')
            quote_form = create_step(flow, 21, 'Send Quote Request Form', 'send_form_link',
                                     message_text='Please fill this quote request form with product, size, quantity, and city.',
                                     form_id=forms.get('Quote Request').id if forms.get('Quote Request') else False)
            quote_lead = create_step(flow, 22, 'Create Quote Lead', 'create_lead',
                                     message_text='WhatsApp quote request. Last reply: {{last_reply}}')
            order_menu = create_step(flow, 30, 'Order / Payment Help', 'send_buttons',
                                     message_text='Choose what you need for your order or payment.')
            payment = create_step(flow, 31, 'Send Payment Link', 'send_payment_link',
                                  message_text='Here is your secure payment link if an invoice or quotation is available.',
                                  payment_mode='account_default')
            order_handoff = create_step(flow, 32, 'Assign Order / Accounts Agent', 'transfer', assign_user_id=assign_user.id)
            support_form = create_step(flow, 40, 'Send Support Ticket Form', 'send_form_link',
                                       message_text='Please share issue details in this support form so we can help faster.',
                                       form_id=forms.get('Support Ticket').id if forms.get('Support Ticket') else False)
            support_transfer = create_step(flow, 41, 'Assign Support Agent', 'transfer', assign_user_id=assign_user.id)
            dealer_form = create_step(flow, 50, 'Send Lead Enquiry Form', 'send_form_link',
                                      message_text='Please share project/dealer details in this form.',
                                      form_id=forms.get('Lead Enquiry').id if forms.get('Lead Enquiry') else False)
            dealer_tag = create_step(flow, 51, 'Tag Dealer / Project Lead', 'assign_tag', assign_tag_id=tags['Dealer / Project Lead'].id)
            human = create_step(flow, 60, 'Human Handoff', 'transfer', assign_user_id=assign_user.id)
            end = create_step(flow, 99, 'End', 'end')
            route(catalogue, catalogue_tag)
            route(catalogue_tag, end)
            route(quote_intro, quote_form)
            route(quote_form, quote_lead)
            route(quote_lead, end)
            route(payment, end)
            route(order_handoff, end)
            route(support_form, support_transfer)
            route(support_transfer, end)
            route(dealer_form, dealer_tag)
            route(dealer_tag, end)
            route(human, end)
            add_buttons(menu, [
                ('Catalogue / Shop', 'menu_catalogue', 'Open catalogue or shop link', catalogue),
                ('New Quote', 'menu_quote', 'Collect details and create sales lead', quote_intro),
                ('Order / Payment', 'menu_order_payment', 'Payment or order support', order_menu),
                ('Support / Warranty', 'menu_support', 'Issue, delivery, warranty, complaint', support_form),
                ('Dealer / Project', 'menu_dealer_project', 'Dealer or project enquiry', dealer_form),
                ('Talk to Agent', 'menu_agent', 'Human handoff', human),
            ])
            add_buttons(order_menu, [
                ('Pay Now', 'pay_now', 'Send latest invoice/quote link', payment),
                ('Order Help', 'order_help', 'Assign order/accounts support', order_handoff),
                ('Talk to Agent', 'order_agent', 'Human handoff', human),
            ])
            created |= finish(flow)

        flow, is_new = create_flow(
            'FiberaFRP Quote Qualification - Blueprint',
            'sales',
            'quote, price, pricing, rate, enquiry, requirement',
            'Inactive quotation qualification bot that asks product, size, quantity, city, then creates CRM lead and sends quote form.',
            priority=70,
        )
        if is_new:
            intro = create_step(flow, 1, 'Quote Greeting', 'send_text',
                                message_text='Hi {{name}}, I can help with pricing. I will ask a few quick questions.')
            product = create_step(flow, 10, 'Ask Product Type', 'ask_question',
                                  message_text='Which product do you need? Example: manhole cover, gully cover, tank cover, FRP grating.',
                                  input_validation_type='text', save_response=True, response_variable='product_type')
            size = create_step(flow, 20, 'Ask Size / Load Rating', 'ask_question',
                               message_text='Please share size and load rating. Example: 600x600, 10T, heavy duty.',
                               input_validation_type='text', save_response=True, response_variable='size_load')
            qty = create_step(flow, 30, 'Ask Quantity', 'ask_question',
                              message_text='How many pieces do you need?',
                              input_validation_type='number', save_response=True, response_variable='quantity')
            city = create_step(flow, 40, 'Ask Delivery City', 'ask_question',
                               message_text='Which city or project location should we quote for?',
                               input_validation_type='city', save_response=True, response_variable='delivery_city')
            lead = create_step(flow, 50, 'Create CRM Lead', 'create_lead',
                               message_text='Qualified WhatsApp quote request:\nProduct: {{product_type}}\nSize/load: {{size_load}}\nQuantity: {{quantity}}\nCity: {{delivery_city}}\nPhone: {{phone}}')
            form_step = create_step(flow, 60, 'Send Quote Form', 'send_form_link',
                                    message_text='You can also upload drawings or BOQ here for accurate pricing.',
                                    form_id=forms.get('Quote Request').id if forms.get('Quote Request') else False)
            handoff = create_step(flow, 70, 'Assign Sales Agent', 'transfer', assign_user_id=assign_user.id)
            done = create_step(flow, 99, 'End', 'end')
            route(intro, product)
            route(product, size)
            route(size, qty)
            route(qty, city)
            route(city, lead)
            route(lead, form_step)
            route(form_step, handoff)
            route(handoff, done)
            created |= finish(flow)

        flow, is_new = create_flow(
            'FiberaFRP Support And Warranty Desk - Blueprint',
            'support',
            'support, help, issue, complaint, warranty, replacement, problem',
            'Inactive support bot that classifies issue type, collects reference/details, sends support form, tags and assigns agent.',
            priority=75,
        )
        if is_new:
            menu = create_step(flow, 1, 'Support Issue Menu', 'send_list',
                               message_text='Sorry you are facing an issue. Please choose the closest category.',
                               list_button_text='Select issue', list_section_title='Support Topics')
            order_ref = create_step(flow, 10, 'Ask Order / Invoice Reference', 'ask_question',
                                    message_text='Please share your order number, invoice number, or delivery reference if available.',
                                    input_validation_type='text', save_response=True, response_variable='support_reference')
            details = create_step(flow, 20, 'Ask Issue Details', 'ask_question',
                                  message_text='Please describe the issue. You can mention product, location, date, and what happened.',
                                  input_validation_type='text', save_response=True, response_variable='support_details')
            form_step = create_step(flow, 30, 'Send Support Form', 'send_form_link',
                                    message_text='Please upload photos/documents here if needed.',
                                    form_id=forms.get('Support Ticket').id if forms.get('Support Ticket') else False)
            tag = create_step(flow, 40, 'Tag Support Required', 'assign_tag', assign_tag_id=tags['Support Required'].id)
            assign = create_step(flow, 50, 'Assign Support Agent', 'transfer', assign_user_id=assign_user.id)
            reply = create_step(flow, 60, 'Support Confirmation', 'send_text',
                                message_text='Thanks {{name}}. I have assigned this to our support team. A team member will reply here shortly.')
            done = create_step(flow, 99, 'End', 'end')
            route(order_ref, details)
            route(details, form_step)
            route(form_step, tag)
            route(tag, assign)
            route(assign, reply)
            route(reply, done)
            add_buttons(menu, [
                ('Order Status', 'support_order_status', 'Order or delivery update', order_ref),
                ('Payment / Invoice', 'support_payment_invoice', 'Payment, invoice, or accounts issue', order_ref),
                ('Product Issue', 'support_product_issue', 'Product quality or fitment issue', order_ref),
                ('Warranty / Replacement', 'support_warranty', 'Warranty or replacement request', order_ref),
                ('Talk to Agent', 'support_agent', 'Human support handoff', assign),
            ])
            created |= finish(flow)

        flow, is_new = create_flow(
            'FiberaFRP Payment And Order Follow-Up - Blueprint',
            'notification',
            'payment, pay, invoice, order, tracking, delivery',
            'Inactive payment/order bot that can send payment links, collect order reference, and route to accounts/support.',
            priority=60,
        )
        if is_new:
            menu = create_step(flow, 1, 'Payment / Order Menu', 'send_buttons',
                               message_text='How can we help with your payment or order?')
            pay = create_step(flow, 10, 'Send Payment Link', 'send_payment_link',
                              message_text='If a payable invoice or quotation is available, here is the secure payment link.',
                              payment_mode='account_default')
            ask_order = create_step(flow, 20, 'Ask Order Reference', 'ask_question',
                                    message_text='Please share your order, invoice, quotation, or payment reference.',
                                    input_validation_type='text', save_response=True, response_variable='order_reference')
            tag = create_step(flow, 30, 'Tag Payment Follow-up', 'assign_tag', assign_tag_id=tags['Payment Follow-up'].id)
            assign = create_step(flow, 40, 'Assign Accounts / Order Agent', 'transfer', assign_user_id=assign_user.id)
            reply = create_step(flow, 50, 'Follow-up Confirmation', 'send_text',
                                message_text='Thanks. I have shared this with our team. They will check and reply here.')
            done = create_step(flow, 99, 'End', 'end')
            route(pay, done)
            route(ask_order, tag)
            route(tag, assign)
            route(assign, reply)
            route(reply, done)
            add_buttons(menu, [
                ('Pay Now', 'payment_pay_now', 'Send payment link', pay),
                ('Order Status', 'payment_order_status', 'Collect order reference', ask_order),
                ('Invoice Help', 'payment_invoice_help', 'Assign accounts team', ask_order),
            ])
            created |= finish(flow)

        flow, is_new = create_flow(
            'FiberaFRP Feedback And Review - Blueprint',
            'survey',
            'feedback, review, rating, experience',
            'Inactive feedback bot that collects customer rating and sends feedback form.',
            priority=35,
        )
        if is_new:
            ask = create_step(flow, 1, 'Ask Rating', 'send_buttons',
                              message_text='How was your experience with FiberaFRP?')
            good = create_step(flow, 10, 'Positive Feedback Reply', 'send_text',
                               message_text='Thank you. We are glad to hear that. Please share any comments in the feedback form.')
            bad = create_step(flow, 20, 'Issue Feedback Reply', 'send_text',
                              message_text='Thank you for telling us. Please share details so we can improve and follow up.')
            form_step = create_step(flow, 30, 'Send Feedback Form', 'send_form_link',
                                    message_text='Please fill this short feedback form.',
                                    form_id=forms.get('Feedback').id if forms.get('Feedback') else False)
            tag = create_step(flow, 40, 'Tag Feedback Received', 'assign_tag', assign_tag_id=tags['Feedback Received'].id)
            done = create_step(flow, 99, 'End', 'end')
            route(good, form_step)
            route(bad, form_step)
            route(form_step, tag)
            route(tag, done)
            add_buttons(ask, [
                ('Good', 'feedback_good', 'Positive experience', good),
                ('Average', 'feedback_average', 'Needs review', bad),
                ('Poor', 'feedback_poor', 'Needs immediate follow-up', bad),
            ])
            created |= finish(flow)

        if created:
            _logger.info("Created %s advanced FiberaFRP business flow blueprint(s).", len(created))
        return created

    def _match_inbound_message(self, message):
        self.ensure_one()
        if not self.active or self.account_id != message.account_id:
            return False

        incoming_text = (message.body or '').lower()
        payload = (message.button_payload or message.list_item_id or '').lower()
        
        if self.trigger_type == 'keyword':
            keywords = [k.strip().lower() for k in (self.keywords or '').split(',') if k.strip()]
            # Match against body text OR button payload
            return bool(keywords) and (any(kw in incoming_text for kw in keywords) or any(kw == payload for kw in keywords))
        if self.trigger_type == 'first_message':
            inbound_count = self.env['whatsapp.message'].search_count([
                ('account_id', '=', message.account_id.id),
                ('phone_number', '=', message.phone_number),
                ('direction', '=', 'inbound'),
            ])
            return inbound_count <= 1
        if self.trigger_type in ('manual', 'schedule', 'webhook'):
            _logger.debug("Flow '%s' trigger '%s' is not executed by inbound message runtime.", self.name, self.trigger_type)
        return False

    @api.model
    def trigger_for_message(self, message):
        flows = self.search([
            ('active', '=', True),
            ('account_id', '=', message.account_id.id),
            ('trigger_type', 'in', ['keyword', 'first_message']),
        ], order='priority desc, id asc')

        for flow in flows:
            if flow._match_inbound_message(message):
                flow._execute_flow(message, source='inbound')
                return flow
        return False

    @api.model
    def resume_for_message(self, message):
        """Resume the most recent pending flow execution for this conversation."""
        if not message or message.direction != 'inbound' or not message.account_id:
            return False

        stale_before = fields.Datetime.now() - timedelta(hours=24)
        domain = [
            ('status', '=', 'pending'),
            ('flow_id.account_id', '=', message.account_id.id),
            ('phone_number', '=', message.phone_number),
        ]
        stale_logs = self.env['whatsapp.bot.flow.log'].search(domain + [('started_date', '<', stale_before)])
        if stale_logs:
            stale_logs.write({
                'status': 'failed',
                'completed_date': fields.Datetime.now(),
                'wake_at': False,
                'error_message': 'Superseded automatically after 24 hours so new inbound messages can trigger fresh flows.',
            })

        pending_logs = self.env['whatsapp.bot.flow.log'].search(
            domain + [('started_date', '>=', stale_before)],
            order='id desc',
            limit=20,
        ).filtered(
            lambda log: not log.wake_at or log.current_step.action_type in ('ask_question', 'wait_response', 'send_buttons', 'send_list')
        )[:10]
        if message.chat_id_ref:
            pending_log = pending_logs.filtered(
                lambda log: not log.chat_id or log.chat_id.id == message.chat_id_ref.id
            )[:1]
        else:
            pending_log = pending_logs[:1]
        if not pending_log:
            return False

        if (
            pending_log.current_step.action_type in ('send_buttons', 'send_list')
            and not (message.button_payload or message.list_item_id)
        ):
            waiting_step = pending_log.current_step
            if not waiting_step.fallback_step_id:
                pending_log.write({
                    'status': 'failed',
                    'completed_date': fields.Datetime.now(),
                    'wake_at': False,
                    'error_message': (
                        f'Superseded by normal text while waiting for button/list reply '
                        f'at step "{waiting_step.name}".'
                    ),
                })
                return False

        flow = pending_log.flow_id
        flow._resume_from_log(pending_log, message, source='inbound_resume')
        return flow

    def start_flow_for_participant(self, participant, message):
        """Initialize a flow in pending state for a campaign participant or direct message."""
        self.ensure_one()
        first_step = self._get_first_step()
        if not first_step:
            return False
            
        variables = self._build_execution_variables(message)
        
        partner_id = False
        if participant:
             partner_id = participant.partner_id.id if participant.partner_id else False
        elif message.partner_id:
             partner_id = message.partner_id.id
             
        if participant and participant.partner_id:
            phone = getattr(participant.partner_id, 'mobile', False) or participant.partner_id.phone
        else:
            phone = message.phone_number
        phone = self.env['whatsapp.message']._normalize_phone(phone, account=self.account_id, strict=False)
        
        log = self.env['whatsapp.bot.flow.log'].create({
            'flow_id': self.id,
            'chat_id': message.chat_id_ref.id if message.chat_id_ref else False,
            'partner_id': partner_id,
            'phone_number': phone,
            'status': 'pending', 
            'current_step': first_step.id,
            'total_steps': len(self.step_ids),
            'variables': json.dumps(variables),
        })
        self.trigger_count += 1
        return log

    def _resume_from_log(self, log, message, source='manual_resume'):
        self.ensure_one()
        if log.flow_id != self:
            raise ValueError("Flow log does not belong to this flow.")

        waiting_step = log.current_step
        if not waiting_step or waiting_step.flow_id != self:
            raise ValueError(f"Pending log {log.id} has no valid current step.")

        try:
            variables = json.loads(log.variables) if log.variables else {}
        except Exception:
            variables = {}
        if not isinstance(variables, dict):
            variables = {}

        variables.update(self._build_execution_variables(message))

        inbound_value = message.button_payload or message.list_item_id or message.body or ''
        if waiting_step.save_response and waiting_step.response_variable:
            variables[waiting_step.response_variable] = inbound_value
        elif waiting_step.action_type in ('wait_response', 'ask_question'):
            variables['last_reply'] = inbound_value

        resume_step = False
        if waiting_step.action_type == 'ask_question':
            if waiting_step.response_variable:
                variables[waiting_step.response_variable] = inbound_value
            if not self._validate_ask_answer(waiting_step, message, inbound_value):
                attempt_key = f'ask_{waiting_step.id}_attempts'
                attempts = int(variables.get(attempt_key) or 0) + 1
                variables[attempt_key] = attempts
                max_attempts = max(1, waiting_step.max_attempts or 1)
                if attempts >= max_attempts and waiting_step.invalid_step_id:
                    resume_step = waiting_step.invalid_step_id
                else:
                    if waiting_step.invalid_message:
                        self._send_flow_text_message(
                            message,
                            waiting_step.invalid_message,
                            partner=message.partner_id,
                            chat=message.chat_id_ref,
                        )
                    log.write({
                        'status': 'pending',
                        'variables': json.dumps(variables),
                    })
                    return log

        reply_token = (message.button_payload or message.list_item_id or '').strip()
        if reply_token:
            source_button_step = self.step_ids.filtered(
                lambda step: step.action_type in ('send_buttons', 'send_list') and step.next_step_id.id == waiting_step.id
            )[:1]
            if not source_button_step and waiting_step.action_type in ('send_buttons', 'send_list'):
                source_button_step = waiting_step

            if source_button_step:
                button = source_button_step.button_ids.filtered(
                    lambda btn: (btn.button_id or '').strip() == reply_token and btn.next_step_id
                )[:1]
                if button:
                    resume_step = button.next_step_id

        if waiting_step.action_type in ('send_buttons', 'send_list'):
            if not reply_token:
                if waiting_step.fallback_step_id:
                    resume_step = waiting_step.fallback_step_id
                else:
                    log.write({
                        'status': 'pending',
                        'variables': json.dumps(variables),
                    })
                    return log
            elif not resume_step:
                _logger.info(
                    "Flow '%s' received unmatched interactive payload '%s' for step '%s'.",
                    self.name, reply_token, waiting_step.name,
                )
                if waiting_step.fallback_step_id:
                    resume_step = waiting_step.fallback_step_id
                else:
                    log.write({
                        'status': 'pending',
                        'variables': json.dumps(variables),
                    })
                    return log

        if waiting_step.action_type == 'ask_question' and not resume_step:
            resume_step = waiting_step.next_step_id

        if not resume_step:
            resume_step = self._get_next_step(waiting_step)

        log.write({
            'status': 'running',
            'chat_id': message.chat_id_ref.id if message.chat_id_ref else log.chat_id.id if log.chat_id else False,
            'partner_id': message.partner_id.id if message.partner_id else log.partner_id.id if log.partner_id else False,
            'phone_number': message.phone_number or log.phone_number,
            'variables': json.dumps(variables),
        })

        if not resume_step:
            log.write({
                'status': 'success',
                'completed_date': fields.Datetime.now(),
            })
            self.success_count += 1
            return log

        visited_ids = {waiting_step.id}
        completed_steps = log.completed_steps
        current_step = resume_step

        try:
            while current_step:
                if current_step.id in visited_ids:
                    raise ValueError(f'Flow "{self.name}" entered a step loop at "{current_step.name}".')
                visited_ids.add(current_step.id)

                log.write({
                    'current_step': current_step.id,
                    'variables': json.dumps(variables),
                })

                result = self._execute_step_with_retry(current_step, message, variables, log, source=source)
                completed_steps += 1
                log.write({'completed_steps': completed_steps})

                if result.get('stop'):
                    new_status = result.get('status', 'pending')
                    finish_vals = {
                        'status': new_status,
                        'variables': json.dumps(variables),
                    }
                    if new_status != 'pending':
                        finish_vals['completed_date'] = fields.Datetime.now()
                    log.write(finish_vals)
                    if new_status == 'success':
                        self.success_count += 1
                    return log

                current_step = result.get('next_step') or self._get_next_step(current_step)

            log.write({
                'status': 'success',
                'completed_date': fields.Datetime.now(),
                'variables': json.dumps(variables),
            })
            self.success_count += 1
            return log
        except Exception as exc:
            _logger.error("Bot flow '%s' resume failed: %s", self.name, exc)
            log.write({
                'status': 'failed',
                'error_message': str(exc),
                'completed_date': fields.Datetime.now(),
                'variables': json.dumps(variables),
            })
            self.failed_count += 1
            raise

    def _resume_delayed_log(self, log):
        self.ensure_one()
        if log.flow_id != self or log.status != 'pending' or not log.current_step:
            return log

        try:
            variables = json.loads(log.variables) if log.variables else {}
        except Exception:
            variables = {}
        if not isinstance(variables, dict):
            variables = {}

        if log.current_step.action_type in ('ask_question', 'wait_response', 'send_buttons', 'send_list'):
            timeout_step = log.current_step.timeout_step_id or log.current_step.fallback_step_id
            if timeout_step:
                variables['no_reply'] = True
                log.write({
                    'status': 'running',
                    'wake_at': False,
                    'current_step': timeout_step.id,
                    'variables': json.dumps(variables),
                })
                current_step = timeout_step
            else:
                log.write({
                    'status': 'failed',
                    'wake_at': False,
                    'completed_date': fields.Datetime.now(),
                    'error_message': f'No reply received for step "{log.current_step.name}".',
                    'variables': json.dumps(variables),
                })
                self.failed_count += 1
                return log

        message = self.env['whatsapp.message'].new({
            'account_id': self.account_id.id,
            'phone_number': log.phone_number,
            'partner_id': log.partner_id.id if log.partner_id else False,
            'chat_id_ref': log.chat_id.id if log.chat_id else False,
            'body': variables.get('incoming_text') or '',
            'direction': 'inbound',
            'message_type': 'text',
        })

        current_step = locals().get('current_step') or log.current_step
        completed_steps = log.completed_steps
        visited_ids = set()
        log.write({'status': 'running', 'wake_at': False})

        try:
            while current_step:
                if current_step.id in visited_ids:
                    raise ValueError(f'Flow "{self.name}" entered a step loop at "{current_step.name}".')
                visited_ids.add(current_step.id)

                log.write({
                    'current_step': current_step.id,
                    'variables': json.dumps(variables),
                })

                result = self._execute_step_with_retry(current_step, message, variables, log, source='delayed_resume')
                completed_steps += 1
                log.write({'completed_steps': completed_steps})

                if result.get('stop'):
                    new_status = result.get('status', 'pending')
                    finish_vals = {
                        'status': new_status,
                        'variables': json.dumps(variables),
                    }
                    if new_status != 'pending':
                        finish_vals['completed_date'] = fields.Datetime.now()
                        finish_vals['wake_at'] = False
                    log.write(finish_vals)
                    if new_status == 'success':
                        self.success_count += 1
                    return log

                current_step = result.get('next_step') or self._get_next_step(current_step)

            log.write({
                'status': 'success',
                'wake_at': False,
                'completed_date': fields.Datetime.now(),
                'variables': json.dumps(variables),
            })
            self.success_count += 1
            return log
        except Exception as exc:
            _logger.error("Delayed bot flow '%s' failed: %s", self.name, exc)
            log.write({
                'status': 'failed',
                'wake_at': False,
                'error_message': str(exc),
                'completed_date': fields.Datetime.now(),
                'variables': json.dumps(variables),
            })
            self.failed_count += 1
            raise

    def _get_first_step(self):
        self.ensure_one()
        return self.step_ids.sorted('step_number')[:1]

    def _get_next_step(self, step):
        self.ensure_one()
        if step.next_step_id:
            return step.next_step_id
        if any(self.step_ids.mapped('node_id')):
            return False
        return self.step_ids.filtered(lambda s: s.step_number > step.step_number).sorted('step_number')[:1]

    def _build_execution_variables(self, message):
        partner = message.partner_id
        return {
            'incoming_text': message.body or '',
            'button_payload': message.button_payload or message.list_item_id or '',
            'last_reply': message.button_payload or message.list_item_id or message.body or '',
            'partner_name': partner.name if partner else '',
            'name': partner.name if partner else '',
            'email': partner.email if partner else '',
            'company': partner.company_name if partner else '',
            'phone_number': message.phone_number or '',
            'phone': message.phone_number or '',
            'chat_id': message.chat_id_ref.id if message.chat_id_ref else False,
        }

    def _json_path_value(self, payload, path):
        current = payload
        for part in (path or '').split('.'):
            part = part.strip()
            if not part:
                continue
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except Exception:
                    return False
            else:
                return False
        return current

    def _send_flow_text_message(self, message, text, partner=False, chat=False):
        partner = partner or message.partner_id
        chat = chat or message.chat_id_ref
        rendered = self._render_flow_text(
            text or '',
            partner=partner,
            message=message,
            variables=None,
        )
        outbound = self.env['whatsapp.message'].sudo().create({
            'account_id': self.account_id.id,
            'phone_number': message.phone_number,
            'partner_id': partner.id if partner else False,
            'chat_id_ref': chat.id if chat else False,
            'message_type': 'text',
            'body': rendered,
            'direction': 'outbound',
            'is_automated': True,
        })
        outbound.action_send()
        return outbound

    def _condition_matches(self, source_value, operator, expected):
        source = '' if source_value in (False, None) else str(source_value)
        target = '' if expected in (False, None) else str(expected)
        source_l = source.lower()
        target_l = target.lower()
        operator = operator or 'contains'
        if operator == 'blank':
            return not source.strip()
        if operator == 'not_blank':
            return bool(source.strip())
        if operator == 'equals':
            return source_l == target_l
        if operator == 'not_equals':
            return source_l != target_l
        if operator == 'starts_with':
            return source_l.startswith(target_l)
        if operator == 'ends_with':
            return source_l.endswith(target_l)
        if operator == 'regex':
            try:
                return bool(re.search(target, source, flags=re.IGNORECASE))
            except re.error:
                return False
        if operator in ('greater_than', 'less_than'):
            try:
                left = float(source)
                right = float(target)
            except Exception:
                return False
            return left > right if operator == 'greater_than' else left < right
        return target_l in source_l

    def _step_condition_value(self, step, message, variables):
        source = step.condition_source or 'last_reply'
        if source == 'incoming_text':
            return message.body or variables.get('incoming_text') or ''
        if source == 'button_payload':
            return message.button_payload or message.list_item_id or variables.get('button_payload') or ''
        if source == 'variable':
            return variables.get(step.condition_variable or step.condition_value or '') or ''
        return variables.get('last_reply') or message.body or message.button_payload or message.list_item_id or ''

    def _validate_ask_answer(self, step, message, value):
        value = value or ''
        validation_type = step.input_validation_type or 'text'
        if validation_type == 'text':
            return bool(str(value).strip())
        if validation_type == 'number':
            try:
                float(str(value).replace(',', '').strip())
                return True
            except Exception:
                return False
        if validation_type == 'email':
            return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', str(value).strip()))
        if validation_type == 'phone':
            return len(re.sub(r'\D+', '', str(value))) >= 8
        if validation_type == 'city':
            return bool(re.match(r'^[A-Za-z][A-Za-z\s\-.]{1,80}$', str(value).strip()))
        if validation_type == 'media':
            return message.message_type in ('image', 'video', 'document', 'audio') or bool(message.media_url)
        if validation_type == 'location':
            return message.message_type == 'location' or '[Location:' in (message.body or '')
        return True

    def _write_contact_attribute(self, partner, message, key, value, variables=None):
        key = (key or '').strip()
        if not key:
            return
        rendered_value = self._render_flow_text(
            value or '',
            partner=partner,
            message=message,
            variables=variables or {},
        )
        for record, field_name in (
            (partner, 'whatsapp_custom_attributes'),
            (
                self.env['whatsapp.contact'].sudo().search([
                    '|', ('partner_id', '=', partner.id if partner else 0),
                    ('phone_number', '=', message.phone_number),
                ], limit=1),
                'custom_attributes',
            ),
        ):
            if not record:
                continue
            try:
                attrs = json.loads(getattr(record, field_name) or '{}')
            except Exception:
                attrs = {}
            if not isinstance(attrs, dict):
                attrs = {}
            attrs[key] = rendered_value
            record.sudo().write({field_name: json.dumps(attrs, ensure_ascii=False, sort_keys=True)})

    def _least_busy_team_user(self, step):
        members = step.assign_team_member_ids
        if not members:
            members = self.env['whatsapp.team.member'].sudo().search([
                ('account_id', '=', self.account_id.id),
                ('is_available', '=', True),
                ('can_send_messages', '=', True),
                ('user_id', '!=', False),
            ])
        members = members.filtered(lambda member: member.user_id and member.is_available)
        if not members:
            return False
        chat_model = self.env['whatsapp.chat'].sudo()
        ranked = sorted(
            members,
            key=lambda member: chat_model.search_count([
                ('assigned_user_id', '=', member.user_id.id),
                ('state', '=', 'open'),
            ]),
        )
        return ranked[0].user_id if ranked else False

    def _execute_step_with_retry(self, step, message, variables, log, source='manual'):
        attempts = self.max_retries if self.retry_on_failure else 1
        attempts = max(1, attempts)
        last_error = False

        for attempt in range(1, attempts + 1):
            try:
                return self._execute_step(step, message, variables, log, source=source)
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                _logger.warning(
                    "Flow '%s' step '%s' failed on attempt %s/%s, retrying: %s",
                    self.name, step.name, attempt, attempts, exc,
                )

        if last_error:
            raise last_error
        return {'stop': False}

    def _execute_flow(self, message, source='manual'):
        self.ensure_one()

        first_step = self._get_first_step()
        if not first_step:
            raise ValueError(f'Flow "{self.name}" has no steps to execute.')

        variables = self._build_execution_variables(message)
        log = self.env['whatsapp.bot.flow.log'].create({
            'flow_id': self.id,
            'chat_id': message.chat_id_ref.id if message.chat_id_ref else False,
            'partner_id': message.partner_id.id if message.partner_id else False,
            'phone_number': message.phone_number,
            'status': 'running',
            'total_steps': len(self.step_ids),
            'variables': json.dumps(variables),
        })

        self.write({'trigger_count': self.trigger_count + 1})

        current_step = first_step
        visited_ids = set()

        try:
            while current_step:
                if current_step.id in visited_ids:
                    raise ValueError(f'Flow "{self.name}" entered a step loop at "{current_step.name}".')
                visited_ids.add(current_step.id)

                log.write({
                    'current_step': current_step.id,
                    'variables': json.dumps(variables),
                })

                result = self._execute_step_with_retry(current_step, message, variables, log, source=source)
                log.completed_steps += 1

                if result.get('stop'):
                    stop_status = result.get('status', 'pending')
                    finish_vals = {
                        'status': stop_status,
                        'variables': json.dumps(variables),
                    }
                    if stop_status != 'pending':
                        finish_vals['completed_date'] = fields.Datetime.now()
                    log.write(finish_vals)
                    if stop_status == 'success':
                        self.success_count += 1
                    return log

                current_step = result.get('next_step') or self._get_next_step(current_step)

            log.write({
                'status': 'success',
                'completed_date': fields.Datetime.now(),
                'variables': json.dumps(variables),
            })
            self.success_count += 1
            return log
        except Exception as exc:
            _logger.error("Bot flow '%s' failed: %s", self.name, exc)
            log.write({
                'status': 'failed',
                'error_message': str(exc),
                'completed_date': fields.Datetime.now(),
                'variables': json.dumps(variables),
            })
            self.failed_count += 1
            raise

    def _execute_step(self, step, message, variables, log, source='manual'):
        self.ensure_one()
        account = self.account_id
        chat = message.chat_id_ref
        partner = message.partner_id

        if step.action_type == 'send_text':
            text = self._render_flow_text(
                step.message_text or 'Hello from your WhatsApp automation.',
                partner=partner,
                message=message,
                variables=variables,
            )
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'text',
                'body': text,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'send_template':
            if not step.template_id:
                raise ValueError(f'Step "{step.name}" is missing a template.')
            template_payload = step.template_id._prepare_send_payload(partner=partner)
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'template',
                'body': step.template_id.body,
                'template_id': step.template_id.id,
                'template_name': step.template_id._get_send_template_name(),
                'template_language': step.template_id._get_send_language_code(),
                'raw_data': json.dumps(template_payload),
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'send_media':
            if not step.media_id:
                raise ValueError(f'Step "{step.name}" is missing media.')
            caption = self._render_flow_text(
                step.message_text or '',
                partner=partner,
                message=message,
                variables=variables,
            )
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': step.media_id.media_type,
                'media_file': step.media_id.media_file,
                'media_filename': step.media_id.media_filename,
                'caption': caption or False,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'send_buttons':
            special_buttons = step.button_ids.filtered(lambda btn: btn.button_action in ('url', 'catalog_product'))
            if special_buttons:
                if len(special_buttons) > 1 or len(step.button_ids) > 1:
                    raise ValueError(
                        f'Step "{step.name}" can send either quick replies or one URL/product action button, not a mixed set.'
                    )
                special_button = special_buttons[0]
                prompt = self._render_flow_text(
                    step.message_text or 'Please review this option.',
                    partner=partner,
                    message=message,
                    variables=variables,
                )
                outbound = self.env['whatsapp.message'].create({
                    'account_id': account.id,
                    'phone_number': message.phone_number,
                    'partner_id': partner.id if partner else False,
                    'chat_id_ref': chat.id if chat else False,
                    'message_type': 'interactive',
                    'body': prompt,
                    'direction': 'outbound',
                    'is_automated': True,
                })
                if special_button.button_action == 'url':
                    outbound._prepare_interactive_cta_url_payload(
                        prompt,
                        special_button.name or step.cta_button_text or 'Open',
                        special_button.url,
                        header_text=step.button_header_text,
                        footer_text=step.button_footer_text,
                    )
                else:
                    outbound._prepare_interactive_product_payload(
                        prompt,
                        special_button.catalog_id or account.commerce_catalog_id,
                        special_button.product_retailer_id,
                        footer_text=step.button_footer_text,
                    )
                outbound.action_send()
                return {'stop': False, 'next_step': special_button.next_step_id or step.next_step_id}

            buttons = []
            for index, button in enumerate(step.button_ids[:3]):
                buttons.append({
                    'id': button.button_id or f'flow_{self.id}_step_{step.id}_{index}',
                    'title': button.name,
                })
            if not buttons:
                raise ValueError(f'Step "{step.name}" has no buttons configured.')
            prompt = self._render_flow_text(
                step.message_text or 'Please choose an option.',
                partner=partner,
                message=message,
                variables=variables,
            )
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'interactive',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound._prepare_interactive_payload(
                outbound.body,
                buttons,
                header_text=step.button_header_text,
                footer_text=step.button_footer_text,
            )
            outbound.action_send()
            return {'stop': True, 'status': 'pending'}

        elif step.action_type == 'send_cta_url':
            prompt = self._render_flow_text(
                step.message_text or 'Please open this link.',
                partner=partner,
                message=message,
                variables=variables,
            )
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'interactive',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound._prepare_interactive_cta_url_payload(
                prompt,
                step.cta_button_text or 'Open',
                step.cta_button_url or account.commerce_shop_url,
                header_text=step.button_header_text,
                footer_text=step.button_footer_text,
            )
            outbound.action_send()
            return {'stop': False}

        elif step.action_type == 'send_form_link':
            form = step.form_id or account.default_form_id
            if not form:
                raise ValueError(f'Step "{step.name}" requires a form or account default form.')
            form_url = form.public_url
            if not form_url:
                raise ValueError(f'Form "{form.display_name}" does not have a public URL.')
            prompt = self._render_flow_text(
                step.message_text or 'Please fill this short form so our team can help you faster: {{form_url}}',
                partner=partner,
                message=message,
                variables=dict(variables or {}, form_url=form_url),
            )
            prompt = prompt.replace('{{form_url}}', form_url)
            if form_url not in prompt:
                prompt = "%s\n%s" % (prompt.rstrip(), form_url)
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'text',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            return {'stop': False}

        elif step.action_type == 'send_payment_link':
            if not partner:
                raise ValueError(f'Step "{step.name}" needs a linked customer before sending a payment link.')
            payment_mode = step.payment_mode or 'account_default'
            payment_url = account._get_payment_link(partner=partner, mode=payment_mode)
            default_body = account._build_payment_link_message(partner=partner, mode=payment_mode)
            prompt = self._render_flow_text(
                step.message_text or default_body,
                partner=partner,
                message=message,
                variables=dict(variables or {}, payment_url=payment_url),
            )
            prompt = prompt.replace('{{payment_url}}', payment_url)
            if payment_url not in prompt:
                prompt = "%s\n%s" % (prompt.rstrip(), payment_url)
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'text',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            return {'stop': False}

        elif step.action_type == 'send_list':
            rows = []
            for index, button in enumerate(step.button_ids[:10]):
                rows.append({
                    'id': button.button_id or f'flow_{self.id}_step_{step.id}_{index}',
                    'title': button.name,
                    'description': button.description or '',
                })
            if not rows:
                raise ValueError(f'Step "{step.name}" has no list rows configured.')
            prompt = self._render_flow_text(
                step.message_text or 'Please choose an option.',
                partner=partner,
                message=message,
                variables=variables,
            )
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'interactive',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound._prepare_interactive_list_payload(
                outbound.body,
                rows,
                button_text=step.list_button_text or 'Choose',
                section_title=step.list_section_title or 'Options',
                header_text=step.button_header_text,
                footer_text=step.button_footer_text,
            )
            outbound.action_send()
            return {'stop': True, 'status': 'pending'}

        elif step.action_type == 'wait_response':
            return {'stop': True, 'status': 'pending'}

        elif step.action_type == 'ask_question':
            prompt = self._render_flow_text(
                step.message_text or 'Please share your answer.',
                partner=partner,
                message=message,
                variables=variables,
            )
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'text',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            vals = {
                'current_step': step.id,
                'variables': json.dumps(variables),
            }
            if step.timeout_minutes and step.timeout_minutes > 0:
                vals['wake_at'] = fields.Datetime.now() + timedelta(minutes=step.timeout_minutes)
            log.write(vals)
            return {'stop': True, 'status': 'pending'}

        elif step.action_type == 'condition':
            source_value = self._step_condition_value(step, message, variables)
            for branch in step.condition_branch_ids.sorted('sequence'):
                if self._condition_matches(source_value, branch.operator, branch.value):
                    return {'next_step': branch.next_step_id, 'stop': False}

            matched = self._condition_matches(source_value, step.condition_operator, step.condition_value)
            if step.condition_type == 'keyword_match' and step.condition_value:
                keywords = [k.strip().lower() for k in (step.condition_value or '').split(',') if k.strip()]
                matched = any(keyword in str(source_value).lower() for keyword in keywords)
            elif step.condition_type == 'json_path':
                matched = bool(variables.get(step.condition_value))

            return {
                'next_step': step.condition_true_step if matched else step.condition_false_step,
                'stop': False
            }

        elif step.action_type == 'transfer':
            if chat and step.assign_user_id:
                chat.write({'assigned_user_id': step.assign_user_id.id, 'state': 'open'})
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'assign_team':
            user = self._least_busy_team_user(step)
            if chat and user:
                previous_user = chat.assigned_user_id
                chat.write({'assigned_user_id': user.id, 'state': 'open'})
                self.env['whatsapp.conversation.assignment'].sudo().create({
                    'chat_id': chat.id,
                    'assigned_user_id': user.id,
                    'assigned_by': self.env.user.id,
                    'previous_user_id': previous_user.id if previous_user else False,
                    'transfer_reason': 'bot',
                    'transfer_notes': f'Assigned by flow step: {step.name}',
                })
            return {'stop': False}

        elif step.action_type == 'create_lead':
            if not self.env['crm.lead'].search_count([
                ('type', '=', 'lead'),
                '|', ('partner_id', '=', partner.id if partner else False), ('phone', '=', message.phone_number),
                ('probability', '<', 100),
            ]):
                desc = self._render_flow_text(
                    step.message_text or '',
                    partner=partner,
                    message=message,
                    variables=variables,
                )
                if message.body:
                    desc = f"{desc}\n\n[Inbound Context / Form Data]\n{message.body}".strip()

                self.env['crm.lead'].create({
                    'name': f'WhatsApp Flow Lead: {partner.name if partner else message.phone_number}',
                    'partner_id': partner.id if partner else False,
                    'phone': message.phone_number,
                    'description': desc,
                    'type': 'lead',
                })
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'assign_tag':
            if chat and step.assign_tag_id:
                chat.write({'tag_ids': [(4, step.assign_tag_id.id)]})
            if partner and step.assign_tag_id:
                partner.write({'category_id': [(4, step.assign_tag_id.id)]})
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'chat_status':
            if chat:
                if step.chat_status == 'archived':
                    chat.write({'is_archived': True})
                else:
                    chat.write({'state': step.chat_status or 'open', 'is_archived': False})
            return {'stop': False}

        elif step.action_type == 'update_contact':
            self._write_contact_attribute(
                partner,
                message,
                step.contact_attribute_name or step.variable_name,
                step.contact_attribute_value or step.variable_value,
                variables=variables,
            )
            return {'stop': False}

        elif step.action_type == 'http_request':
            if not step.http_url:
                raise ValueError(f'Step "{step.name}" has no URL configured.')
            request_payload = {}
            if step.http_payload:
                rendered_payload = self._render_flow_text(
                    step.http_payload,
                    partner=partner,
                    message=message,
                    variables=variables,
                )
                request_payload = json.loads(rendered_payload)
            query_params = {}
            if step.http_query_params:
                rendered_query = self._render_flow_text(
                    step.http_query_params,
                    partner=partner,
                    message=message,
                    variables=variables,
                )
                query_params = json.loads(rendered_query)
            headers = {}
            if step.http_headers:
                rendered_headers = self._render_flow_text(
                    step.http_headers,
                    partner=partner,
                    message=message,
                    variables=variables,
                )
                headers = json.loads(rendered_headers)
            auth = None
            if step.http_auth_type == 'bearer' and step.http_auth_token:
                headers['Authorization'] = f'Bearer {step.http_auth_token}'
            elif step.http_auth_type == 'basic' and step.http_username:
                auth = (step.http_username, step.http_password or '')
            response = requests.request(
                step.http_method,
                step.http_url,
                json=request_payload if step.http_method in ('POST', 'PUT', 'PATCH') else None,
                params=query_params or (request_payload if step.http_method == 'GET' else None),
                headers=headers or None,
                auth=auth,
                timeout=20,
            )
            variables[f'http_{step.id}_status'] = response.status_code
            response_value = response.text
            try:
                response_json = response.json()
                variables[f'http_{step.id}_response'] = response_json
                if step.http_response_path:
                    response_value = self._json_path_value(response_json, step.http_response_path)
            except Exception:
                response_json = False
            if step.response_variable:
                variables[step.response_variable] = response_value
            if response.ok:
                return {'stop': False, 'next_step': step.http_success_step_id or False}
            variables[f'http_{step.id}_error'] = response.text
            if step.http_failure_step_id:
                return {'stop': False, 'next_step': step.http_failure_step_id}
            response.raise_for_status()
            return {'stop': False}

        elif step.action_type == 'set_variable':
            if step.variable_name:
                variables[step.variable_name] = self._render_flow_text(
                    step.variable_value or '',
                    partner=partner,
                    message=message,
                    variables=variables,
                )
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'send_catalog':
            prompt = self._render_flow_text(
                step.message_text or 'Please review our catalogue.',
                partner=partner,
                message=message,
                variables=variables,
            )
            catalog_id = step.catalog_id or account.commerce_catalog_id
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'interactive',
                'body': prompt,
                'direction': 'outbound',
                'is_automated': True,
            })
            if step.catalog_message_type == 'catalog_message':
                outbound._prepare_interactive_catalog_message_payload(
                    prompt,
                    thumbnail_product_retailer_id=(
                        step.thumbnail_product_retailer_id
                        or step.product_retailer_id
                        or account.commerce_default_product_retailer_id
                    ),
                    footer_text=step.button_footer_text,
                )
            elif step.catalog_message_type == 'multi_product':
                outbound._prepare_interactive_product_list_payload(
                    prompt,
                    catalog_id,
                    step.product_retailer_ids or step.product_retailer_id,
                    header_text=step.button_header_text or 'Products',
                    footer_text=step.button_footer_text,
                    section_title=step.catalog_section_title or 'Products',
                )
            else:
                outbound._prepare_interactive_product_payload(
                    prompt,
                    catalog_id,
                    step.product_retailer_id or account.commerce_default_product_retailer_id,
                    footer_text=step.button_footer_text,
                )
            outbound.action_send()
            return {'stop': False}

        elif step.action_type == 'delay':
            if step.delay_seconds:
                next_step = self._get_next_step(step)
                if next_step:
                    wake_at = fields.Datetime.now() + timedelta(seconds=step.delay_seconds)
                    log.write({
                        'status': 'pending',
                        'current_step': next_step.id,
                        'wake_at': wake_at,
                        'variables': json.dumps(variables),
                    })
                    _logger.info(
                        "Flow '%s' delayed %ss for %s until %s",
                        self.name, step.delay_seconds, message.phone_number, wake_at,
                    )
                    return {'stop': True, 'status': 'pending'}
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'end':
            return {'stop': True, 'status': 'success'}

        else:
            _logger.warning(f"Unknown step action type: {step.action_type}")
            return {'stop': False}  # FIXED: Added fallback return


class WhatsAppBotNode(models.Model):
    """Visual builder node persisted separately from executable flow steps."""
    _name = 'whatsapp.bot.node'
    _description = 'WhatsApp Bot Visual Node'
    _order = 'flow_id, sequence, id'
    _rec_name = 'name'
    _node_key_flow_unique = models.Constraint(
        'unique(flow_id, node_key)',
        'Node keys must be unique inside a bot flow.',
    )

    flow_id = fields.Many2one('whatsapp.bot.flow', required=True, ondelete='cascade', index=True)
    node_key = fields.Char('Node Key', required=True, index=True)
    name = fields.Char('Label', required=True, default='Node')
    node_type = fields.Selection([
        ('trigger', 'Trigger'),
        ('message', 'Message'),
        ('condition', 'Condition'),
        ('action', 'Action'),
    ], required=True, default='message', index=True)
    node_subtype = fields.Char('Subtype', help='Text/template/action variant used by the visual builder.')
    legacy_type = fields.Char('Legacy Canvas Type', help='Compatibility key for older canvas JSON.')
    x_position = fields.Float('X Position', default=0)
    y_position = fields.Float('Y Position', default=0)
    sequence = fields.Integer('Sequence', default=10)
    config_json = fields.Text('Configuration JSON', default='{}')

    def to_graph_dict(self):
        self.ensure_one()
        return {
            'id': self.node_key,
            'type': self.node_type,
            'subtype': self.node_subtype or self.node_type,
            'legacy_type': self.legacy_type or self.node_type,
            'label': self.name,
            'x': self.x_position,
            'y': self.y_position,
            'config': _json_loads(self.config_json, {}),
        }


class WhatsAppBotEdge(models.Model):
    """Visual builder edge linking two persisted graph nodes."""
    _name = 'whatsapp.bot.edge'
    _description = 'WhatsApp Bot Visual Edge'
    _order = 'flow_id, sequence, id'
    _rec_name = 'edge_key'

    flow_id = fields.Many2one('whatsapp.bot.flow', required=True, ondelete='cascade', index=True)
    edge_key = fields.Char('Edge Key', required=True, index=True)
    source_node_id = fields.Many2one('whatsapp.bot.node', string='Source Node', required=True, ondelete='cascade')
    target_node_id = fields.Many2one('whatsapp.bot.node', string='Target Node', required=True, ondelete='cascade')
    source_key = fields.Char('Source Key', required=True)
    target_key = fields.Char('Target Key', required=True)
    label = fields.Char('Branch Label')
    sequence = fields.Integer('Sequence', default=10)
    config_json = fields.Text('Configuration JSON', default='{}')

    @api.constrains('flow_id', 'source_node_id', 'target_node_id')
    def _check_edge_flow(self):
        for edge in self:
            if edge.source_node_id.flow_id != edge.flow_id or edge.target_node_id.flow_id != edge.flow_id:
                raise ValidationError('Both edge endpoints must belong to the same flow.')

    def to_graph_dict(self):
        self.ensure_one()
        return {
            'id': self.edge_key,
            'from': self.source_key or self.source_node_id.node_key,
            'to': self.target_key or self.target_node_id.node_key,
            'label': self.label or '',
            'config': _json_loads(self.config_json, {}),
        }


class WhatsAppBotFlowStep(models.Model):
    """Steps within a bot flow"""
    _name = 'whatsapp.bot.flow.step'
    _description = 'Bot Flow Step'
    _order = 'flow_id, step_number'
    _rec_name = 'name'

    name = fields.Char('Step Name', required=True, help='Admin-facing name for this step in the flow.')
    flow_id = fields.Many2one(
        'whatsapp.bot.flow',
        required=True,
        ondelete='cascade',
        help='Flow that owns this step.',
    )
    account_id = fields.Many2one(
        'whatsapp.account',
        string='WhatsApp Account',
        related='flow_id.account_id',
        readonly=True,
        help='Account inherited from the parent flow.',
    )
    step_number = fields.Integer('Step Number', required=True, default=1, help='Execution order when no branch overrides the route.')
    node_id = fields.Char('Canvas Node ID', help='Technical link to the corresponding visual builder node.')
    
    # Step action
    action_type = fields.Selection([
        ('send_text', 'Send Text Message'),
        ('send_template', 'Send Template'),
        ('send_media', 'Send Media'),
        ('send_buttons', 'Send Buttons/Quick Replies'),
        ('send_list', 'Send List Menu'),
        ('send_cta_url', 'Send URL Button'),
        ('send_form_link', 'Send Form Link'),
        ('send_payment_link', 'Send Payment Link'),
        ('wait_response', 'Wait for Response'),
        ('ask_question', 'Ask / Collect Input'),
        ('condition', 'Conditional Logic'),
        ('transfer', 'Transfer to Agent'),
        ('assign_team', 'Assign Team'),
        ('create_lead', 'Create Lead'),
        ('assign_tag', 'Assign Tag'),
        ('chat_status', 'Update Chat Status'),
        ('update_contact', 'Update Contact Attribute'),
        ('http_request', 'HTTP Request'),
        ('set_variable', 'Set Variable'),
        ('send_catalog', 'Send Catalog / Product'),
        ('delay', 'Add Delay'),
        ('end', 'End Flow'),
    ], string='Action', required=True, default='send_text', help='What this step does when the flow reaches it.')
    
    # Text action
    message_text = fields.Text(
        'Message Text',
        help='Text sent to the customer. Also used as the button prompt, media caption, or CRM lead note where relevant.',
    )
    
    # Template action
    template_id = fields.Many2one(
        'whatsapp.template',
        string='Template',
        help='Approved WhatsApp template to send when Action is Send Template.',
    )
    
    # Media action
    media_id = fields.Many2one(
        'whatsapp.media.library',
        string='Media',
        help='Media Library item sent when Action is Send Media.',
    )
    
    # Buttons action
    button_ids = fields.One2many(
        'whatsapp.bot.flow.button',
        'step_id',
        string='Buttons',
        help='Quick reply buttons. In the visual builder, outgoing connection labels create these buttons.',
    )
    button_header_text = fields.Char(
        'Header Text',
        help='Optional header shown above a button or list message. Keep it short for WhatsApp.',
    )
    button_footer_text = fields.Char(
        'Footer Text',
        help='Optional small footer shown below a button or list message.',
    )
    list_button_text = fields.Char(
        'List Button Text',
        default='Choose',
        help='Text shown on the list opener button when Action is Send List Menu.',
    )
    list_section_title = fields.Char(
        'List Section Title',
        default='Options',
        help='Section title grouping the list rows when Action is Send List Menu.',
    )
    cta_button_text = fields.Char(
        'URL Button Text',
        default='Open',
        help='Display text on the single CTA URL button. WhatsApp supports one URL button per CTA message.',
    )
    cta_button_url = fields.Char(
        'URL Button Link',
        help='HTTP/HTTPS link opened when the customer taps the CTA URL button.',
    )
    form_id = fields.Many2one(
        'whatsapp.form',
        string='WhatsApp Form',
        domain="[('active', '=', True)]",
        help='Form sent by Send Form Link. If empty, the WhatsApp account default form is used.',
    )
    payment_mode = fields.Selection([
        ('account_default', 'Account Default'),
        ('latest_invoice', 'Latest Unpaid Invoice'),
        ('latest_quote', 'Latest Quotation / Order'),
        ('manual_url', 'Manual URL From Account'),
    ], string='Payment Source', default='account_default',
        help='Controls which payable document or manual URL is used by Send Payment Link.')
    
    # Conditional logic
    condition_type = fields.Selection([
        ('keyword_match', 'Keyword Match'),
        ('response_contains', 'Response Contains Text'),
        ('json_path', 'JSON Path from Response'),
    ], string='Condition Type', help='How to evaluate the latest reply or saved response before branching.')
    condition_source = fields.Selection([
        ('incoming_text', 'Current Incoming Text'),
        ('last_reply', 'Last Reply'),
        ('variable', 'Saved Variable'),
        ('button_payload', 'Button/List Payload'),
    ], string='Condition Source', default='last_reply')
    condition_variable = fields.Char('Condition Variable', help='Variable name used when source is Saved Variable.')
    condition_operator = fields.Selection([
        ('contains', 'Contains'),
        ('equals', 'Equals'),
        ('not_equals', 'Does Not Equal'),
        ('starts_with', 'Starts With'),
        ('ends_with', 'Ends With'),
        ('regex', 'Regex Match'),
        ('greater_than', 'Greater Than'),
        ('less_than', 'Less Than'),
        ('blank', 'Is Blank'),
        ('not_blank', 'Is Not Blank'),
    ], string='Operator', default='contains')
    condition_value = fields.Char('Condition Value', help='Text or variable value used by the selected condition.')
    condition_branch_ids = fields.One2many(
        'whatsapp.bot.flow.branch',
        'step_id',
        string='Condition Branches',
        help='Optional multi-branch routes evaluated before the true/false fallback.',
    )
    condition_true_step = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To (If True)',
        domain='[("flow_id", "=", flow_id)]',
        help='Step to run when the condition matches.',
    )
    condition_false_step = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To (If False)',
        domain='[("flow_id", "=", flow_id)]',
        help='Step to run when the condition does not match.',
    )
    
    # Transfer/Assign
    assign_user_id = fields.Many2one(
        'res.users',
        string='Assign to Agent',
        help='User who should own the chat when Action is Transfer to Agent.',
    )
    assign_team_member_ids = fields.Many2many(
        'whatsapp.team.member',
        string='Assign Team Members',
        help='Candidate team members. The least busy available agent is selected at runtime.',
    )
    assign_tag_id = fields.Many2one(
        'res.partner.category',
        string='Tag',
        help='Contact tag applied when Action is Assign Tag.',
    )
    chat_status = fields.Selection([
        ('open', 'Open / Reopen'),
        ('snoozed', 'Snoozed'),
        ('resolved', 'Resolved'),
        ('archived', 'Archived'),
    ], string='Chat Status', default='open')
    contact_attribute_name = fields.Char('Contact Attribute')
    contact_attribute_value = fields.Char('Attribute Value')
    
    # HTTP Request
    http_method = fields.Selection(
        [('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'), ('PATCH', 'PATCH'), ('DELETE', 'DELETE')],
        default='POST',
        help='HTTP method used by the external request step.',
    )
    http_url = fields.Char('URL', help='External webhook URL called when Action is HTTP Request.')
    http_headers = fields.Text('Headers (JSON)', help='Optional JSON object of request headers.')
    http_query_params = fields.Text('Query Params (JSON)', help='Optional JSON object of query string parameters.')
    http_auth_type = fields.Selection([
        ('none', 'None'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Auth'),
    ], string='Auth Type', default='none')
    http_auth_token = fields.Char('Bearer Token')
    http_username = fields.Char('Username')
    http_password = fields.Char('Password')
    http_payload = fields.Text('Payload (JSON)', help='Optional JSON body for POST/PUT HTTP requests.')
    http_response_path = fields.Char('Response JSON Path', help='Dot path to store from the JSON response, e.g. data.order.status.')
    http_success_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To On Success',
        domain='[("flow_id", "=", flow_id)]',
    )
    http_failure_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To On Failure',
        domain='[("flow_id", "=", flow_id)]',
    )

    # Ask / Collect Input
    input_validation_type = fields.Selection([
        ('text', 'Text'),
        ('number', 'Number'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('city', 'City / Location Text'),
        ('media', 'File or Media'),
        ('location', 'WhatsApp Location'),
    ], string='Answer Type', default='text')
    invalid_message = fields.Text('Invalid Answer Message', default='Please send a valid answer so we can continue.')
    max_attempts = fields.Integer('Max Attempts', default=2)
    timeout_minutes = fields.Integer('No Reply Timeout (minutes)', default=0)
    invalid_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To On Invalid',
        domain='[("flow_id", "=", flow_id)]',
    )
    timeout_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To On No Reply',
        domain='[("flow_id", "=", flow_id)]',
    )
    fallback_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Fallback Step',
        domain='[("flow_id", "=", flow_id)]',
        help='Used for unmatched buttons/list selections and other runtime fallbacks.',
    )

    # Catalog/product messages
    catalog_message_type = fields.Selection([
        ('catalog_message', 'Open Full Catalog / Shop'),
        ('single_product', 'Single Product Card'),
        ('multi_product', 'Multi-Product List'),
    ], string='Catalog Message Type', default='single_product')
    catalog_id = fields.Char(
        'Catalog ID',
        help='Meta Commerce Manager catalog ID. If empty, the WhatsApp account default catalog is used when available.',
    )
    product_retailer_id = fields.Char(
        'Product Retailer ID',
        help='Single product/content ID from Meta Commerce Manager.',
    )
    product_retailer_ids = fields.Text(
        'Product Retailer IDs',
        help='One product/content ID per line, comma, or semicolon for multi-product list messages.',
    )
    thumbnail_product_retailer_id = fields.Char(
        'Thumbnail Product Retailer ID',
        help='Optional product/content ID used by the full catalog/shop message thumbnail.',
    )
    catalog_section_title = fields.Char(
        'Product Section Title',
        default='Products',
        help='Section title shown for product list messages.',
    )
    
    # Delay
    delay_seconds = fields.Integer('Delay (seconds)', default=0, help='Seconds to pause before continuing to the next step.')
    
    # Variable
    variable_name = fields.Char('Variable Name', help='Name of the flow variable to set or read later.')
    variable_value = fields.Char('Variable Value', help='Value stored when Action is Set Variable.')
    
    # Next step
    next_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Next Step',
        domain='[("flow_id", "=", flow_id)]',
        help='Default next step after this one completes.',
    )
    
    # Settings
    condition_on_previous = fields.Boolean(
        'Wait for Response from Previous Step',
        default=False,
        help='Use the previous customer response when evaluating this step.',
    )
    save_response = fields.Boolean(
        'Save User Response',
        default=False,
        help='Store the next customer response into a flow variable.',
    )
    response_variable = fields.Char(
        'Response Variable Name',
        help='Variable name used to store a customer reply or HTTP response.',
    )
    placeholder_help = fields.Text(
        'Available Placeholders',
        compute='_compute_placeholder_guidance',
        help='Named placeholders available for bot message text and action values.',
    )
    message_preview = fields.Text(
        'Sample Preview',
        compute='_compute_placeholder_guidance',
        help='Preview of the message using sample placeholder values.',
    )
    started_count = fields.Integer('Started', compute='_compute_step_analytics')
    pending_count = fields.Integer('Pending', compute='_compute_step_analytics')
    completed_count = fields.Integer('Completed', compute='_compute_step_analytics')
    failed_count = fields.Integer('Failed', compute='_compute_step_analytics')

    def _compute_step_analytics(self):
        Log = self.env['whatsapp.bot.flow.log'].sudo()
        for step in self:
            domain = [('current_step', '=', step.id)]
            step.started_count = Log.search_count(domain)
            step.pending_count = Log.search_count(domain + [('status', '=', 'pending')])
            step.completed_count = Log.search_count(domain + [('status', '=', 'success')])
            step.failed_count = Log.search_count(domain + [('status', '=', 'failed')])

    @api.depends(
        'message_text', 'button_header_text', 'button_footer_text', 'variable_name',
        'response_variable', 'contact_attribute_name', 'input_validation_type',
        'cta_button_text', 'cta_button_url', 'catalog_message_type', 'product_retailer_id',
        'product_retailer_ids', 'thumbnail_product_retailer_id', 'form_id',
        'payment_mode',
    )
    def _compute_placeholder_guidance(self):
        help_text = (
            "Use named placeholders in message text, button prompts, media captions, "
            "lead notes, set-variable values, and HTTP JSON payloads. Available: "
            "{{name}}, {{phone}}, {{email}}, {{company}}, {{last_message}}, {{last_reply}}. "
            "Saved variables from Wait Reply or Set Variable can also be used as {{variable_name}}."
        )
        sample_variables = {
            'last_reply': 'Customer reply',
        }
        for step in self:
            if step.variable_name:
                sample_variables[step.variable_name] = 'Sample value'
            if step.response_variable:
                sample_variables[step.response_variable] = 'Customer reply'
            step.placeholder_help = help_text
            step.message_preview = step.flow_id._render_flow_text(
                step.message_text or '',
                variables=sample_variables,
                sample=True,
            )

    def action_open_step_form(self):
        self.ensure_one()
        form_view = self.env.ref(
            'elsx_whatsapp_marketing.whatsapp_bot_flow_step_view_form',
            raise_if_not_found=False,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': f'Configure Step: {self.name}',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(form_view.id, 'form')] if form_view else [(False, 'form')],
            'target': 'new',
            'context': {
                'default_flow_id': self.flow_id.id,
            },
        }

    def _ensure_default_interactive_options(self):
        Button = self.env['whatsapp.bot.flow.button'].sudo().with_context(skip_canvas_sync=True)
        for step in self.filtered(lambda rec: rec.action_type in ('send_buttons', 'send_list') and not rec.button_ids):
            Button.create({
                'step_id': step.id,
                'name': 'Option 1',
                'button_id': f'flow_{step.flow_id.id}_step_{step.id}_option_1',
            })

    def action_view_buttons(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Buttons: {self.name}',
            'res_model': 'whatsapp.bot.flow.button',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('step_id', '=', self.id)],
            'context': {
                'default_step_id': self.id,
            },
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_flow_step_validation'):
            records._ensure_default_interactive_options()
        if not self.env.context.get('skip_canvas_sync'):
            flows = records.mapped('flow_id')
            for flow in flows:
                flow._sync_steps_to_canvas()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'action_type' in vals and not self.env.context.get('skip_flow_step_validation'):
            self._ensure_default_interactive_options()
        if not self.env.context.get('skip_canvas_sync'):
            flows = self.mapped('flow_id')
            for flow in flows:
                flow._sync_steps_to_canvas()
        return res

    def unlink(self):
        flows = self.mapped('flow_id')
        res = super().unlink()
        if not self.env.context.get('skip_canvas_sync'):
            for flow in flows:
                if flow.exists():
                    flow._sync_steps_to_canvas()
        return res

    @api.constrains(
        'action_type', 'template_id', 'media_id', 'button_ids', 'condition_type',
        'condition_true_step', 'condition_false_step', 'condition_branch_ids',
        'http_url', 'delay_seconds', 'max_attempts', 'timeout_minutes',
        'cta_button_text', 'cta_button_url', 'catalog_message_type',
        'catalog_id', 'product_retailer_id', 'product_retailer_ids',
        'thumbnail_product_retailer_id', 'form_id',
    )
    def _check_step_configuration(self):
        if self.env.context.get('skip_flow_step_validation'):
            return
        strict = self.env.context.get('strict_flow_validation')
        for step in self:
            if strict and step.action_type == 'send_template' and not step.template_id:
                raise ValidationError(f'Step "{step.name}" requires a template.')
            if strict and step.action_type == 'send_media' and not step.media_id:
                raise ValidationError(f'Step "{step.name}" requires a media record.')
            if step.action_type == 'send_buttons' and len(step.button_ids) > 3:
                raise ValidationError(f'Step "{step.name}" can have maximum 3 quick reply buttons.')
            if step.action_type == 'send_list' and len(step.button_ids) > 10:
                raise ValidationError(f'Step "{step.name}" can have maximum 10 list rows.')
            if step.action_type == 'ask_question':
                if strict and not (step.message_text or '').strip():
                    raise ValidationError(f'Step "{step.name}" requires a question/prompt.')
                if strict and not step.response_variable:
                    raise ValidationError(f'Step "{step.name}" requires a response variable.')
                if step.max_attempts <= 0:
                    raise ValidationError(f'Step "{step.name}" max attempts must be at least 1.')
                if step.timeout_minutes < 0:
                    raise ValidationError(f'Step "{step.name}" timeout cannot be negative.')
            if strict and step.action_type == 'condition':
                if not step.condition_type:
                    raise ValidationError(f'Step "{step.name}" requires a condition type.')
                if not step.condition_true_step and not step.condition_false_step and not step.condition_branch_ids:
                    raise ValidationError(
                        f'Step "{step.name}" must route to at least one target step.'
                    )
            if strict and step.action_type == 'http_request' and not step.http_url:
                raise ValidationError(f'Step "{step.name}" requires a request URL.')
            if strict and step.action_type == 'send_cta_url':
                if not (step.cta_button_text or '').strip():
                    raise ValidationError(f'Step "{step.name}" requires URL button text.')
                url = (step.cta_button_url or step.account_id.commerce_shop_url or '').strip()
                if not url:
                    raise ValidationError(f'Step "{step.name}" requires a URL button link or account Shop / Catalogue URL.')
                if not url.startswith(('http://', 'https://')):
                    raise ValidationError(f'Step "{step.name}" URL button link must start with http:// or https://.')
            elif step.action_type == 'send_cta_url':
                url = (step.cta_button_url or '').strip()
                if url and not url.startswith(('http://', 'https://')):
                    raise ValidationError(f'Step "{step.name}" URL button link must start with http:// or https://.')
            if strict and step.action_type == 'send_form_link':
                if not step.form_id and not step.account_id.default_form_id:
                    raise ValidationError(
                        f'Step "{step.name}" requires a form or a Default WhatsApp Form on the account.'
                    )
            if strict and step.action_type == 'send_payment_link':
                if step.account_id.payment_link_mode == 'disabled':
                    raise ValidationError(
                        f'Step "{step.name}" requires Payment Link Mode to be enabled on the WhatsApp account.'
                    )
                if (
                    (step.payment_mode == 'manual_url' or step.account_id.payment_link_mode == 'manual_url')
                    and not step.account_id.payment_manual_url
                ):
                    raise ValidationError(
                        f'Step "{step.name}" requires a Manual Payment URL on the WhatsApp account.'
                    )
            if strict and step.action_type == 'send_catalog':
                catalog_id = (step.catalog_id or step.account_id.commerce_catalog_id or '').strip()
                default_product = (
                    step.product_retailer_id
                    or step.thumbnail_product_retailer_id
                    or step.account_id.commerce_default_product_retailer_id
                    or ''
                ).strip()
                if step.catalog_message_type == 'single_product':
                    if not catalog_id or not default_product:
                        raise ValidationError(
                            f'Step "{step.name}" single product mode requires Catalog ID and Product Retailer ID.'
                        )
                elif step.catalog_message_type == 'multi_product':
                    if not catalog_id or not (step.product_retailer_ids or step.product_retailer_id or '').strip():
                        raise ValidationError(
                            f'Step "{step.name}" product list mode requires Catalog ID and one or more Product Retailer IDs.'
                        )
            if step.action_type == 'delay':
                if step.delay_seconds < 0:
                    raise ValidationError(f'Step "{step.name}" delay cannot be negative.')
                if step.delay_seconds > 86400:
                    raise ValidationError(f'Step "{step.name}" delay cannot exceed 24 hours.')


class WhatsAppBotFlowBranch(models.Model):
    """Multi-branch condition route for a bot flow step."""
    _name = 'whatsapp.bot.flow.branch'
    _description = 'Bot Flow Condition Branch'
    _order = 'step_id, sequence, id'

    step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        required=True,
        ondelete='cascade',
    )
    flow_id = fields.Many2one('whatsapp.bot.flow', related='step_id.flow_id', readonly=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Branch Label', required=True, default='Branch')
    operator = fields.Selection([
        ('contains', 'Contains'),
        ('equals', 'Equals'),
        ('not_equals', 'Does Not Equal'),
        ('starts_with', 'Starts With'),
        ('ends_with', 'Ends With'),
        ('regex', 'Regex Match'),
        ('greater_than', 'Greater Than'),
        ('less_than', 'Less Than'),
        ('blank', 'Is Blank'),
        ('not_blank', 'Is Not Blank'),
    ], default='contains', required=True)
    value = fields.Char('Match Value')
    next_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To Step',
        domain='[("flow_id", "=", flow_id)]',
        required=True,
    )

    @api.constrains('step_id', 'next_step_id')
    def _check_branch_flow(self):
        for branch in self:
            if branch.next_step_id and branch.next_step_id.flow_id != branch.step_id.flow_id:
                raise ValidationError('Branch target step must belong to the same flow.')


class WhatsAppBotFlowButton(models.Model):
    """Buttons in a bot flow step"""
    _name = 'whatsapp.bot.flow.button'
    _description = 'Bot Flow Button'
    _button_id_step_unique = models.Constraint(
        'unique(step_id, button_id)',
        'Button IDs must be unique per flow step.',
    )
    
    step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        required=True,
        ondelete='cascade',
        help='Button message step that owns this quick reply.',
    )
    flow_id = fields.Many2one('whatsapp.bot.flow', related='step_id.flow_id', readonly=True, help='Flow inherited from the parent step.')
    name = fields.Char('Button Text', required=True, help='Text shown to the customer on the quick reply button.')
    button_id = fields.Char('Button ID', help='Unique identifier for this button')
    description = fields.Char('Description', help='Optional description shown under a list row.')
    button_action = fields.Selection([
        ('reply', 'Reply / Route'),
        ('url', 'Open URL'),
        ('catalog_product', 'Send Product Card'),
    ], string='Button Action', default='reply', required=True,
        help='Reply buttons wait for a customer tap. URL and Product actions send a single CTA/product message and then continue.')
    url = fields.Char('URL', help='HTTP/HTTPS URL for Open URL button actions.')
    catalog_id = fields.Char(
        'Catalog ID',
        help='Optional catalog override for Product Card actions. The account default catalog is used if empty.',
    )
    product_retailer_id = fields.Char(
        'Product Retailer ID',
        help='Commerce Manager product/content ID for Product Card actions.',
    )
    next_step_id = fields.Many2one(
        'whatsapp.bot.flow.step',
        string='Go To Step',
        domain='[("flow_id", "=", flow_id)]',
        help='Step to run when the customer selects this button.',
    )

    def action_open_button_form(self):
        self.ensure_one()
        form_view = self.env.ref(
            'elsx_whatsapp_marketing.whatsapp_bot_flow_button_view_form',
            raise_if_not_found=False,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': f'Configure Button: {self.name}',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(form_view.id, 'form')] if form_view else [(False, 'form')],
            'target': 'new',
            'context': {
                'default_step_id': self.step_id.id,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_canvas_sync'):
            flows = records.mapped('step_id.flow_id')
            for flow in flows:
                flow._sync_steps_to_canvas()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_canvas_sync'):
            flows = self.mapped('step_id.flow_id')
            for flow in flows:
                flow._sync_steps_to_canvas()
        return res

    def unlink(self):
        flows = self.mapped('step_id.flow_id')
        res = super().unlink()
        if not self.env.context.get('skip_canvas_sync'):
            for flow in flows:
                if flow.exists():
                    flow._sync_steps_to_canvas()
        return res

    @api.constrains('step_id', 'name', 'button_action', 'url', 'catalog_id', 'product_retailer_id')
    def _check_button_configuration(self):
        for button in self:
            strict = self.env.context.get('strict_flow_validation') or bool(button.step_id.flow_id.active)
            if button.step_id.action_type == 'send_list' and button.button_action != 'reply':
                raise ValidationError('List menu rows can only use Reply / Route actions.')
            label_limit = 24 if button.step_id.action_type == 'send_list' else 20
            if button.name and len(button.name) > label_limit:
                raise ValidationError(
                    f'Button "{button.name}" exceeds WhatsApp label limit of {label_limit} characters.'
                )
            if button.button_action == 'url':
                if strict and not button.url:
                    raise ValidationError(f'Button "{button.name}" requires a URL.')
                if button.url and not button.url.startswith(('http://', 'https://')):
                    raise ValidationError(f'Button "{button.name}" URL must start with http:// or https://.')
            if button.button_action == 'catalog_product':
                if strict and not button.product_retailer_id:
                    raise ValidationError(f'Button "{button.name}" requires a Product Retailer ID.')
                if strict and not (button.catalog_id or button.step_id.account_id.commerce_catalog_id):
                    raise ValidationError(
                        f'Button "{button.name}" requires a Catalog ID or an account default Meta Catalog ID.'
                    )


class WhatsAppBotFlowLog(models.Model):
    """Execution log for bot flows"""
    _name = 'whatsapp.bot.flow.log'
    _description = 'Bot Flow Execution Log'
    _rec_name = 'flow_id'
    _order = 'create_date desc'

    flow_id = fields.Many2one('whatsapp.bot.flow', required=True, ondelete='cascade')
    chat_id = fields.Many2one('whatsapp.chat', string='Conversation')
    partner_id = fields.Many2one('res.partner', string='Contact')
    phone_number = fields.Char('Phone Number')
    
    # Execution details
    status = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], default='pending')
    
    current_step = fields.Many2one('whatsapp.bot.flow.step', string='Current Step')
    total_steps = fields.Integer('Total Steps')
    completed_steps = fields.Integer('Completed Steps', default=0)
    
    # Timeline
    started_date = fields.Datetime('Started', default=fields.Datetime.now)
    wake_at = fields.Datetime('Resume At', index=True)
    completed_date = fields.Datetime('Completed')
    duration = fields.Float('Duration (minutes)', compute='_compute_duration')
    
    # Details
    variables = fields.Text('Variables (JSON)')  # Store variables used in this execution
    error_message = fields.Text('Error Message')
    
    @api.depends('completed_date', 'started_date')
    def _compute_duration(self):
        for record in self:
            if record.completed_date and record.started_date:
                delta = record.completed_date - record.started_date
                record.duration = delta.total_seconds() / 60
            else:
                record.duration = 0

    @api.model
    def _cron_resume_delayed_flows(self, limit=50):
        logs = self.sudo().search([
            ('status', '=', 'pending'),
            ('wake_at', '!=', False),
            ('wake_at', '<=', fields.Datetime.now()),
            ('current_step', '!=', False),
        ], order='wake_at asc, id asc', limit=limit)
        for log in logs:
            try:
                log.flow_id.sudo()._resume_delayed_log(log)
            except Exception as exc:
                _logger.error("Failed to resume delayed flow log %s: %s", log.id, exc)



class WhatsAppBotFlowTestWizard(models.TransientModel):
    """Wizard to test bot flows"""
    _name = 'whatsapp.bot.flow.test.wizard'
    _description = 'Test Bot Flow'

    flow_id = fields.Many2one('whatsapp.bot.flow', required=True)
    contact_id = fields.Many2one('res.partner', string='Test Contact', required=True)
    test_message = fields.Char('Test Message', default='test')
    
    def action_test(self):
        """Execute the flow for testing"""
        self.ensure_one()
        
        try:
            phone = getattr(self.contact_id, 'mobile', False) or self.contact_id.phone
            if not phone:
                raise ValidationError("Selected contact has no phone number.")
            # Create a test message
            message = self.env['whatsapp.message'].create({
                'account_id': self.flow_id.account_id.id,
                'phone_number': phone,
                'partner_id': self.contact_id.id,
                'body': self.test_message,
                'direction': 'inbound',
                'message_type': 'text',
            })
            
            # Execute the flow
            self.flow_id._execute_flow(message)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Flow Test Complete',
                    'message': 'The flow has been executed successfully.',
                    'type': 'success',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Flow Test Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }
