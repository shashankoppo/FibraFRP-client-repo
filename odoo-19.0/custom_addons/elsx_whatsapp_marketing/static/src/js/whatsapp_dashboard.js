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
            data: {
                kpis: {},
                top_templates: [],
                recent_campaigns: [],
                volume_trend: { dates: [], sent: [], delivered: [], read: [] }
            }
        });

        this.canvasRef = useRef("volumeChartCanvas");
        this.chartInstance = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            if (!this.state.loading) this.renderChart();
        });

        onPatched(() => {
            if (!this.state.loading) this.renderChart();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("whatsapp.analytics", "get_dashboard_data", [[]]);
            this.state.data = data;
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
        } finally {
            this.state.loading = false;
        }
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

    async renderChart() {
        if (!this.canvasRef.el) return;
        if (this.chartInstance) {
            this.chartInstance.destroy();
            this.chartInstance = null;
        }

        try {
            await loadJS("/web/static/lib/Chart/Chart.js");
        } catch (e) {
            // Chart.js may already be loaded or path differs — non-fatal
        }

        if (!window.Chart) {
            console.warn("[WhatsApp Dashboard] Chart.js not available — chart disabled.");
            return;
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
                            borderColor: '#0d6efd',
                            backgroundColor: 'rgba(13, 110, 253, 0.1)',
                            tension: 0.4,
                            fill: true,
                        },
                        {
                            label: 'Delivered',
                            data: trendData.delivered || [],
                            borderColor: '#198754',
                            backgroundColor: 'rgba(25, 135, 84, 0.1)',
                            tension: 0.4,
                            fill: true,
                        },
                        {
                            label: 'Read',
                            data: trendData.read || [],
                            borderColor: '#0dcaf0',
                            backgroundColor: 'rgba(13, 202, 240, 0.1)',
                            tension: 0.4,
                            fill: true,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom' } },
                    scales: { y: { beginAtZero: true } },
                },
            });
        } catch (e) {
            console.error('[WhatsApp Dashboard] Chart render error:', e);
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
}

registry.category("actions").add("whatsapp_marketing_dashboard", WhatsAppDashboard);
