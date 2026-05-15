# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class WhatsAppContactSegment(models.Model):
    """Advanced Contact Segmentation for WhatsApp Marketing"""
    _name = 'whatsapp.contact.segment'
    _description = 'WhatsApp Contact Segment'
    _rec_name = 'name'

    name = fields.Char('Segment Name', required=True)
    description = fields.Text('Description')
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account')
    active = fields.Boolean('Active', default=True)
    
    # Segmentation Criteria
    segment_type = fields.Selection([
        ('manual', 'Manual Selection'),
        ('auto_tag', 'Auto-Tag Based'),
        ('behavior', 'Behavior-Based'),
        ('demographics', 'Demographics-Based'),
        ('engagement', 'Engagement-Based'),
        ('revenue', 'Revenue-Based'),
        ('custom_filter', 'Custom Filter'),
    ], string='Segment Type', default='manual')
    
    # Tag-based segmentation
    manual_contact_ids = fields.Many2many(
        'res.partner',
        relation='whatsapp_segment_manual_partner_rel',
        string='Manual Contacts',
        help='Contacts explicitly included in this segment.'
    )
    tag_ids = fields.Many2many(
        'res.partner.category',
        relation='whatsapp_segment_tag_any_rel',
        column1='segment_id',
        column2='category_id',
        string='Tags (Any)',
        help='Contacts with any of these tags'
    )
    tag_all_ids = fields.Many2many(
        'res.partner.category', 
        relation='whatsapp_segment_tag_all_rel',
        column1='segment_id',
        column2='category_id',
        string='Tags (All)', 
        help='Contacts with ALL these tags'
    )
    tag_exclude_ids = fields.Many2many(
        'res.partner.category', 
        relation='whatsapp_segment_tag_exclude_rel',
        column1='segment_id',
        column2='category_id',
        string='Exclude Tags', 
        help='Exclude contacts with these tags'
    )
    
    # Behavior-based criteria
    min_message_count = fields.Integer('Min Messages Received', default=0)
    max_message_count = fields.Integer('Max Messages Received', default=999999)
    last_message_days = fields.Integer('Last Message (days ago)', help='Contacts who messaged in last N days')
    inactive_days = fields.Integer('Inactive (days)', help='Contacts inactive for N days')
    engagement_level = fields.Selection([
        ('very_low', 'Very Low'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('very_high', 'Very High'),
    ], string='Engagement Level')
    
    # Demographics
    country_code = fields.Char('Country Code', size=2)
    min_age = fields.Integer('Min Age')
    max_age = fields.Integer('Max Age')
    gender = fields.Selection([('M', 'Male'), ('F', 'Female'), ('O', 'Other')])
    
    # Revenue-based
    min_lifetime_value = fields.Float('Min Lifetime Value')
    max_lifetime_value = fields.Float('Max Lifetime Value')
    
    # Custom domain filter
    domain_filter = fields.Text('Custom Domain Filter', 
                               help='Advanced: Use Odoo domain syntax. e.g. [("name", "ilike", "John")]')
    
    # Statistics
    contact_count = fields.Integer('Contact Count', compute='_compute_contact_count', store=True)
    contact_ids = fields.Many2many(
        'res.partner',
        relation='whatsapp_segment_computed_partner_rel',
        string='Contacts',
        compute='_compute_contacts',
        store=True,
    )
    
    # Timeline
    created_date = fields.Datetime('Created', readonly=True, default=fields.Datetime.now)
    
    @api.depends(
        'segment_type',
        'manual_contact_ids',
        'tag_ids',
        'tag_all_ids',
        'tag_exclude_ids',
        'min_message_count',
        'max_message_count',
        'last_message_days',
        'inactive_days',
        'engagement_level',
        'country_code',
        'min_lifetime_value',
        'max_lifetime_value',
        'domain_filter',
    )
    def _compute_contacts(self):
        """Dynamically compute contacts matching segment criteria"""
        Partner = self.env['res.partner'].sudo()
        for record in self:
            domain = record._base_partner_domain()
            
            if record.segment_type == 'manual':
                record.contact_ids = record.manual_contact_ids
            
            elif record.segment_type == 'auto_tag':
                if record.tag_ids:
                    # Contacts with any of these tags
                    domain.extend([('category_id', 'in', record.tag_ids.ids)])
                for tag in record.tag_all_ids:
                    domain.append(('category_id', 'in', tag.ids))
                if record.tag_exclude_ids:
                    domain.extend([('category_id', 'not in', record.tag_exclude_ids.ids)])
                record.contact_ids = Partner.search(domain)
            
            elif record.segment_type == 'behavior':
                # Based on message history
                message_domain = [
                    ('account_id', '=', record.account_id.id),
                    ('direction', '=', 'inbound'),
                    ('partner_id', '!=', False),
                ]
                messages = self.env['whatsapp.message'].sudo().search(message_domain)
                
                # Filter by message count
                partner_msg_count = {}
                for msg in messages:
                    if msg.partner_id:
                        partner_msg_count[msg.partner_id.id] = partner_msg_count.get(msg.partner_id.id, 0) + 1
                
                valid_partner_ids = [p_id for p_id, count in partner_msg_count.items() 
                                     if record.min_message_count <= count <= record.max_message_count]
                
                # Filter by last message date
                if record.last_message_days:
                    cutoff_date = datetime.now() - timedelta(days=record.last_message_days)
                    recent_msgs = messages.filtered(lambda m: m.create_date >= cutoff_date)
                    recent_partner_ids = set(m.partner_id.id for m in recent_msgs if m.partner_id)
                    valid_partner_ids = list(set(valid_partner_ids) & recent_partner_ids)

                if record.inactive_days:
                    inactive_cutoff = datetime.now() - timedelta(days=record.inactive_days)
                    active_partner_ids = set(messages.filtered(lambda m: m.create_date >= inactive_cutoff).mapped('partner_id').ids)
                    valid_partner_ids = list(set(valid_partner_ids) - active_partner_ids)
                
                domain.extend([('id', 'in', valid_partner_ids)])
                record.contact_ids = Partner.search(domain)
            
            elif record.segment_type == 'custom_filter':
                try:
                    if record.domain_filter:
                        custom_domain = safe_eval(record.domain_filter)
                        if not isinstance(custom_domain, (list, tuple)):
                            raise ValueError("Custom domain must be a list or tuple.")
                        domain.extend(custom_domain)
                except Exception as e:
                    _logger.error(f"Custom filter error on segment {record.name}: {e}")
                    record.contact_ids = Partner.browse([])
                    continue
                record.contact_ids = Partner.search(domain)
            
            elif record.segment_type == 'demographics':
                if record.country_code:
                    domain.append(('country_id.code', '=', record.country_code.upper()))
                if 'gender' in Partner._fields and record.gender:
                    domain.append(('gender', '=', record.gender))
                if 'age' in Partner._fields:
                    if record.min_age:
                        domain.append(('age', '>=', record.min_age))
                    if record.max_age:
                        domain.append(('age', '<=', record.max_age))
                record.contact_ids = Partner.search(domain)

            elif record.segment_type == 'revenue':
                contacts = Partner.search(domain)
                if record.min_lifetime_value or record.max_lifetime_value:
                    valid_ids = []
                    for partner in contacts:
                        revenue = sum(self.env['sale.order'].sudo().search([
                            ('partner_id', 'child_of', partner.id),
                            ('state', 'in', ['sale', 'done']),
                        ]).mapped('amount_total'))
                        if record.min_lifetime_value and revenue < record.min_lifetime_value:
                            continue
                        if record.max_lifetime_value and revenue > record.max_lifetime_value:
                            continue
                        valid_ids.append(partner.id)
                    contacts = Partner.browse(valid_ids)
                record.contact_ids = contacts
            
            else:
                record.contact_ids = Partner.browse([])

    def _base_partner_domain(self):
        self.ensure_one()
        domain = [('active', '=', True)]
        if 'mobile' in self.env['res.partner']._fields:
            domain = ['|', ('phone', '!=', False), ('mobile', '!=', False)] + domain
        else:
            domain = [('phone', '!=', False)] + domain
        return domain

    @api.depends('contact_ids')
    def _compute_contact_count(self):
        """Count contacts in segment"""
        for record in self:
            record.contact_count = len(record.contact_ids)

    def action_add_contacts(self):
        """Add contacts manually to this segment"""
        return {
            'name': 'Add Contacts',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'whatsapp.contact.segment.wizard',
            'target': 'new',
            'context': {'default_segment_id': self.id}
        }

    def action_refresh_contacts(self):
        """Refresh the computed contact list and show the resulting count."""
        self.invalidate_recordset(['contact_ids', 'contact_count'])
        self._compute_contacts()
        self._compute_contact_count()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Segment Refreshed',
                'message': f'{self.contact_count} contact(s) match this segment.',
                'type': 'success',
            }
        }

    def action_send_campaign(self):
        """Create and send campaign to this segment"""
        self.ensure_one()
        self._compute_contacts()
        if not self.contact_ids:
            raise UserError("This segment does not contain any contacts with a phone number.")
        return {
            'name': 'Send Campaign',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'whatsapp.campaign',
            'target': 'new',
            'context': {
                'default_target_type': 'segment',
                'default_segment_id': self.id,
                'default_partner_ids': [(6, 0, self.contact_ids.ids)],
            }
        }


class WhatsAppContactSegmentWizard(models.TransientModel):
    """Wizard to add contacts to segment"""
    _name = 'whatsapp.contact.segment.wizard'
    _description = 'Add Contacts to Segment'
    
    segment_id = fields.Many2one('whatsapp.contact.segment', required=True)
    partner_ids = fields.Many2many('res.partner', string='Contacts to Add')
    action_type = fields.Selection([
        ('add', 'Add to Segment'),
        ('remove', 'Remove from Segment'),
        ('replace', 'Replace Segment Contacts'),
    ], default='add')
    
    def action_apply(self):
        """Apply the selected action"""
        self.ensure_one()
        
        if self.action_type == 'add':
            self.segment_id.manual_contact_ids = [(4, pid) for pid in self.partner_ids.ids]
        elif self.action_type == 'remove':
            self.segment_id.manual_contact_ids = [(3, pid) for pid in self.partner_ids.ids]
        elif self.action_type == 'replace':
            self.segment_id.manual_contact_ids = [(6, 0, self.partner_ids.ids)]
        self.segment_id.action_refresh_contacts()
        return {'type': 'ir.actions.act_window_close'}
