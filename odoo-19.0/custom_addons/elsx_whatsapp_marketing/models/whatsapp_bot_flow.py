# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import json
import requests

_logger = logging.getLogger(__name__)

CANVAS_ACTION_MAP = {
    'wait_reply': 'wait_response',
    'assign_agent': 'transfer',
    'add_tag': 'assign_tag',
    'api_call': 'http_request',
    'send_list': 'send_buttons',
    'end': 'delay',
}


class WhatsAppBotFlow(models.Model):
    """Advanced WhatsApp Chatbot Flows with multi-step automation"""
    _name = 'whatsapp.bot.flow'
    _description = 'WhatsApp Bot Flow/Automation Sequence'
    _rec_name = 'name'

    name = fields.Char('Flow Name', required=True)
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account', required=True, ondelete='cascade')
    description = fields.Text('Description')
    
    # Flow type
    flow_type = fields.Selection([
        ('greeting', 'Greeting/Welcome'),
        ('support', 'Customer Support'),
        ('sales', 'Sales Funnel'),
        ('survey', 'Survey/Feedback'),
        ('verification', 'Verification/OTP'),
        ('notification', 'Notification'),
        ('custom', 'Custom Flow'),
    ], default='custom', required=True)
    
    # Trigger configuration
    trigger_type = fields.Selection([
        ('keyword', 'Keyword Match'),
        ('first_message', 'First Message'),
        ('manual', 'Manual Trigger'),
        ('schedule', 'Scheduled'),
        ('webhook', 'Webhook Event'),
    ], string='Trigger', default='keyword')
    
    keywords = fields.Char('Keywords', help='Comma-separated keywords to trigger this flow')
    webhook_event = fields.Char('Webhook Event', help='Event name to listen for')
    schedule_pattern = fields.Char('Schedule Pattern', help='Cron expression for scheduling')
    
    # Flow settings
    active = fields.Boolean('Active', default=True)
    priority = fields.Integer('Priority', default=10, help='Higher priority flows execute first')
    retry_on_failure = fields.Boolean('Retry on Failure', default=True)
    max_retries = fields.Integer('Max Retries', default=3)
    
    # Steps in this flow
    step_ids = fields.One2many('whatsapp.bot.flow.step', 'flow_id', string='Flow Steps')
    
    # Statistics
    trigger_count = fields.Integer('Times Triggered', readonly=True, default=0)
    success_count = fields.Integer('Successful Executions', readonly=True, default=0)
    failed_count = fields.Integer('Failed Executions', readonly=True, default=0)
    
    # Visual Flow Builder data (JSON: node positions, connections)
    canvas_data = fields.Text('Canvas Layout', default='{}',
                              help='JSON data storing the visual flow builder layout')
    
    # Execution log
    log_ids = fields.One2many('whatsapp.bot.flow.log', 'flow_id', string='Execution Logs', readonly=True)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Create flow with default first step"""
        records = super().create(vals_list)
        for record in records:
            if not record.step_ids:
                self.env['whatsapp.bot.flow.step'].create({
                    'flow_id': record.id,
                    'step_number': 1,
                    'action_type': 'send_text',
                    'name': 'Welcome Message',
                })
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'canvas_data' in vals:
            for record in self:
                record._sync_canvas_to_steps()
        return res

    def _sync_canvas_to_steps(self):
        self.ensure_one()
        if not self.canvas_data:
            return
        try:
            data = json.loads(self.canvas_data)
            nodes = data.get('nodes', [])
            connections = data.get('connections', [])
            
            existing_steps = {step.node_id: step for step in self.step_ids if step.node_id}
            new_step_ids = []
            
            node_id_to_step = {}
            step_number = 1
            for node in nodes:
                node_id = node.get('id')
                name = node.get('label', 'Unnamed Step')
                action_type = CANVAS_ACTION_MAP.get(node.get('type'), node.get('type', 'send_text'))
                
                if node_id in existing_steps:
                    step = existing_steps[node_id]
                    step.write({
                        'name': name,
                        'action_type': action_type,
                        'step_number': step_number,
                    })
                else:
                    step = self.env['whatsapp.bot.flow.step'].create({
                        'flow_id': self.id,
                        'name': name,
                        'node_id': node_id,
                        'action_type': action_type,
                        'step_number': step_number,
                    })
                
                node_id_to_step[node_id] = step
                new_step_ids.append(step.id)
                step_number += 1
                
            for conn in connections:
                from_id = conn.get('from')
                to_id = conn.get('to')
                if from_id in node_id_to_step and to_id in node_id_to_step:
                    node_id_to_step[from_id].write({
                        'next_step_id': node_id_to_step[to_id].id
                    })
            
            steps_to_unlink = self.step_ids.filtered(lambda s: s.id not in new_step_ids)
            if steps_to_unlink:
                steps_to_unlink.unlink()
                
        except Exception as e:
            _logger.error(f"Failed to sync canvas to steps: {e}")
    
    def action_test_flow(self):
        """Test this flow by manually triggering it"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Test Flow',
            'res_model': 'whatsapp.bot.flow.test.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_flow_id': self.id,
            }
        }
    
    def action_view_logs(self):
        """View execution logs for this flow"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Execution Logs',
            'res_model': 'whatsapp.bot.flow.log',
            'view_mode': 'tree,form',
            'domain': [('flow_id', '=', self.id)],
            'target': 'current',
        }

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

    def _get_first_step(self):
        self.ensure_one()
        return self.step_ids.sorted('step_number')[:1]

    def _get_next_step(self, step):
        self.ensure_one()
        if step.next_step_id:
            return step.next_step_id
        return self.step_ids.filtered(lambda s: s.step_number > step.step_number).sorted('step_number')[:1]

    def _build_execution_variables(self, message):
        partner = message.partner_id
        return {
            'incoming_text': message.body or '',
            'partner_name': partner.name if partner else '',
            'phone_number': message.phone_number or '',
            'chat_id': message.chat_id_ref.id if message.chat_id_ref else False,
        }

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

                result = self._execute_step(current_step, message, variables, log, source=source)
                log.completed_steps += 1

                if result.get('stop'):
                    log.write({
                        'status': result.get('status', 'pending'),
                        'completed_date': fields.Datetime.now(),
                        'variables': json.dumps(variables),
                    })
                    if result.get('status') == 'success':
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

        if step.save_response and step.response_variable:
            variables[step.response_variable] = message.body or ''

        if step.action_type == 'send_text':
            text = step.message_text or 'Hello from your WhatsApp automation.'
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
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': step.media_id.media_type,
                'media_file': step.media_id.media_file,
                'media_filename': step.media_id.media_filename,
                'caption': step.message_text or False,
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound.action_send()
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'send_buttons':
            buttons = []
            for index, button in enumerate(step.button_ids[:3]):
                buttons.append({
                    'id': button.button_id or f'flow_{self.id}_step_{step.id}_{index}',
                    'title': button.name,
                })
            if not buttons:
                raise ValueError(f'Step "{step.name}" has no buttons configured.')
            outbound = self.env['whatsapp.message'].create({
                'account_id': account.id,
                'phone_number': message.phone_number,
                'partner_id': partner.id if partner else False,
                'chat_id_ref': chat.id if chat else False,
                'message_type': 'interactive',
                'body': step.message_text or 'Please choose an option.',
                'direction': 'outbound',
                'is_automated': True,
            })
            outbound._prepare_interactive_payload(outbound.body, buttons)
            outbound.action_send()
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'wait_response':
            if step.response_variable:
                variables[step.response_variable] = message.body or ''
            return {'stop': True, 'status': 'pending'}

        elif step.action_type == 'condition':
            comparison_value = (step.condition_value or '').lower()
            incoming_text = (message.body or '').lower()
            matched = False
            if step.condition_type == 'keyword_match':
                keywords = [k.strip() for k in comparison_value.split(',') if k.strip()]
                matched = any(keyword in incoming_text for keyword in keywords)
            elif step.condition_type == 'response_contains':
                matched = comparison_value in incoming_text
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

        elif step.action_type == 'create_lead':
            if not self.env['crm.lead'].search_count([
                ('type', '=', 'lead'),
                '|', ('partner_id', '=', partner.id if partner else False), ('phone', '=', message.phone_number),
                ('probability', '<', 100),
            ]):
                self.env['crm.lead'].create({
                    'name': f'WhatsApp Flow Lead: {partner.name if partner else message.phone_number}',
                    'partner_id': partner.id if partner else False,
                    'phone': message.phone_number,
                    'description': step.message_text or message.body or '',
                    'type': 'lead',
                })
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'assign_tag':
            if chat and step.assign_tag_id:
                chat.write({'tag_ids': [(4, step.assign_tag_id.id)]})
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'http_request':
            if not step.http_url:
                raise ValueError(f'Step "{step.name}" has no URL configured.')
            request_payload = {}
            if step.http_payload:
                request_payload = json.loads(step.http_payload)
            response = requests.request(
                step.http_method,
                step.http_url,
                json=request_payload if step.http_method in ('POST', 'PUT') else None,
                params=request_payload if step.http_method == 'GET' else None,
                timeout=20,
            )
            response.raise_for_status()
            variables[f'http_{step.id}_status'] = response.status_code
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'set_variable':
            if step.variable_name:
                variables[step.variable_name] = step.variable_value or ''
            return {'stop': False}  # FIXED: Added return

        elif step.action_type == 'delay':
            # Don't block execution, just log the delay
            if step.delay_seconds:
                _logger.info(f"Flow delay: {step.delay_seconds}s for {message.phone_number}")
            return {'stop': False}  # FIXED: Added return

        else:
            _logger.warning(f"Unknown step action type: {step.action_type}")
            return {'stop': False}  # FIXED: Added fallback return


class WhatsAppBotFlowStep(models.Model):
    """Steps within a bot flow"""
    _name = 'whatsapp.bot.flow.step'
    _description = 'Bot Flow Step'
    _order = 'flow_id, step_number'
    _rec_name = 'name'

    name = fields.Char('Step Name', required=True)
    flow_id = fields.Many2one('whatsapp.bot.flow', required=True, ondelete='cascade')
    step_number = fields.Integer('Step Number', required=True, default=1)
    node_id = fields.Char('Canvas Node ID', help="Link to visual builder node")
    
    # Step action
    action_type = fields.Selection([
        ('send_text', 'Send Text Message'),
        ('send_template', 'Send Template'),
        ('send_media', 'Send Media'),
        ('send_buttons', 'Send Buttons/Quick Replies'),
        ('wait_response', 'Wait for Response'),
        ('condition', 'Conditional Logic'),
        ('transfer', 'Transfer to Agent'),
        ('create_lead', 'Create Lead'),
        ('assign_tag', 'Assign Tag'),
        ('http_request', 'HTTP Request'),
        ('set_variable', 'Set Variable'),
        ('delay', 'Add Delay'),
    ], string='Action', required=True, default='send_text')
    
    # Text action
    message_text = fields.Text('Message Text')
    
    # Template action
    template_id = fields.Many2one('whatsapp.template', string='Template')
    
    # Media action
    media_id = fields.Many2one('whatsapp.media.library', string='Media')
    
    # Buttons action
    button_ids = fields.One2many('whatsapp.bot.flow.button', 'step_id', string='Buttons')
    
    # Conditional logic
    condition_type = fields.Selection([
        ('keyword_match', 'Keyword Match'),
        ('response_contains', 'Response Contains Text'),
        ('json_path', 'JSON Path from Response'),
    ], string='Condition Type')
    condition_value = fields.Char('Condition Value')
    condition_true_step = fields.Many2one('whatsapp.bot.flow.step', string='Go To (If True)',
                                         domain='[("flow_id", "=", flow_id)]')
    condition_false_step = fields.Many2one('whatsapp.bot.flow.step', string='Go To (If False)',
                                          domain='[("flow_id", "=", flow_id)]')
    
    # Transfer/Assign
    assign_user_id = fields.Many2one('res.users', string='Assign to Agent')
    assign_tag_id = fields.Many2one('res.partner.category', string='Tag')
    
    # HTTP Request
    http_method = fields.Selection([('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT')], default='POST')
    http_url = fields.Char('URL')
    http_payload = fields.Text('Payload (JSON)')
    
    # Delay
    delay_seconds = fields.Integer('Delay (seconds)', default=0)
    
    # Variable
    variable_name = fields.Char('Variable Name')
    variable_value = fields.Char('Variable Value')
    
    # Next step
    next_step_id = fields.Many2one('whatsapp.bot.flow.step', string='Next Step',
                                   domain='[("flow_id", "=", flow_id)]')
    
    # Settings
    condition_on_previous = fields.Boolean('Wait for Response from Previous Step', default=False)
    save_response = fields.Boolean('Save User Response', default=False)
    response_variable = fields.Char('Response Variable Name')


class WhatsAppBotFlowButton(models.Model):
    """Buttons in a bot flow step"""
    _name = 'whatsapp.bot.flow.button'
    _description = 'Bot Flow Button'
    
    step_id = fields.Many2one('whatsapp.bot.flow.step', required=True, ondelete='cascade')
    flow_id = fields.Many2one('whatsapp.bot.flow', related='step_id.flow_id', readonly=True)
    name = fields.Char('Button Text', required=True)
    button_id = fields.Char('Button ID', help='Unique identifier for this button')
    next_step_id = fields.Many2one('whatsapp.bot.flow.step', string='Go To Step',
                                   domain='[("flow_id", "=", flow_id)]')


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
            # Create a test message
            message = self.env['whatsapp.message'].create({
                'account_id': self.flow_id.account_id.id,
                'phone_number': self.contact_id.phone or self.contact_id.mobile,
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
