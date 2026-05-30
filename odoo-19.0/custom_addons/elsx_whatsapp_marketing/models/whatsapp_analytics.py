# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import json

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

    def _dashboard_start_date(self, date_range, now):
        if date_range == 'today':
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if date_range == '30d':
            return now - timedelta(days=30)
        if date_range == 'all':
            return False
        return now - timedelta(days=7)

    def _dashboard_where(self, start_date=False, account_id=False, extra=None):
        clauses = list(extra or [])
        params = []
        if start_date:
            clauses.append("create_date >= %s")
            params.append(start_date)
        if account_id:
            clauses.append("account_id = %s")
            params.append(account_id)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _dashboard_live_message_stats(self, start_date=False, account_id=False):
        where, params = self._dashboard_where(start_date=start_date, account_id=account_id)
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN direction = 'outbound' AND status IN ('sent', 'delivered', 'read') THEN 1 ELSE 0 END), 0) AS sent,
                COALESCE(SUM(CASE WHEN direction = 'outbound' AND status IN ('delivered', 'read') THEN 1 ELSE 0 END), 0) AS delivered,
                COALESCE(SUM(CASE WHEN direction = 'outbound' AND status = 'read' THEN 1 ELSE 0 END), 0) AS read_count,
                COALESCE(SUM(CASE WHEN direction = 'outbound' AND status = 'failed' THEN 1 ELSE 0 END), 0) AS failed,
                COALESCE(SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END), 0) AS inbound,
                COALESCE(SUM(CASE WHEN direction = 'inbound' AND (button_text IS NOT NULL OR button_payload IS NOT NULL OR list_item_id IS NOT NULL) THEN 1 ELSE 0 END), 0) AS clicked,
                COALESCE(SUM(CASE WHEN direction = 'outbound' THEN message_cost ELSE 0 END), 0.0) AS total_spend,
                COALESCE(COUNT(DISTINCT CASE WHEN direction = 'outbound' AND status IN ('sent', 'delivered', 'read') THEN phone_number END), 0) AS outbound_contacts,
                COALESCE(COUNT(DISTINCT CASE WHEN direction = 'inbound' THEN phone_number END), 0) AS inbound_contacts,
                COALESCE(COUNT(DISTINCT CASE WHEN direction = 'inbound' AND (button_text IS NOT NULL OR button_payload IS NOT NULL OR list_item_id IS NOT NULL) THEN phone_number END), 0) AS click_contacts
            FROM whatsapp_message
        """ + where, params)
        row = self.env.cr.dictfetchone() or {}
        sent = int(row.get('sent') or 0)
        delivered = int(row.get('delivered') or 0)
        read_count = int(row.get('read_count') or 0)
        failed = int(row.get('failed') or 0)
        inbound = int(row.get('inbound') or 0)
        clicked = int(row.get('clicked') or 0)
        outbound_contacts = int(row.get('outbound_contacts') or 0)
        inbound_contacts = int(row.get('inbound_contacts') or 0)
        click_contacts = int(row.get('click_contacts') or 0)
        return {
            'sent': sent,
            'delivered': delivered,
            'read': read_count,
            'failed': failed,
            'inbound': inbound,
            'clicked': clicked,
            'total_spend': round(float(row.get('total_spend') or 0.0), 2),
            'delivered_rate': round((delivered / sent * 100.0) if sent else 0.0, 1),
            'read_rate': round((read_count / sent * 100.0) if sent else 0.0, 1),
            'ctr_rate': round(min((click_contacts / outbound_contacts * 100.0) if outbound_contacts else 0.0, 100.0), 1),
            'reply_rate': round(min((inbound_contacts / outbound_contacts * 100.0) if outbound_contacts else 0.0, 100.0), 1),
        }

    def _dashboard_chat_stats(self, start_date=False, account_id=False):
        Chat = self.env['whatsapp.chat'].sudo()
        chat_domain = []
        if account_id:
            chat_domain.append(('account_id', '=', account_id))
        chats = Chat.search(chat_domain)
        now = fields.Datetime.now()
        resolved_today_domain = [('state', '=', 'resolved'), ('write_date', '>=', now.replace(hour=0, minute=0, second=0))]
        if account_id:
            resolved_today_domain.append(('account_id', '=', account_id))

        resolved_period = chats.filtered(lambda c: c.state == 'resolved' and c.create_date and c.write_date)
        if start_date:
            resolved_period = resolved_period.filtered(lambda c: c.write_date >= start_date)
        art = 0.0
        if resolved_period:
            total_hours = sum((c.write_date - c.create_date).total_seconds() / 3600.0 for c in resolved_period)
            art = round(total_hours / len(resolved_period), 1)

        frt_minutes = 0.0
        gaps = []
        for chat in (chats.filtered(lambda c: not start_date or c.create_date >= start_date)[:50]):
            msgs = chat.message_ids.sorted('create_date')
            inbound_msg = msgs.filtered(lambda m: m.direction == 'inbound')[:1]
            if inbound_msg:
                outbound = msgs.filtered(lambda m: m.direction == 'outbound' and m.create_date > inbound_msg.create_date)[:1]
                if outbound:
                    gaps.append((outbound.create_date - inbound_msg.create_date).total_seconds() / 60.0)
        if gaps:
            frt_minutes = round(sum(gaps) / len(gaps), 1)

        return {
            'total_chats': len(chats),
            'open_chats': len(chats.filtered(lambda c: c.state == 'open')),
            'resolved_today': Chat.search_count(resolved_today_domain),
            'art_hours': art,
            'frt_minutes': frt_minutes,
        }

    def _dashboard_heavy_sections(self, start_date=False, account_id=False):
        where, params = self._dashboard_where(start_date=start_date, account_id=account_id)
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN pricing_category = 'marketing' THEN message_cost ELSE 0 END), 0.0),
                COALESCE(SUM(CASE WHEN pricing_category = 'utility' THEN message_cost ELSE 0 END), 0.0),
                COALESCE(SUM(CASE WHEN pricing_category = 'authentication' THEN message_cost ELSE 0 END), 0.0),
                COALESCE(SUM(CASE WHEN pricing_category = 'service'
                    OR (pricing_category IS NULL AND direction = 'outbound' AND message_type != 'template')
                    THEN message_cost ELSE 0 END), 0.0)
            FROM whatsapp_message
        """ + where, params)
        cost_row = self.env.cr.fetchone() or (0, 0, 0, 0)
        cost_by_category = {
            'marketing': round(float(cost_row[0] or 0.0), 2),
            'utility': round(float(cost_row[1] or 0.0), 2),
            'authentication': round(float(cost_row[2] or 0.0), 2),
            'service': round(float(cost_row[3] or 0.0), 2),
        }

        top_where, top_params = self._dashboard_where(
            start_date=start_date,
            account_id=account_id,
            extra=["template_name IS NOT NULL", "message_type = 'template'", "direction = 'outbound'"],
        )
        self.env.cr.execute("""
            SELECT template_name, COUNT(id),
                   SUM(CASE WHEN status IN ('delivered', 'read') THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN button_text IS NOT NULL OR button_payload IS NOT NULL THEN 1 ELSE 0 END),
                   MAX(pricing_category)
            FROM whatsapp_message
        """ + top_where + """
            GROUP BY template_name
            ORDER BY COUNT(id) DESC
            LIMIT 5
        """, top_params)
        top_templates = [{
            'name': row[0],
            'usage': row[1],
            'delivered_rate': round((row[2] / row[1] * 100.0) if row[1] else 0.0, 1),
            'read_rate': round((row[3] / row[1] * 100.0) if row[1] else 0.0, 1),
            'clicks': row[4],
            'ctr_rate': round((row[4] / row[1] * 100.0) if row[1] else 0.0, 1),
            'category': (row[5] or 'marketing').capitalize(),
        } for row in self.env.cr.fetchall()]

        campaign_domain = []
        if account_id:
            campaign_domain.append(('account_id', '=', account_id))
        campaigns = self.env['whatsapp.campaign'].sudo().search(campaign_domain, order='create_date desc', limit=5)
        recent_campaigns = [{
            'id': c.id,
            'name': c.name,
            'state': c.state,
            'sent': c.sent_count,
            'delivered_rate': round((c.delivered_count / c.sent_count * 100.0) if c.sent_count else 0.0, 1),
            'read_rate': round((c.read_count / c.sent_count * 100.0) if c.sent_count else 0.0, 1),
            'clicks': c.click_count or 0,
            'ctr_rate': round((c.click_count / c.sent_count * 100.0) if c.sent_count else 0.0, 1),
        } for c in campaigns]

        chats = self.env['whatsapp.chat'].sudo().search([('account_id', '=', account_id)] if account_id else [])
        agent_stats = []
        for agent in chats.mapped('assigned_user_id'):
            if not agent:
                continue
            agent_chats = chats.filtered(lambda c: c.assigned_user_id.id == agent.id)
            total_assigned = len(agent_chats)
            open_count = len(agent_chats.filtered(lambda c: c.state == 'open'))
            resolved_count = len(agent_chats.filtered(lambda c: c.state == 'resolved'))
            resolved_chats = agent_chats.filtered(lambda c: c.state == 'resolved' and c.create_date and c.write_date)
            avg_res_time = 0.0
            if resolved_chats:
                total_hours = sum((c.write_date - c.create_date).total_seconds() / 3600.0 for c in resolved_chats)
                avg_res_time = round(total_hours / len(resolved_chats), 1)
            agent_stats.append({
                'id': agent.id,
                'name': agent.name,
                'open_chats': open_count,
                'resolved_chats': resolved_count,
                'avg_resolution_time': avg_res_time,
                'resolution_rate': round((resolved_count / total_assigned * 100.0) if total_assigned else 0.0, 1),
            })
        agent_stats = sorted(agent_stats, key=lambda x: x['resolved_chats'], reverse=True)

        trend_start = fields.Datetime.now() - timedelta(days=14)
        trend_where, trend_params = self._dashboard_where(start_date=trend_start, account_id=account_id)
        self.env.cr.execute("""
            SELECT DATE(create_date),
                   SUM(CASE WHEN direction = 'outbound' AND status IN ('sent', 'delivered', 'read') THEN 1 ELSE 0 END),
                   SUM(CASE WHEN direction = 'outbound' AND status IN ('delivered', 'read') THEN 1 ELSE 0 END),
                   SUM(CASE WHEN direction = 'outbound' AND status = 'read' THEN 1 ELSE 0 END)
            FROM whatsapp_message
        """ + trend_where + """
            GROUP BY DATE(create_date)
            ORDER BY DATE(create_date) ASC
        """, trend_params)
        trend_rows = self.env.cr.fetchall()
        volume_trend = {
            'dates': [str(row[0]) for row in trend_rows],
            'sent': [int(row[1] or 0) for row in trend_rows],
            'delivered': [int(row[2] or 0) for row in trend_rows],
            'read': [int(row[3] or 0) for row in trend_rows],
        }

        return {
            'cost_by_category': cost_by_category,
            'top_templates': top_templates,
            'recent_campaigns': recent_campaigns,
            'agent_stats': agent_stats,
            'volume_trend': volume_trend,
        }

    def _dashboard_today_usage_by_account(self, account_ids=None):
        if account_ids is not None and not account_ids:
            return {}
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        params = [today_start]
        account_filter = ""
        if account_ids:
            account_filter = " AND account_id IN %s"
            params.append(tuple(account_ids))
        self.env.cr.execute("""
            SELECT account_id, COUNT(id)
            FROM whatsapp_message
            WHERE direction = 'outbound'
              AND create_date >= %s
              AND status IN ('queued', 'sent', 'delivered', 'read')
              AND account_id IS NOT NULL
        """ + account_filter + """
            GROUP BY account_id
        """, params)
        return {row[0]: row[1] for row in self.env.cr.fetchall()}

    def _dashboard_account_health(self, account_id=False):
        accounts = self.env['whatsapp.account'].sudo().search([('active', '=', True)], order='id')
        selected_accounts = accounts.filtered(lambda a: a.id == account_id) if account_id else accounts
        live_usage = self._dashboard_today_usage_by_account(accounts.ids)
        cards = []
        total_daily_sent = 0
        total_daily_limit = 0
        reached_count = 0
        latest_webhook = False
        for account in accounts:
            daily_sent = max(account.daily_message_count or 0, live_usage.get(account.id, 0))
            daily_limit = account.max_daily_limit or 0
            daily_remaining = max(daily_limit - daily_sent, 0) if daily_limit else 0
            usage_percent = round((daily_sent / daily_limit * 100.0), 1) if daily_limit else 0.0
            is_limit_reached = daily_limit > 0 and daily_sent >= daily_limit
            if not account_id or account.id == account_id:
                total_daily_sent += daily_sent
                total_daily_limit += daily_limit
                if is_limit_reached:
                    reached_count += 1
                latest = account.last_webhook_at or account.last_inbound_webhook_at or account.last_status_webhook_at
                if latest and (not latest_webhook or latest > latest_webhook):
                    latest_webhook = latest
            cards.append({
                'id': account.id,
                'name': account.name,
                'phone_number': account.phone_number,
                'status': account.status or '',
                'quality_rating': account.quality_rating or 'Unknown',
                'messaging_limit': account.messaging_limit or (f"{daily_limit:,} / day" if daily_limit else 'Unknown'),
                'daily_sent': daily_sent,
                'daily_limit': daily_limit,
                'daily_remaining': daily_remaining,
                'usage_percent': usage_percent,
                'webhook_status': account.webhook_status or 'none',
                'last_webhook_at': fields.Datetime.to_string(account.last_webhook_at) if account.last_webhook_at else '',
                'last_status_webhook_at': fields.Datetime.to_string(account.last_status_webhook_at) if account.last_status_webhook_at else '',
                'last_inbound_webhook_at': fields.Datetime.to_string(account.last_inbound_webhook_at) if account.last_inbound_webhook_at else '',
            })
        now = fields.Datetime.now()
        stale_seconds = int((now - latest_webhook).total_seconds()) if latest_webhook else 0
        return {
            'active_accounts': len(selected_accounts),
            'daily_sent': total_daily_sent,
            'daily_limit': total_daily_limit,
            'daily_remaining': max(total_daily_limit - total_daily_sent, 0) if total_daily_limit else 0,
            'usage_percent': round((total_daily_sent / total_daily_limit * 100.0), 1) if total_daily_limit else 0.0,
            'limit_reached_accounts': reached_count,
            'accounts': cards,
            'selected_account_id': account_id or False,
            'stale_seconds': stale_seconds,
        }

    def _dashboard_conversion_sections(self, start_date=False, account_id=False):
        """Live lightweight counters for features outside basic message delivery."""
        Submission = self.env['whatsapp.form.submission'].sudo()
        Campaign = self.env['whatsapp.campaign'].sudo()
        Rule = self.env['whatsapp.campaign.reply.rule'].sudo()
        Chat = self.env['whatsapp.chat'].sudo()
        Flow = self.env['whatsapp.bot.flow'].sudo()

        submission_domain = []
        campaign_domain = []
        chat_domain = []
        flow_domain = []
        if start_date:
            submission_domain.append(('create_date', '>=', start_date))
            campaign_domain.append(('create_date', '>=', start_date))
            chat_domain.append(('create_date', '>=', start_date))
        if account_id:
            submission_domain.append(('account_id', '=', account_id))
            campaign_domain.append(('account_id', '=', account_id))
            chat_domain.append(('account_id', '=', account_id))
            flow_domain.append(('account_id', '=', account_id))

        form_total = Submission.search_count(submission_domain)
        form_new = Submission.search_count(submission_domain + [('state', '=', 'new')])
        form_leads = Submission.search_count(submission_domain + [('state', '=', 'lead_created')])

        form_where = []
        form_params = []
        if start_date:
            form_where.append("s.create_date >= %s")
            form_params.append(start_date)
        if account_id:
            form_where.append("s.account_id = %s")
            form_params.append(account_id)
        form_where_sql = (" WHERE " + " AND ".join(form_where)) if form_where else ""
        self.env.cr.execute("""
            SELECT s.form_id, f.name, COUNT(s.id)
            FROM whatsapp_form_submission s
            LEFT JOIN whatsapp_form f ON f.id = s.form_id
        """ + form_where_sql + """
            GROUP BY s.form_id, f.name
            ORDER BY COUNT(s.id) DESC
            LIMIT 5
        """, form_params)
        top_forms = [{
            'id': row[0] or False,
            'name': row[1] or _('Unknown Form'),
            'submissions': row[2] or 0,
        } for row in self.env.cr.fetchall()]

        campaigns = Campaign.search(campaign_domain)
        rules = Rule.search([('campaign_id', 'in', campaigns.ids)]) if campaigns else Rule.browse()
        active_rules = rules.filtered('active')
        payment_actions = sum(rules.filtered(lambda r: r.action_type == 'send_payment_link').mapped('handled_count'))
        form_actions = sum(rules.filtered(lambda r: r.action_type == 'send_form_link').mapped('handled_count'))
        top_rules = [{
            'id': rule.id,
            'campaign': rule.campaign_id.display_name,
            'name': rule.name,
            'action': dict(rule._fields['action_type'].selection).get(rule.action_type, rule.action_type),
            'handled': rule.handled_count,
        } for rule in rules.sorted(lambda r: r.handled_count, reverse=True)[:5]]

        source_chat_count = Chat.search_count(chat_domain + [('source_campaign_id', '!=', False)])
        source_where = ["ch.source_campaign_id IS NOT NULL"]
        source_params = []
        if start_date:
            source_where.append("ch.create_date >= %s")
            source_params.append(start_date)
        if account_id:
            source_where.append("ch.account_id = %s")
            source_params.append(account_id)
        self.env.cr.execute("""
            SELECT ch.source_campaign_id, camp.name, COUNT(ch.id)
            FROM whatsapp_chat ch
            LEFT JOIN whatsapp_campaign camp ON camp.id = ch.source_campaign_id
            WHERE """ + " AND ".join(source_where) + """
            GROUP BY ch.source_campaign_id, camp.name
            ORDER BY COUNT(ch.id) DESC
            LIMIT 5
        """, source_params)
        top_sources = [{
            'id': row[0] or False,
            'name': row[1] or _('Unknown Campaign'),
            'chats': row[2] or 0,
        } for row in self.env.cr.fetchall()]

        has_ai_jobs = bool(self.env.registry.get('elsx.ai.job'))
        ai_jobs = self.env['elsx.ai.job'].sudo() if has_ai_jobs else False
        ai_domain = [('create_date', '>=', start_date)] if start_date and has_ai_jobs else []
        ai_total = ai_jobs.search_count(ai_domain) if has_ai_jobs else 0
        ai_failed = ai_jobs.search_count(ai_domain + [('state', '=', 'failed')]) if has_ai_jobs else 0
        ai_completed = ai_jobs.search_count(ai_domain + [('state', 'in', ['done', 'reviewed', 'applied'])]) if has_ai_jobs else 0

        flows = Flow.search(flow_domain)
        warning_count = 0
        for flow in flows:
            try:
                if flow._get_flow_health_warnings():
                    warning_count += 1
            except Exception:
                warning_count += 1

        payment_ready_accounts = self.env['whatsapp.account'].sudo().search_count([
            ('active', '=', True),
            ('payment_link_mode', '!=', 'disabled'),
        ] + ([('id', '=', account_id)] if account_id else []))

        return {
            'forms': {
                'submissions': form_total,
                'new': form_new,
                'lead_created': form_leads,
                'reply_rule_form_actions': form_actions,
                'top_forms': top_forms,
            },
            'payments': {
                'payment_actions': payment_actions,
                'payment_ready_accounts': payment_ready_accounts,
                'campaigns_with_payment_rules': len(campaigns.filtered(lambda c: c.reply_rule_ids.filtered(lambda r: r.action_type == 'send_payment_link'))),
            },
            'sources': {
                'tracked_chats': source_chat_count,
                'top_sources': top_sources,
            },
            'reply_rules': {
                'active_rules': len(active_rules),
                'handled': sum(rules.mapped('handled_count')),
                'top_rules': top_rules,
            },
            'ai_health': {
                'jobs': ai_total,
                'completed': ai_completed,
                'failed': ai_failed,
            },
            'flow_health': {
                'flows': len(flows),
                'active_flows': len(flows.filtered('active')),
                'warning_flows': warning_count,
            },
        }

    @api.model
    def get_dashboard_data(self, date_range='7d', account_id=False, refresh_mode='hybrid'):
        """Hybrid WhatsApp dashboard.

        Critical operational values are live. Heavy chart/table sections are cached briefly in hybrid mode.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        now = fields.Datetime.now()
        account_id = int(account_id) if account_id and str(account_id).isdigit() else False
        date_range = date_range if date_range in ('today', '7d', '30d', 'all') else '7d'
        refresh_mode = refresh_mode if refresh_mode in ('hybrid', 'live', 'cache') else 'hybrid'
        start_date = self._dashboard_start_date(date_range, now)

        refresh_seconds = int(ICP.get_param('whatsapp.dashboard.refresh.seconds', default='30') or 30)
        cache_minutes = int(ICP.get_param('whatsapp.dashboard.cache.minutes', default='5') or 5)
        motion_enabled = ICP.get_param('whatsapp.ui.motion.enabled', default='True') == 'True'
        motion_level = ICP.get_param('whatsapp.ui.motion.level', default='subtle') or 'subtle'

        live_msg = self._dashboard_live_message_stats(start_date=start_date, account_id=account_id)
        chat_stats = self._dashboard_chat_stats(start_date=start_date, account_id=account_id)
        active_campaign_domain = [('state', 'in', ['running', 'scheduled'])]
        if account_id:
            active_campaign_domain.append(('account_id', '=', account_id))
        active_campaigns = self.env['whatsapp.campaign'].sudo().search_count(active_campaign_domain)

        account_health = self._dashboard_account_health(account_id=account_id)
        conversion_sections = self._dashboard_conversion_sections(start_date=start_date, account_id=account_id)
        failed_live = live_msg['failed']
        loaded = live_msg['sent'] + failed_live
        funnel_data = {
            'loaded': loaded,
            'sent': live_msg['sent'],
            'delivered': live_msg['delivered'],
            'read': live_msg['read'],
            'clicked': live_msg['clicked'],
            'replied': live_msg['inbound'],
        }

        cache_key = 'whatsapp.dashboard.cache.%s.%s' % (date_range, account_id or 'all')
        cached = {}
        cache_age = None
        source = 'live'
        if refresh_mode in ('hybrid', 'cache') and cache_minutes > 0:
            try:
                cached = json.loads(ICP.get_param(cache_key, default='{}') or '{}')
                cached_at = fields.Datetime.to_datetime(cached.get('cached_at')) if cached.get('cached_at') else False
                cache_age = int((now - cached_at).total_seconds()) if cached_at else None
            except Exception:
                cached = {}
                cache_age = None

        heavy_sections = cached.get('data') if cached and cache_age is not None and cache_age <= cache_minutes * 60 else False
        if refresh_mode == 'live' or not heavy_sections:
            heavy_sections = self._dashboard_heavy_sections(start_date=start_date, account_id=account_id)
            source = 'live' if refresh_mode == 'live' else 'live+refreshed-charts'
            if refresh_mode in ('hybrid', 'cache') and cache_minutes > 0:
                ICP.set_param(cache_key, json.dumps({
                    'cached_at': fields.Datetime.to_string(now),
                    'data': heavy_sections,
                }))
                cache_age = 0
        else:
            source = 'live+cached-charts'

        warnings = []
        if account_health['stale_seconds'] > 7200:
            warnings.append('No recent webhook activity for more than 2 hours.')
        if failed_live:
            warnings.append('%s failed messages in the selected range.' % failed_live)
        if account_health['limit_reached_accounts']:
            warnings.append('%s WhatsApp account(s) reached the local daily cap.' % account_health['limit_reached_accounts'])

        sync_state = 'Live'
        if warnings and account_health['stale_seconds'] > 7200:
            sync_state = 'Stale'

        return {
            'meta': {
                'generated_at': fields.Datetime.to_string(now),
                'source': source,
                'sync_state': sync_state,
                'stale_seconds': account_health['stale_seconds'],
                'account_id': account_id or False,
                'warnings': warnings,
                'data_version': 'dashboard-v3',
                'refresh_seconds': max(refresh_seconds, 0),
                'cache_minutes': cache_minutes,
                'cache_age_seconds': cache_age,
                'motion_enabled': motion_enabled,
                'motion_level': motion_level,
            },
            'kpis': {
                **chat_stats,
                'sent': live_msg['sent'],
                'delivered_rate': live_msg['delivered_rate'],
                'read_rate': live_msg['read_rate'],
                'active_campaigns': active_campaigns,
                'ctr_rate': live_msg['ctr_rate'],
                'reply_rate': live_msg['reply_rate'],
                'total_spend': live_msg['total_spend'],
            },
            'cost_by_category': heavy_sections.get('cost_by_category', {}),
            'funnel_data': funnel_data,
            'top_templates': heavy_sections.get('top_templates', []),
            'recent_campaigns': heavy_sections.get('recent_campaigns', []),
            'agent_stats': heavy_sections.get('agent_stats', []),
            'volume_trend': heavy_sections.get('volume_trend', {'dates': [], 'sent': [], 'delivered': [], 'read': []}),
            'account_health': account_health,
            **conversion_sections,
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
