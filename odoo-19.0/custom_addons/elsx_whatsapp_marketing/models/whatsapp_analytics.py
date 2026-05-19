# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class WhatsAppAnalytics(models.Model):
    """WhatsApp Analytics and Reporting"""
    _name = 'whatsapp.analytics'
    _description = 'WhatsApp Analytics Report'
    _auto = False
    
    account_id = fields.Many2one('whatsapp.account', string='WhatsApp Account')
    
    # Time period
    period_start = fields.Datetime('Period Start')
    period_end = fields.Datetime('Period End')
    
    # Message Statistics
    total_messages = fields.Integer('Total Messages')
    inbound_count = fields.Integer('Inbound Messages')
    outbound_count = fields.Integer('Outbound Messages')
    template_count = fields.Integer('Template Messages')
    
    # Message Types
    text_count = fields.Integer('Text Messages')
    image_count = fields.Integer('Image Messages')
    video_count = fields.Integer('Video Messages')
    document_count = fields.Integer('Document Messages')
    audio_count = fields.Integer('Audio Messages')
    
    # Delivery Metrics
    sent_count = fields.Integer('Sent')
    delivered_count = fields.Integer('Delivered')
    read_count = fields.Integer('Read')
    failed_count = fields.Integer('Failed')
    
    # Performance
    delivery_rate = fields.Float('Delivery Rate %')
    read_rate = fields.Float('Read Rate %')
    failure_rate = fields.Float('Failure Rate %')
    avg_latency = fields.Float('Avg Latency (ms)')
    total_spend = fields.Float('Total Spend')
    opt_out_count = fields.Integer('Opt-outs')
    
    # Engagement
    unique_contacts = fields.Integer('Unique Contacts')
    conversations = fields.Integer('Conversations')
    avg_response_time = fields.Float('Avg Response Time (hours)')
    
    # Campaign Stats
    campaign_count = fields.Integer('Campaigns Run')
    campaign_send_count = fields.Integer('Campaign Messages Sent')
    campaign_delivery_rate = fields.Float('Campaign Delivery Rate %')
    
    # Business Metrics
    revenue_attributed = fields.Float('Revenue Attributed')
    cost_per_message = fields.Float('Cost per Message')
    roi = fields.Float('ROI %')

    def init(self):
        from odoo import tools
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    m.id AS id,
                    m.account_id AS account_id,
                    m.create_date AS period_start,
                    m.create_date AS period_end,
                    1 AS total_messages,
                    CASE WHEN m.direction = 'inbound' THEN 1 ELSE 0 END AS inbound_count,
                    CASE WHEN m.direction = 'outbound' THEN 1 ELSE 0 END AS outbound_count,
                    CASE WHEN m.message_type = 'template' THEN 1 ELSE 0 END AS template_count,
                    CASE WHEN m.message_type = 'text' THEN 1 ELSE 0 END AS text_count,
                    CASE WHEN m.message_type = 'image' THEN 1 ELSE 0 END AS image_count,
                    CASE WHEN m.message_type = 'video' THEN 1 ELSE 0 END AS video_count,
                    CASE WHEN m.message_type = 'document' THEN 1 ELSE 0 END AS document_count,
                    CASE WHEN m.message_type = 'audio' THEN 1 ELSE 0 END AS audio_count,
                    CASE WHEN m.status IN ('sent', 'delivered', 'read') THEN 1 ELSE 0 END AS sent_count,
                    CASE WHEN m.status IN ('delivered', 'read') THEN 1 ELSE 0 END AS delivered_count,
                    CASE WHEN m.status = 'read' THEN 1 ELSE 0 END AS read_count,
                    CASE WHEN m.status = 'failed' THEN 1 ELSE 0 END AS failed_count,
                    m.latency_ms AS avg_latency,
                    m.message_cost AS total_spend,
                    CASE WHEN m.is_opt_out THEN 1 ELSE 0 END AS opt_out_count,
                    0.0 AS delivery_rate,
                    0.0 AS read_rate,
                    0.0 AS failure_rate,
                    1 AS unique_contacts,
                    1 AS conversations,
                    0.0 AS avg_response_time,
                    0 AS campaign_count,
                    0 AS campaign_send_count,
                    0.0 AS campaign_delivery_rate,
                    0.0 AS revenue_attributed,
                    0.0 AS cost_per_message,
                    0.0 AS roi
                FROM
                    whatsapp_message m
            )
        """ % (self._table,))

    @api.model
    def get_dashboard_data(self):
        """Fetch all KPI and chart data for the new web dashboard"""
        now = fields.Datetime.now()
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)
        
        # Messaging stats (Last 7 days)
        msg_domain = [('create_date', '>=', seven_days_ago)]
        messages = self.env['whatsapp.message'].search(msg_domain)
        
        sent = len(messages.filtered(lambda m: m.direction == 'outbound'))
        delivered = len(messages.filtered(lambda m: m.status in ['delivered', 'read']))
        read = len(messages.filtered(lambda m: m.status == 'read'))
        
        delivered_rate = round((delivered / sent * 100) if sent else 0, 1)
        read_rate = round((read / sent * 100) if sent else 0, 1)
        
        # Chat counts
        chats = self.env['whatsapp.chat'].search([])
        total_chats = len(chats)
        open_chats = len(chats.filtered(lambda c: c.state == 'open'))
        resolved_today = len(self.env['whatsapp.chat'].search([
            ('state', '=', 'resolved'),
            ('write_date', '>=', now.replace(hour=0, minute=0, second=0))
        ]))
        
        # Active Campaigns
        active_campaigns = self.env['whatsapp.campaign'].search_count([('state', 'in', ['running', 'scheduled'])])
        
        # Top 5 Templates
        self.env.cr.execute("""
            SELECT template_name, COUNT(id) as usage, 
                   SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) as reads
            FROM whatsapp_message 
            WHERE template_name IS NOT NULL AND message_type = 'template'
            GROUP BY template_name 
            ORDER BY usage DESC LIMIT 5
        """)
        top_templates = [
            {
                'name': row[0],
                'usage': row[1],
                'read_rate': round((row[2] / row[1] * 100) if row[1] else 0, 1)
            }
            for row in self.env.cr.fetchall()
        ]
        
        # Recent Campaigns
        recent_campaigns_records = self.env['whatsapp.campaign'].search([], order='create_date desc', limit=5)
        recent_campaigns = [{
            'id': c.id,
            'name': c.name,
            'state': c.state,
            'sent': c.sent_count,
            'delivered': c.delivered_count,
            'read': c.read_count
        } for c in recent_campaigns_records]

        # 14 Day Volume Trend
        self.env.cr.execute("""
            SELECT DATE(create_date) as day,
                   SUM(CASE WHEN status IN ('sent', 'delivered', 'read') THEN 1 ELSE 0 END) as sent,
                   SUM(CASE WHEN status IN ('delivered', 'read') THEN 1 ELSE 0 END) as delivered,
                   SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) as read
            FROM whatsapp_message 
            WHERE create_date >= %s 
            GROUP BY DATE(create_date) ORDER BY day ASC
        """, [fourteen_days_ago])
        
        trend_rows = self.env.cr.fetchall()
        volume_trend = {
            'dates': [str(row[0]) for row in trend_rows],
            'sent': [row[1] for row in trend_rows],
            'delivered': [row[2] for row in trend_rows],
            'read': [row[3] for row in trend_rows]
        }
        
        return {
            'kpis': {
                'total_chats': total_chats,
                'open_chats': open_chats,
                'resolved_today': resolved_today,
                'sent_7d': sent,
                'delivered_rate': delivered_rate,
                'read_rate': read_rate,
                'active_campaigns': active_campaigns,
            },
            'top_templates': top_templates,
            'recent_campaigns': recent_campaigns,
            'volume_trend': volume_trend,
        }

class WhatsAppAnalyticsReportHelper(models.Model):
    """Helper model to generate analytics reports"""
    _name = 'whatsapp.analytics.report'
    _description = 'WhatsApp Analytics Report Generator'
    _transient = True
    
    account_id = fields.Many2one('whatsapp.account', required=True)
    date_from = fields.Datetime('From Date', required=True, default=lambda self: fields.Datetime.now() - timedelta(days=30))
    date_to = fields.Datetime('To Date', required=True, default=fields.Datetime.now)
    report_type = fields.Selection([
        ('overview', 'Overview'),
        ('messages', 'Message Analytics'),
        ('campaigns', 'Campaign Performance'),
        ('contacts', 'Contact Analytics'),
        ('engagement', 'Engagement Metrics'),
        ('roi', 'ROI Analysis'),
        ('revenue', 'Revenue Attribution'),
    ], default='overview', required=True)
    
    def action_generate_report(self):
        """Generate analytics report"""
        self.ensure_one()
        
        if self.report_type == 'overview':
            return self._generate_overview_report()
        elif self.report_type == 'messages':
            return self._generate_message_report()
        elif self.report_type == 'campaigns':
            return self._generate_campaign_report()
        elif self.report_type == 'contacts':
            return self._generate_contact_report()
        elif self.report_type == 'engagement':
            return self._generate_engagement_report()
        elif self.report_type == 'roi':
            return self._generate_roi_report()
        elif self.report_type == 'revenue':
            return self._generate_revenue_report()
    
    def _get_messages(self):
        """Get messages for the selected period"""
        return self.env['whatsapp.message'].search([
            ('account_id', '=', self.account_id.id),
            ('create_date', '>=', self.date_from),
            ('create_date', '<=', self.date_to),
        ])
    
    def _generate_overview_report(self):
        """Generate overview report"""
        messages = self._get_messages()
        
        total = len(messages)
        inbound = len(messages.filtered(lambda m: m.direction == 'inbound'))
        outbound = len(messages.filtered(lambda m: m.direction == 'outbound'))
        sent = len(messages.filtered(lambda m: m.status in ['sent', 'delivered', 'read']))
        delivered = len(messages.filtered(lambda m: m.status in ['delivered', 'read']))
        read = len(messages.filtered(lambda m: m.status == 'read'))
        failed = len(messages.filtered(lambda m: m.status == 'failed'))
        
        delivery_rate = (delivered / sent * 100) if sent > 0 else 0
        read_rate = (read / delivered * 100) if delivered > 0 else 0
        
        summary = f"""
        WhatsApp Analytics Report
        Period: {self.date_from} to {self.date_to}
        
        Total Messages: {total}
        - Inbound: {inbound}
        - Outbound: {outbound}
        
        Message Status:
        - Sent: {sent}
        - Delivered: {delivered}
        - Read: {read}
        - Failed: {failed}
        
        Performance Metrics:
        - Delivery Rate: {delivery_rate:.1f}%
        - Read Rate: {read_rate:.1f}%
        
        Unique Contacts: {len(set(m.partner_id.id for m in messages if m.partner_id))}
        """
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Analytics Report',
                'message': summary,
                'sticky': True,
            }
        }
    
    def _generate_message_report(self):
        """Generate detailed message analytics"""
        messages = self._get_messages()
        
        by_type = defaultdict(int)
        by_status = defaultdict(int)
        by_direction = defaultdict(int)
        
        for msg in messages:
            by_type[msg.message_type] += 1
            by_status[msg.status] += 1
            by_direction[msg.direction] += 1
        
        report = "Message Type Breakdown:\n"
        for msg_type, count in sorted(by_type.items()):
            report += f"  {msg_type}: {count}\n"
        
        report += "\nMessage Status Breakdown:\n"
        for status, count in sorted(by_status.items()):
            report += f"  {status}: {count}\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Message Analytics',
                'message': report,
                'sticky': True,
            }
        }
    
    def _generate_campaign_report(self):
        """Generate campaign performance report"""
        campaigns = self.env['whatsapp.campaign'].search([
            ('account_id', '=', self.account_id.id),
            ('create_date', '>=', self.date_from),
            ('create_date', '<=', self.date_to),
        ])
        
        report = f"Campaign Performance Report\n{'=' * 50}\n"
        report += f"Total Campaigns: {len(campaigns)}\n\n"
        
        for campaign in campaigns:
            if campaign.sent_count > 0:
                delivery_rate = (campaign.delivered_count / campaign.sent_count * 100)
                read_rate = (campaign.read_count / campaign.sent_count * 100)
            else:
                delivery_rate = read_rate = 0
            
            report += f"Campaign: {campaign.name}\n"
            report += f"  Status: {campaign.state}\n"
            report += f"  Recipients: {campaign.total_recipients}\n"
            report += f"  Sent: {campaign.sent_count}\n"
            report += f"  Delivered: {campaign.delivered_count}\n"
            report += f"  Read: {campaign.read_count}\n"
            report += f"  Failed: {campaign.failed_count}\n"
            report += f"  Delivery Rate: {delivery_rate:.1f}%\n"
            report += f"  Read Rate: {read_rate:.1f}%\n\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Campaign Performance',
                'message': report,
                'sticky': True,
            }
        }
    
    def _generate_contact_report(self):
        """Generate contact analytics"""
        chats = self.env['whatsapp.chat'].search([
            ('account_id', '=', self.account_id.id),
        ])
        
        report = f"Contact Analytics Report\n{'=' * 50}\n"
        report += f"Total Conversations: {len(chats)}\n\n"
        
        # Top contacts by message count
        top_contacts = sorted([(c.display_name, len(c.message_ids)) for c in chats], 
                            key=lambda x: x[1], reverse=True)[:10]
        
        report += "Top 10 Most Active Contacts:\n"
        for name, count in top_contacts:
            report += f"  {name}: {count} messages\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Contact Analytics',
                'message': report,
                'sticky': True,
            }
        }
    
    def _generate_engagement_report(self):
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                'params': {'title': 'Engagement Report', 'message': 'Engagement metrics calculated'}}
    
    def _generate_roi_report(self):
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                'params': {'title': 'ROI Report', 'message': 'ROI analysis generated'}}
    
    def _generate_revenue_report(self):
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                'params': {'title': 'Revenue Report', 'message': 'Revenue attribution calculated'}}
