/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onPatched, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class WhatsAppDashboard extends Component {
    static template = "elsx_whatsapp_marketing.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        
        this.state = useState({
            loading: true,
            dateRange: '7d', // Default to 7 days
            data: {
                kpis: {},
                cost_by_category: { marketing: 0, utility: 0, authentication: 0, service: 0 },
                funnel_data: { loaded: 0, sent: 0, delivered: 0, read: 0, clicked: 0, replied: 0 },
                top_templates: [],
                recent_campaigns: [],
                agent_stats: [],
                volume_trend: { dates: [], sent: [], delivered: [], read: [] }
            }
        });

        this.canvasRef = useRef("volumeChartCanvas");
        this.categoryChartRef = useRef("categoryChartCanvas");
        this.funnelChartRef = useRef("funnelChartCanvas");

        this.chartInstance = null;
        this.categoryChartInstance = null;
        this.funnelChartInstance = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            if (!this.state.loading) this.renderCharts();
        });

        onPatched(() => {
            if (!this.state.loading) this.renderCharts();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("whatsapp.analytics", "get_dashboard_data", [this.state.dateRange]);
            this.state.data = data;
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async changeDateRange(range) {
        this.state.dateRange = range;
        await this.loadData();
    }

    async reloadDashboard() {
        await this.loadData();
    }

    openMetaManager() {
        window.open('https://business.facebook.com/wa/manage/message-templates/', '_blank');
    }

    openNewChat() {
        this.actionService.doAction('elsx_whatsapp_marketing.wizard_whatsapp_new_chat_action');
    }

    async renderCharts() {
        // Safe ChartJS loading
        try {
            await loadJS("/web/static/lib/Chart/Chart.js");
        } catch (e) {
            // Path differs or loaded already
        }

        if (!window.Chart) {
            console.warn("[WhatsApp Dashboard] Chart.js not available — charts disabled.");
            return;
        }

        this.renderVolumeTrendChart();
        this.renderCategorySpendChart();
        this.renderSuccessFunnelChart();
    }

    renderVolumeTrendChart() {
        if (!this.canvasRef.el) return;
        if (this.chartInstance) {
            this.chartInstance.destroy();
            this.chartInstance = null;
        }

        try {
            const ctx = this.canvasRef.el.getContext('2d');
            const trendData = this.state.data.volume_trend || {};

            this.chartInstance = new window.Chart(ctx, {
                type: 'line',
                data: {
                    labels: trendData.dates || [],
                    datasets: [
                        {
                            label: 'Sent',
                            data: trendData.sent || [],
                            borderColor: '#0284c7',
                            backgroundColor: 'rgba(2, 132, 199, 0.08)',
                            borderWidth: 2.5,
                            tension: 0.35,
                            fill: true,
                        },
                        {
                            label: 'Delivered',
                            data: trendData.delivered || [],
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.08)',
                            borderWidth: 2.5,
                            tension: 0.35,
                            fill: true,
                        },
                        {
                            label: 'Read',
                            data: trendData.read || [],
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.08)',
                            borderWidth: 2.5,
                            tension: 0.35,
                            fill: true,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { weight: '600' } } } },
                    scales: { y: { beginAtZero: true, grid: { color: '#f1f5f9' } }, x: { grid: { display: false } } },
                },
            });
        } catch (e) {
            console.error('[WhatsApp Dashboard] Volume trend render error:', e);
        }
    }

    renderCategorySpendChart() {
        if (!this.categoryChartRef.el) return;
        if (this.categoryChartInstance) {
            this.categoryChartInstance.destroy();
            this.categoryChartInstance = null;
        }

        try {
            const ctx = this.categoryChartRef.el.getContext('2d');
            const costData = this.state.data.cost_by_category || { marketing: 0, utility: 0, authentication: 0, service: 0 };
            
            // Avoid zero-data empty display by rendering a placeholder segment if everything is 0
            const values = [costData.marketing || 0, costData.utility || 0, costData.authentication || 0, costData.service || 0];
            const hasData = values.some(v => v > 0);

            this.categoryChartInstance = new window.Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: hasData ? ['Marketing', 'Utility', 'Authentication', 'Service'] : ['No Spend Data'],
                    datasets: [{
                        data: hasData ? values : [1],
                        backgroundColor: hasData 
                            ? ['#ec4899', '#f59e0b', '#8b5cf6', '#10b981'] 
                            : ['#e2e8f0'],
                        borderWidth: 1.5,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { weight: '600' } } } },
                    cutout: '68%',
                }
            });
        } catch (e) {
            console.error('[WhatsApp Dashboard] Spend category render error:', e);
        }
    }

    renderSuccessFunnelChart() {
        if (!this.funnelChartRef.el) return;
        if (this.funnelChartInstance) {
            this.funnelChartInstance.destroy();
            this.funnelChartInstance = null;
        }

        try {
            const ctx = this.funnelChartRef.el.getContext('2d');
            const funnel = this.state.data.funnel_data || { loaded: 0, sent: 0, delivered: 0, read: 0, clicked: 0, replied: 0 };

            this.funnelChartInstance = new window.Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['Targeted', 'Sent', 'Delivered', 'Read', 'Clicked', 'Replied'],
                    datasets: [{
                        label: 'Messages',
                        data: [funnel.loaded || 0, funnel.sent || 0, funnel.delivered || 0, funnel.read || 0, funnel.clicked || 0, funnel.replied || 0],
                        backgroundColor: [
                            'rgba(148, 163, 184, 0.85)',
                            'rgba(2, 132, 199, 0.85)',
                            'rgba(245, 158, 11, 0.85)',
                            'rgba(16, 185, 129, 0.85)',
                            'rgba(236, 72, 153, 0.85)',
                            'rgba(139, 92, 246, 0.85)'
                        ],
                        borderRadius: 6,
                        barThickness: 28,
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true, grid: { color: '#f1f5f9' } }, y: { grid: { display: false } } }
                }
            });
        } catch (e) {
            console.error('[WhatsApp Dashboard] Funnel render error:', e);
        }
    }

    openCampaign(campaignId) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.campaign',
            res_id: campaignId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    openTemplateByName(name) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.template',
            domain: [['name', '=', name]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openAgentChat(agentId) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.chat',
            domain: [['assigned_user_id', '=', agentId], ['state', '=', 'open']],
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }
}

registry.category("actions").add("whatsapp_marketing_dashboard", WhatsAppDashboard);

