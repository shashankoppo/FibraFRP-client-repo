# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import json
import requests

_logger = logging.getLogger(__name__)

CANVAS_ACTION_MAP = {
    'trigger': False,
    'message': 'send_text',
    'action': 'transfer',
    'wait_reply': 'wait_response',
    'assign_agent': 'transfer',
    'add_tag': 'assign_tag',
    'api_call': 'http_request',
    'send_list': 'send_buttons',
    'end': 'end',
}

MESSAGE_NODE_ACTIONS = {
    'text': 'send_text',
    'template': 'send_template',
    'buttons': 'send_buttons',
    'list': 'send_buttons',
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
    'assign_agent': 'action',
    'add_tag': 'action',
    'delay': 'action',
    'api_call': 'action',
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
    node_ids = fields.One2many('whatsapp.bot.node', 'flow_id', string='Visual Nodes')
    edge_ids = fields.One2many('whatsapp.bot.edge', 'flow_id', string='Visual Edges')
    graph_version = fields.Integer('Graph Version', default=1, readonly=True)
    
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
            if record.canvas_data:
                record._sync_node_edge_records_from_canvas()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'canvas_data' in vals:
            for record in self:
                record._sync_canvas_to_steps()
                record._sync_node_edge_records_from_canvas()
        return res

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
        graph = self._normalize_graph_payload(graph)
        self.write({
            'canvas_data': json.dumps(graph, ensure_ascii=False),
            'graph_version': self.graph_version + 1,
        })
        return self.get_visual_graph()

    def _sync_canvas_to_steps(self):
        self.ensure_one()
        if not self.canvas_data:
            return
        try:
            data = json.loads(self.canvas_data)
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
            for conn in connections:
                from_id = conn.get('from')
                to_id = conn.get('to')
                if not from_id or not to_id:
                    continue
                outgoing.setdefault(from_id, []).append(to_id)

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
                    self.write(trigger_update_vals)

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
            step_model = self.env['whatsapp.bot.flow.step'].with_context(skip_flow_step_validation=True)
            node_id_to_step = {}
            new_step_ids = []
            step_number = 1
            valid_actions = {
                value for value, _label in self.env['whatsapp.bot.flow.step']._fields['action_type'].selection
            }

            for node_id in ordered_node_ids:
                node = nodes_by_id.get(node_id) or {}
                node_type = node.get('type', 'send_text')
                config = node.get('config') if isinstance(node.get('config'), dict) else {}
                if node_type == 'message':
                    message_mode = config.get('message_mode') or config.get('subtype') or node.get('subtype') or 'text'
                    action_type = MESSAGE_NODE_ACTIONS.get(message_mode, 'send_text')
                elif node_type == 'action':
                    action_kind = config.get('action_kind') or config.get('action_type') or config.get('subtype') or node.get('subtype') or 'assign_agent'
                    action_type = ACTION_NODE_ACTIONS.get(action_kind, 'transfer')
                else:
                    action_type = CANVAS_ACTION_MAP.get(node_type, node_type)
                if not action_type:
                    continue

                if action_type not in valid_actions:
                    _logger.warning("Unsupported node type '%s' in flow %s", node_type, self.id)
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
                if 'condition_value' in config:
                    step_vals['condition_value'] = config.get('condition_value') or False
                if 'delay_seconds' in config:
                    step_vals['delay_seconds'] = _int_or_false(config.get('delay_seconds')) or 0
                if 'http_method' in config:
                    step_vals['http_method'] = config.get('http_method') or 'POST'
                if 'http_url' in config:
                    step_vals['http_url'] = config.get('http_url') or False
                if 'http_payload' in config:
                    step_vals['http_payload'] = config.get('http_payload') or False
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
                if 'template_id' in config:
                    step_vals['template_id'] = _existing_id('whatsapp.template', config.get('template_id'))
                if 'media_id' in config:
                    step_vals['media_id'] = _existing_id('whatsapp.media.library', config.get('media_id'))
                if 'assign_user_id' in config:
                    step_vals['assign_user_id'] = _existing_id('res.users', config.get('assign_user_id'))
                if 'assign_tag_id' in config:
                    step_vals['assign_tag_id'] = _existing_id('res.partner.category', config.get('assign_tag_id'))

                step = existing_steps.get(node_id)
                if step:
                    step.with_context(skip_flow_step_validation=True).write(step_vals)
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
                if step.action_type == 'condition':
                    true_step = node_id_to_step.get(target_ids[0]) if len(target_ids) > 0 else False
                    false_step = node_id_to_step.get(target_ids[1]) if len(target_ids) > 1 else False
                    write_vals.update({
                        'condition_true_step': true_step.id if true_step else False,
                        'condition_false_step': false_step.id if false_step else False,
                    })
                step.with_context(skip_flow_step_validation=True).write(write_vals)

                if step.action_type == 'send_buttons':
                    existing_buttons = step.button_ids.sorted('id')
                    if not target_ids:
                        if existing_buttons:
                            existing_buttons.unlink()
                        continue

                    for index, target_id in enumerate(target_ids):
                        target_step = node_id_to_step[target_id]
                        button_name = target_step.name or f'Option {index + 1}'
                        generated_button_id = f'flow_{self.id}_{step.id}_{index + 1}'

                        if index < len(existing_buttons):
                            existing_buttons[index].write({
                                'name': button_name,
                                'button_id': existing_buttons[index].button_id or generated_button_id,
                                'next_step_id': target_step.id,
                            })
                        else:
                            self.env['whatsapp.bot.flow.button'].create({
                                'step_id': step.id,
                                'name': button_name,
                                'button_id': generated_button_id,
                                'next_step_id': target_step.id,
                            })

                    if len(existing_buttons) > len(target_ids):
                        existing_buttons[len(target_ids):].unlink()

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

        domain = [
            ('status', '=', 'pending'),
            ('flow_id.account_id', '=', message.account_id.id),
            ('phone_number', '=', message.phone_number),
        ]
        pending_logs = self.env['whatsapp.bot.flow.log'].search(domain, order='id desc', limit=10)
        if message.chat_id_ref:
            pending_log = pending_logs.filtered(
                lambda log: not log.chat_id or log.chat_id.id == message.chat_id_ref.id
            )[:1]
        else:
            pending_log = pending_logs[:1]
        if not pending_log:
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
        elif waiting_step.action_type == 'wait_response':
            variables['last_reply'] = inbound_value

        resume_step = False
        reply_token = (message.button_payload or message.list_item_id or '').strip()
        if reply_token:
            source_button_step = self.step_ids.filtered(
                lambda step: step.action_type == 'send_buttons' and step.next_step_id.id == waiting_step.id
            )[:1]
            if not source_button_step and waiting_step.action_type == 'send_buttons':
                source_button_step = waiting_step

            if source_button_step:
                button = source_button_step.button_ids.filtered(
                    lambda btn: (btn.button_id or '').strip() == reply_token and btn.next_step_id
                )[:1]
                if button:
                    resume_step = button.next_step_id

        if waiting_step.action_type == 'send_buttons':
            if not reply_token:
                log.write({
                    'status': 'pending',
                    'variables': json.dumps(variables),
                })
                return log
            if not resume_step:
                _logger.info(
                    "Flow '%s' received unmatched button payload '%s' for step '%s'.",
                    self.name, reply_token, waiting_step.name,
                )
                log.write({
                    'status': 'pending',
                    'variables': json.dumps(variables),
                })
                return log

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
            return {'stop': True, 'status': 'pending'}

        elif step.action_type == 'wait_response':
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
        ('end', 'End Flow'),
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

    @api.constrains('action_type', 'template_id', 'media_id', 'button_ids', 'condition_type', 'condition_true_step', 'condition_false_step', 'http_url')
    def _check_step_configuration(self):
        if self.env.context.get('skip_flow_step_validation'):
            return
        for step in self:
            if step.action_type == 'send_template' and not step.template_id:
                raise ValidationError(f'Step "{step.name}" requires a template.')
            if step.action_type == 'send_media' and not step.media_id:
                raise ValidationError(f'Step "{step.name}" requires a media record.')
            if step.action_type == 'send_buttons' and not step.button_ids:
                raise ValidationError(f'Step "{step.name}" requires at least one button.')
            if step.action_type == 'condition':
                if not step.condition_type:
                    raise ValidationError(f'Step "{step.name}" requires a condition type.')
                if not step.condition_true_step and not step.condition_false_step:
                    raise ValidationError(
                        f'Step "{step.name}" must route to at least one target step.'
                    )
            if step.action_type == 'http_request' and not step.http_url:
                raise ValidationError(f'Step "{step.name}" requires a request URL.')


class WhatsAppBotFlowButton(models.Model):
    """Buttons in a bot flow step"""
    _name = 'whatsapp.bot.flow.button'
    _description = 'Bot Flow Button'
    _button_id_step_unique = models.Constraint(
        'unique(step_id, button_id)',
        'Button IDs must be unique per flow step.',
    )
    
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
            phone = self.contact_id.mobile or self.contact_id.phone
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
