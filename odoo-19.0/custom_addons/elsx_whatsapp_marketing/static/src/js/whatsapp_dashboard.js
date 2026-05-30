/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onPatched, onWillUnmount, useRef, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { animateDashboardIn, animateSyncBadge, pulseChangedValues } from "@elsx_whatsapp_marketing/js/elsx_ui_motion";

export class WhatsAppDashboard extends Component {
    static template = xml`
<div class="o_action elsx-wa-dashboard-wrapper" t-ref="dashboardRoot">
            <div class="elsx-wa-dashboard container-fluid py-4 bg-light">

                <!-- Loading State -->
                <div t-if="state.loading" class="text-center py-5">
                    <div class="spinner-border text-success" role="status" style="width: 3rem; height: 3rem;">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <h5 class="mt-3 text-muted">Loading Real-Time Analytics...</h5>
                </div>

                <div t-if="!state.loading">
                    <!-- Top Navigation Bar & Date Selector -->
                    <div class="d-flex flex-wrap justify-content-between align-items-center mb-4 gap-3">
                        <div>
                            <h2 class="mb-0 fw-bold text-dark d-flex align-items-center gap-2">
                                <i class="fa fa-pie-chart text-success"></i>
                                <span>WhatsApp Analytics Hub</span>
                            </h2>
                            <p class="text-muted mb-0">Monitor broadcast delivery, support performance, and marketing ROI</p>
                        </div>

                        <div class="d-flex align-items-center flex-wrap gap-2">
                            <!-- Dynamic Date Range Pickers -->
                            <div class="btn-group shadow-sm bg-white rounded-3 p-1">
                                <button type="button"
                                        t-attf-class="btn btn-sm px-3 rounded-2 #{state.dateRange === 'today' ? 'btn-success text-white fw-semibold' : 'btn-light text-secondary border-0'}"
                                        t-on-click="() => this.changeDateRange('today')">Today</button>
                                <button type="button"
                                        t-attf-class="btn btn-sm px-3 rounded-2 #{state.dateRange === '7d' ? 'btn-success text-white fw-semibold' : 'btn-light text-secondary border-0'}"
                                        t-on-click="() => this.changeDateRange('7d')">Last 7d</button>
                                <button type="button"
                                        t-attf-class="btn btn-sm px-3 rounded-2 #{state.dateRange === '30d' ? 'btn-success text-white fw-semibold' : 'btn-light text-secondary border-0'}"
                                        t-on-click="() => this.changeDateRange('30d')">Last 30d</button>
                                <button type="button"
                                        t-attf-class="btn btn-sm px-3 rounded-2 #{state.dateRange === 'all' ? 'btn-success text-white fw-semibold' : 'btn-light text-secondary border-0'}"
                                        t-on-click="() => this.changeDateRange('all')">All Time</button>
                            </div>

                            <select class="form-select form-select-sm shadow-sm border-0 rounded-3 bg-white elsx-wa-account-selector"
                                    t-att-value="state.accountId || ''"
                                    t-on-change="(ev) => this.changeAccount(ev.target.value)">
                                <option value="">All Accounts</option>
                                <option t-foreach="state.data.account_health.accounts" t-as="account" t-key="account.id"
                                        t-att-value="account.id">
                                    <t t-esc="account.name"/>
                                </option>
                            </select>

                            <!-- Header Actions -->
                            <div class="d-flex gap-2">
                                <button class="btn btn-whatsapp-meta d-flex align-items-center gap-2 shadow-sm rounded-3 py-2 px-3 bg-white" t-on-click="openMetaManager">
                                    <i class="fa fa-facebook-square fs-5 text-primary"></i>
                                    <span class="small fw-bold">Meta WABA Manager</span>
                                </button>
                                <button class="btn btn-success d-flex align-items-center gap-2 shadow-sm rounded-3 py-2 px-3" t-on-click="openNewChat">
                                    <i class="fa fa-plus"></i>
                                    <span class="small fw-bold">New Chat</span>
                                </button>
                                <button class="btn btn-outline-secondary d-flex align-items-center gap-2 shadow-sm rounded-3 py-2 px-3 bg-white"
                                        t-att-disabled="state.refreshing || state.loading"
                                        t-on-click="reloadDashboard"
                                        title="Force a live dashboard refresh">
                                    <i t-attf-class="fa #{state.refreshing ? 'fa-circle-o-notch fa-spin' : 'fa-refresh'}"></i>
                                    <span class="small fw-bold d-none d-md-inline">Refresh</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Hybrid Sync State -->
                    <div class="elsx-wa-sync-card card border-0 shadow-sm rounded-4 mb-4">
                        <div class="card-body py-3 d-flex flex-wrap align-items-center justify-content-between gap-3">
                            <div class="d-flex flex-wrap align-items-center gap-2">
                                <span t-attf-class="elsx-wa-sync-badge badge rounded-pill px-3 py-2 #{this.syncBadgeClass()}">
                                    <t t-esc="state.data.meta.sync_state"/>
                                </span>
                                <span class="text-muted small">
                                    Updated <span class="fw-semibold text-dark"><t t-esc="state.data.meta.generated_at || 'not loaded yet'"/></span>
                                </span>
                                <span class="text-muted small">
                                    Source <span class="fw-semibold text-dark"><t t-esc="state.data.meta.source || 'hybrid'"/></span>
                                </span>
                                <span class="text-muted small" t-if="state.data.meta.cache_age_seconds !== false &amp;&amp; state.data.meta.cache_age_seconds !== null">
                                    Cache age <span class="fw-semibold text-dark"><t t-esc="state.data.meta.cache_age_seconds"/>s</span>
                                </span>
                                <span class="text-muted small" t-if="state.lastRefreshNote">
                                    <i class="fa fa-info-circle me-1"></i><t t-esc="state.lastRefreshNote"/>
                                </span>
                            </div>
                            <div class="d-flex align-items-center gap-2">
                                <span class="text-muted small" t-if="state.refreshing">
                                    <i class="fa fa-circle-o-notch fa-spin me-1"></i>Refreshing
                                </span>
                                <button class="btn btn-sm btn-outline-success rounded-3"
                                        t-att-disabled="state.refreshing || state.loading"
                                        t-on-click="reloadDashboard">
                                    <i t-attf-class="fa me-1 #{state.refreshing ? 'fa-circle-o-notch fa-spin' : 'fa-refresh'}"></i>
                                    <t t-if="state.refreshing">Refreshing...</t>
                                    <t t-if="!state.refreshing">Refresh Now</t>
                                </button>
                            </div>
                        </div>
                        <div class="px-3 pb-3" t-if="state.data.meta.warnings.length">
                            <div class="alert alert-warning mb-0 py-2 px-3 small rounded-3">
                                <div t-foreach="state.data.meta.warnings" t-as="warning" t-key="warning">
                                    <i class="fa fa-exclamation-triangle me-1"></i><t t-esc="warning"/>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Operations Control Center -->
                    <div class="row g-3 mb-4">
                        <div class="col-xl-8 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-control-center">
                                <div class="card-header bg-white border-0 pt-4 pb-0 d-flex flex-wrap justify-content-between align-items-start gap-2">
                                    <div>
                                        <h5 class="fw-bold text-dark mb-0">Operations Control Center</h5>
                                        <span class="text-muted small">Open the right workspace directly from the dashboard</span>
                                    </div>
                                    <span class="badge bg-success bg-opacity-10 text-success rounded-pill px-3 py-2 fw-bold">
                                        <i class="fa fa-bolt me-1"></i>Live workspace
                                    </span>
                                </div>
                                <div class="card-body">
                                    <div class="row g-3">
                                        <div class="col-lg-4 col-md-6 col-12">
                                            <button type="button" class="elsx-wa-command-card w-100 text-start" t-on-click="openTeamInbox">
                                                <span class="elsx-wa-command-icon bg-success bg-opacity-10 text-success"><i class="fa fa-comments"></i></span>
                                                <span class="d-block fw-bold text-dark">Team Inbox</span>
                                                <span class="d-block text-muted small"><t t-esc="state.data.kpis.open_chats"/> active chats, <t t-esc="state.data.kpis.total_chats"/> total</span>
                                            </button>
                                        </div>
                                        <div class="col-lg-4 col-md-6 col-12">
                                            <button type="button" class="elsx-wa-command-card w-100 text-start" t-on-click="openCampaigns">
                                                <span class="elsx-wa-command-icon bg-primary bg-opacity-10 text-primary"><i class="fa fa-bullhorn"></i></span>
                                                <span class="d-block fw-bold text-dark">Campaigns</span>
                                                <span class="d-block text-muted small"><t t-esc="state.data.kpis.active_campaigns"/> active, <t t-esc="state.data.recent_campaigns.length"/> recent shown</span>
                                            </button>
                                        </div>
                                        <div class="col-lg-4 col-md-6 col-12">
                                            <button type="button" class="elsx-wa-command-card w-100 text-start" t-on-click="openTemplates">
                                                <span class="elsx-wa-command-icon bg-warning bg-opacity-10 text-warning"><i class="fa fa-file-text-o"></i></span>
                                                <span class="d-block fw-bold text-dark">Templates</span>
                                                <span class="d-block text-muted small"><t t-esc="state.data.top_templates.length"/> active in selected range</span>
                                            </button>
                                        </div>
                                        <div class="col-lg-4 col-md-6 col-12">
                                            <button type="button" class="elsx-wa-command-card w-100 text-start" t-on-click="openForms">
                                                <span class="elsx-wa-command-icon bg-info bg-opacity-10 text-info"><i class="fa fa-list-alt"></i></span>
                                                <span class="d-block fw-bold text-dark">Forms &amp; Leads</span>
                                                <span class="d-block text-muted small"><t t-esc="state.data.forms.new"/> new, <t t-esc="state.data.forms.lead_created"/> leads created</span>
                                            </button>
                                        </div>
                                        <div class="col-lg-4 col-md-6 col-12">
                                            <button type="button" class="elsx-wa-command-card w-100 text-start" t-on-click="openFlows">
                                                <span class="elsx-wa-command-icon bg-secondary bg-opacity-10 text-secondary"><i class="fa fa-sitemap"></i></span>
                                                <span class="d-block fw-bold text-dark">Flow Builder</span>
                                                <span class="d-block text-muted small"><t t-esc="state.data.flow_health.active_flows"/> active, <t t-esc="state.data.flow_health.warning_flows"/> warnings</span>
                                            </button>
                                        </div>
                                        <div class="col-lg-4 col-md-6 col-12">
                                            <button type="button" class="elsx-wa-command-card w-100 text-start" t-on-click="openAccounts">
                                                <span class="elsx-wa-command-icon bg-danger bg-opacity-10 text-danger"><i class="fa fa-whatsapp"></i></span>
                                                <span class="d-block fw-bold text-dark">Accounts &amp; Health</span>
                                                <span class="d-block text-muted small"><t t-esc="state.data.account_health.active_accounts"/> active, <t t-esc="this.unverifiedAccountCount()"/> need attention</span>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col-xl-4 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-attention-card">
                                <div class="card-header bg-white border-0 pt-4 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">What Needs Attention</h5>
                                    <span class="text-muted small">Operational checklist for this selected range</span>
                                </div>
                                <div class="card-body">
                                    <div t-foreach="this.attentionItems()" t-as="item" t-key="item.id" class="d-flex align-items-start gap-3 border-bottom py-2">
                                        <span t-attf-class="elsx-wa-attention-dot #{this.attentionDotClass(item.type)}"></span>
                                        <div class="min-w-0 flex-grow-1">
                                            <div class="fw-bold text-dark"><t t-esc="item.title"/></div>
                                            <div class="text-muted small"><t t-esc="item.detail"/></div>
                                            <button t-if="item.action" type="button" class="btn btn-link btn-sm p-0 mt-1 fw-semibold" t-on-click="() => this.openAttention(item.action)">
                                                <t t-esc="item.label || 'Open'"/>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Live Operational Snapshot -->
                    <div class="row g-3 mb-4">
                        <div class="col-lg-2 col-md-4 col-6">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-mini-metric">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small">Delivered</span>
                                    <h4 class="mb-0 fw-black text-success" data-wa-kpi-value="1"><t t-esc="state.data.funnel_data.delivered"/></h4>
                                    <span class="text-muted small">messages</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-2 col-md-4 col-6">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-mini-metric">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small">Read</span>
                                    <h4 class="mb-0 fw-black text-primary" data-wa-kpi-value="1"><t t-esc="state.data.funnel_data.read"/></h4>
                                    <span class="text-muted small">opened</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-2 col-md-4 col-6">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-mini-metric">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small">Replies</span>
                                    <h4 class="mb-0 fw-black text-info" data-wa-kpi-value="1"><t t-esc="state.data.funnel_data.replied"/></h4>
                                    <span class="text-muted small">inbound</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-2 col-md-4 col-6">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-mini-metric">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small">Clicks</span>
                                    <h4 class="mb-0 fw-black text-danger" data-wa-kpi-value="1"><t t-esc="state.data.funnel_data.clicked"/></h4>
                                    <span class="text-muted small">button/list</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-2 col-md-4 col-6">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-mini-metric">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small">Failed</span>
                                    <h4 class="mb-0 fw-black text-warning" data-wa-kpi-value="1"><t t-esc="Math.max((state.data.funnel_data.loaded || 0) - (state.data.funnel_data.sent || 0), 0)"/></h4>
                                    <span class="text-muted small">needs review</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-2 col-md-4 col-6">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-wa-mini-metric">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small">Total Chats</span>
                                    <h4 class="mb-0 fw-black text-dark" data-wa-kpi-value="1"><t t-esc="state.data.kpis.total_chats"/></h4>
                                    <span class="text-muted small">all states</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Meta Account Health & Limits -->
                    <div class="row g-3 mb-4">
                        <div class="col-lg-3 col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-success">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Meta Daily Usage</span>
                                    <h3 class="mb-1 fw-black text-dark" data-wa-kpi-value="1">
                                        <t t-esc="state.data.account_health.daily_sent"/> / <t t-esc="state.data.account_health.daily_limit || 'Unlimited'"/>
                                    </h3>
                                    <div class="progress" style="height: 6px;">
                                        <div class="progress-bar bg-success rounded-pill" role="progressbar" t-attf-style="width: #{Math.min(state.data.account_health.usage_percent || 0, 100)}%;"></div>
                                    </div>
                                    <span class="text-muted small"><t t-esc="state.data.account_health.usage_percent"/>% used today</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-3 col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-info">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Remaining Capacity</span>
                                    <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.account_health.daily_remaining"/></h3>
                                    <span class="text-muted small">available before local safety cap</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-3 col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-primary">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Active WABA Accounts</span>
                                    <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.account_health.active_accounts"/></h3>
                                    <span class="text-muted small">connected sending profiles</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-3 col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-danger">
                                <div class="card-body py-3">
                                    <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Limit Reached</span>
                                    <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.account_health.limit_reached_accounts"/></h3>
                                    <span class="text-muted small">accounts currently blocked by cap</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-12" t-if="state.data.account_health.accounts.length">
                            <div class="card border-0 shadow-sm rounded-4">
                                <div class="card-header bg-white border-0 pt-3 pb-1">
                                    <h5 class="fw-bold text-dark mb-0">Meta Account Health</h5>
                                    <span class="text-muted small">Quality, messaging limit, and webhook freshness per WhatsApp number</span>
                                </div>
                                <div class="card-body py-2">
                                    <div class="table-responsive">
                                        <table class="table table-borderless align-middle mb-0">
                                            <thead class="text-muted small text-uppercase bg-light">
                                                <tr>
                                                    <th class="ps-3 py-2 rounded-start">Account</th>
                                                    <th class="py-2">Quality</th>
                                                    <th class="py-2">Meta Limit</th>
                                                    <th class="py-2">Local Usage</th>
                                                    <th class="py-2">Last Status Webhook</th>
                                                    <th class="py-2 rounded-end">Webhook</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr t-foreach="state.data.account_health.accounts" t-as="account" t-key="account.id" class="border-bottom">
                                                    <td class="ps-3">
                                                        <div class="fw-bold text-dark"><t t-esc="account.name"/></div>
                                                        <div class="text-muted small"><t t-esc="account.phone_number"/></div>
                                                    </td>
                                                    <td>
                                                        <span t-attf-class="badge rounded-pill px-2.5 py-1 #{account.quality_rating === 'GREEN' ? 'bg-success' : account.quality_rating === 'YELLOW' ? 'bg-warning text-dark' : account.quality_rating === 'RED' ? 'bg-danger' : 'bg-secondary'}">
                                                            <t t-esc="account.quality_rating"/>
                                                        </span>
                                                    </td>
                                                    <td class="fw-semibold text-dark"><t t-esc="account.messaging_limit"/></td>
                                                    <td>
                                                        <div class="small fw-semibold"><t t-esc="account.daily_sent"/> / <t t-esc="account.daily_limit || 'Unlimited'"/></div>
                                                        <div class="progress" style="height: 5px; max-width: 140px;">
                                                            <div class="progress-bar bg-success rounded-pill" t-attf-style="width: #{Math.min(account.usage_percent || 0, 100)}%;"></div>
                                                        </div>
                                                    </td>
                                                    <td class="text-muted small"><t t-esc="account.last_status_webhook_at || 'No status received yet'"/></td>
                                                    <td>
                                                        <span t-attf-class="badge rounded-pill px-2.5 py-1 #{account.webhook_status === 'verified' ? 'bg-success' : account.webhook_status === 'failed' ? 'bg-danger' : 'bg-secondary'}">
                                                            <t t-esc="account.webhook_status"/>
                                                        </span>
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 10 Advanced KPI Row -->
                    <div class="row g-3 mb-4">
                        <!-- Outbound Sent -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-primary">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Sent Messages</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.sent"/></h3>
                                        </div>
                                        <div class="bg-primary bg-opacity-10 p-2.5 rounded-circle text-primary">
                                            <i class="fa fa-paper-plane fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Delivered Rate -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-warning">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Delivered Rate</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.delivered_rate"/>%</h3>
                                        </div>
                                        <div class="bg-warning bg-opacity-10 p-2.5 rounded-circle text-warning">
                                            <i class="fa fa-check-circle fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Read Rate -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-success">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Read Rate</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.read_rate"/>%</h3>
                                        </div>
                                        <div class="bg-success bg-opacity-10 p-2.5 rounded-circle text-success">
                                            <i class="fa fa-eye fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Click Rate (CTR) -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-danger">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Click Rate (CTR)</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.ctr_rate"/>%</h3>
                                        </div>
                                        <div class="bg-danger bg-opacity-10 p-2.5 rounded-circle text-danger">
                                            <i class="fa fa-mouse-pointer fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Reply Rate -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-info">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Reply Rate</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.reply_rate"/>%</h3>
                                        </div>
                                        <div class="bg-info bg-opacity-10 p-2.5 rounded-circle text-info">
                                            <i class="fa fa-reply fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Second KPI Row -->
                    <div class="row g-3 mb-4">
                        <!-- Total Est Spend -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card bg-gradient border-0" style="background: linear-gradient(135deg, #10b981, #059669); color: white;">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-white text-opacity-75 fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Estimated Cost</span>
                                            <h3 class="mb-0 fw-black text-white mt-1" data-wa-kpi-value="1">$<t t-esc="state.data.kpis.total_spend"/></h3>
                                        </div>
                                        <div class="bg-white bg-opacity-20 p-2.5 rounded-circle text-white">
                                            <i class="fa fa-dollar fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- FRT (First Response Time) -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-secondary">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">First Response (FRT)</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.frt_minutes"/> min</h3>
                                        </div>
                                        <div class="bg-secondary bg-opacity-10 p-2.5 rounded-circle text-secondary">
                                            <i class="fa fa-hourglass-half fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- ART (Resolution Time) -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-dark">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Avg Resolution (ART)</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.art_hours"/> hrs</h3>
                                        </div>
                                        <div class="bg-dark bg-opacity-10 p-2.5 rounded-circle text-dark">
                                            <i class="fa fa-check fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Open Chats -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-primary">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Active Chats</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.open_chats"/></h3>
                                        </div>
                                        <div class="bg-primary bg-opacity-10 p-2.5 rounded-circle text-primary">
                                            <i class="fa fa-comments fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Resolved Today -->
                        <div class="col-md col-sm-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 elsx-kpi-card border-start border-4 border-success">
                                <div class="card-body py-3">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <span class="text-uppercase text-muted fw-bold small" style="font-size: 0.68rem; letter-spacing: 0.05em;">Resolved Today</span>
                                            <h3 class="mb-0 fw-black text-dark mt-1" data-wa-kpi-value="1"><t t-esc="state.data.kpis.resolved_today"/></h3>
                                        </div>
                                        <div class="bg-success bg-opacity-10 p-2.5 rounded-circle text-success">
                                            <i class="fa fa-check-square fs-5"></i>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Conversion Sync Row -->
                    <div class="row g-3 mb-4">
                        <div class="col-lg-4 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-success">
                                <div class="card-header bg-white border-0 pt-3 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">Forms &amp; Leads</h5>
                                    <span class="text-muted small">Public form submissions and lead conversion</span>
                                </div>
                                <div class="card-body">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">Submissions</span>
                                        <strong data-wa-kpi-value="1"><t t-esc="state.data.forms.submissions"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">New / Unreviewed</span>
                                        <strong class="text-warning"><t t-esc="state.data.forms.new"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-3">
                                        <span class="text-muted small">Leads Created</span>
                                        <strong class="text-success"><t t-esc="state.data.forms.lead_created"/></strong>
                                    </div>
                                    <div t-if="state.data.forms.top_forms.length === 0" class="text-muted small">No form submissions in this range</div>
                                    <div t-foreach="state.data.forms.top_forms" t-as="form" t-key="form.id || form.name" class="d-flex justify-content-between border-top py-1 small">
                                        <span class="text-truncate" t-esc="form.name"/>
                                        <strong t-esc="form.submissions"/>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-4 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-info">
                                <div class="card-header bg-white border-0 pt-3 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">Payments &amp; Reply Rules</h5>
                                    <span class="text-muted small">Campaign automations handled after replies</span>
                                </div>
                                <div class="card-body">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">Payment Link Actions</span>
                                        <strong data-wa-kpi-value="1"><t t-esc="state.data.payments.payment_actions"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">Form Link Actions</span>
                                        <strong><t t-esc="state.data.forms.reply_rule_form_actions"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">Active Reply Rules</span>
                                        <strong><t t-esc="state.data.reply_rules.active_rules"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center">
                                        <span class="text-muted small">Payment-Ready Accounts</span>
                                        <strong class="text-success"><t t-esc="state.data.payments.payment_ready_accounts"/></strong>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-4 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100 border-start border-4 border-primary">
                                <div class="card-header bg-white border-0 pt-3 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">Source, AI &amp; Flow Health</h5>
                                    <span class="text-muted small">Tracking links, AI jobs, and automation warnings</span>
                                </div>
                                <div class="card-body">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">Tracked Chats</span>
                                        <strong data-wa-kpi-value="1"><t t-esc="state.data.sources.tracked_chats"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">AI Jobs Failed</span>
                                        <strong t-att-class="state.data.ai_health.failed ? 'text-danger' : 'text-success'"><t t-esc="state.data.ai_health.failed"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <span class="text-muted small">Active Flows</span>
                                        <strong><t t-esc="state.data.flow_health.active_flows"/></strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center">
                                        <span class="text-muted small">Flows With Warnings</span>
                                        <strong t-att-class="state.data.flow_health.warning_flows ? 'text-warning' : 'text-success'"><t t-esc="state.data.flow_health.warning_flows"/></strong>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Automation Detail Row -->
                    <div class="row g-4 mb-4">
                        <div class="col-lg-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0 d-flex justify-content-between align-items-center">
                                    <div>
                                        <h5 class="fw-bold text-dark mb-0">Top Reply Automations</h5>
                                        <span class="text-muted small">Campaign reply rules that handled customer responses</span>
                                    </div>
                                    <span class="badge bg-success bg-opacity-10 text-success rounded-pill px-3 py-1 fw-bold">
                                        <t t-esc="state.data.reply_rules.handled"/> handled
                                    </span>
                                </div>
                                <div class="card-body">
                                    <div t-if="state.data.reply_rules.top_rules.length === 0" class="text-center py-4 text-muted">
                                        No reply automation activity in this range
                                    </div>
                                    <div t-foreach="state.data.reply_rules.top_rules" t-as="rule" t-key="rule.id" class="d-flex justify-content-between align-items-start border-bottom py-2 gap-3">
                                        <div class="min-w-0">
                                            <div class="fw-bold text-dark text-truncate" t-att-title="rule.name"><t t-esc="rule.name"/></div>
                                            <div class="text-muted small text-truncate" t-att-title="rule.campaign"><t t-esc="rule.campaign"/></div>
                                            <span class="badge bg-light text-secondary border mt-1"><t t-esc="rule.action"/></span>
                                        </div>
                                        <strong class="text-success" data-wa-kpi-value="1"><t t-esc="rule.handled"/></strong>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0 d-flex justify-content-between align-items-center">
                                    <div>
                                        <h5 class="fw-bold text-dark mb-0">Tracked Sources</h5>
                                        <span class="text-muted small">Click-to-WhatsApp and campaign-attributed conversations</span>
                                    </div>
                                    <span class="badge bg-primary bg-opacity-10 text-primary rounded-pill px-3 py-1 fw-bold">
                                        <t t-esc="state.data.sources.tracked_chats"/> chats
                                    </span>
                                </div>
                                <div class="card-body">
                                    <div t-if="state.data.sources.top_sources.length === 0" class="text-center py-4 text-muted">
                                        No tracked source conversations in this range
                                    </div>
                                    <div t-foreach="state.data.sources.top_sources" t-as="source" t-key="source.id || source.name" class="d-flex justify-content-between align-items-center border-bottom py-2 gap-3">
                                        <span class="fw-bold text-dark text-truncate" t-att-title="source.name"><t t-esc="source.name"/></span>
                                        <strong class="text-primary" data-wa-kpi-value="1"><t t-esc="source.chats"/></strong>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Main Charts Row: Volume Trend & Spend Doughnut -->
                    <div class="row g-4 mb-4">
                        <!-- 14-Day Line Trend -->
                        <div class="col-lg-8 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0 d-flex justify-content-between align-items-center">
                                    <div>
                                        <h5 class="fw-bold text-dark mb-0">Message Volume &amp; Engagement Trend</h5>
                                        <span class="text-muted small">Daily volume of outbound, delivered, and read messages</span>
                                    </div>
                                </div>
                                <div class="card-body">
                                    <div style="height: 320px; width: 100%;">
                                        <canvas t-ref="volumeChartCanvas"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Spend Category Doughnut -->
                        <div class="col-lg-4 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">Cost by Meta Category</h5>
                                    <span class="text-muted small">Breakdown of billing spend across conversation types</span>
                                </div>
                                <div class="card-body d-flex flex-column align-items-center justify-content-center">
                                    <div style="height: 240px; width: 100%; position: relative;">
                                        <canvas t-ref="categoryChartCanvas"></canvas>
                                    </div>
                                    <!-- Dynamic breakdown list below chart -->
                                    <div class="w-100 mt-3 d-flex justify-content-between px-3 small">
                                        <div class="text-center">
                                            <span class="d-block text-pink" style="color: #ec4899; font-weight: 700;">Marketing</span>
                                            <span class="fw-bold">$<t t-esc="state.data.cost_by_category.marketing"/></span>
                                        </div>
                                        <div class="text-center">
                                            <span class="d-block text-amber" style="color: #f59e0b; font-weight: 700;">Utility</span>
                                            <span class="fw-bold">$<t t-esc="state.data.cost_by_category.utility"/></span>
                                        </div>
                                        <div class="text-center">
                                            <span class="d-block text-purple" style="color: #8b5cf6; font-weight: 700;">Auth</span>
                                            <span class="fw-bold">$<t t-esc="state.data.cost_by_category.authentication"/></span>
                                        </div>
                                        <div class="text-center">
                                            <span class="d-block text-emerald" style="color: #10b981; font-weight: 700;">Service</span>
                                            <span class="fw-bold">$<t t-esc="state.data.cost_by_category.service"/></span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Second Visual Row: Funnel Success and Agent Leaderboard -->
                    <div class="row g-4 mb-4">
                        <!-- Campaign Funnel Chart -->
                        <div class="col-lg-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">Interactive Broadcast Success Funnel</h5>
                                    <span class="text-muted small">Drop-off tracking from targeting to active user replies</span>
                                </div>
                                <div class="card-body">
                                    <div style="height: 300px; width: 100%;">
                                        <canvas t-ref="funnelChartCanvas"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Agent Performance Leaderboard -->
                        <div class="col-lg-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0 d-flex justify-content-between align-items-center">
                                    <div>
                                        <h5 class="fw-bold text-dark mb-0">Support Agent Leaderboard</h5>
                                        <span class="text-muted small">Real-time performance and chat resolution analytics</span>
                                    </div>
                                </div>
                                <div class="card-body">
                                    <div class="table-responsive">
                                        <table class="table table-borderless table-hover align-middle">
                                            <thead class="text-muted small text-uppercase bg-light rounded">
                                                <tr>
                                                    <th class="rounded-start ps-3 py-2">Agent Name</th>
                                                    <th class="py-2 text-center">Active Chats</th>
                                                    <th class="py-2 text-center">Resolved</th>
                                                    <th class="py-2 text-center">Avg ART</th>
                                                    <th class="rounded-end py-2 text-end pe-3">Resolution Rate</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr t-foreach="state.data.agent_stats" t-as="agent" t-key="agent.id" class="border-bottom" style="cursor: pointer;" t-on-click="() => this.openAgentChat(agent.id)">
                                                    <td class="ps-3 fw-bold text-dark">
                                                        <i class="fa fa-user-circle-o text-muted me-2"></i>
                                                        <t t-esc="agent.name"/>
                                                    </td>
                                                    <td class="text-center fw-semibold text-primary"><t t-esc="agent.open_chats"/></td>
                                                    <td class="text-center fw-semibold text-success"><t t-esc="agent.resolved_chats"/></td>
                                                    <td class="text-center text-muted"><t t-esc="agent.avg_resolution_time"/> hrs</td>
                                                    <td class="text-end pe-3">
                                                        <span class="badge rounded-pill bg-success bg-opacity-10 text-success fw-bold px-2.5 py-1">
                                                            <t t-esc="agent.resolution_rate"/>%
                                                        </span>
                                                    </td>
                                                </tr>
                                                <tr t-if="state.data.agent_stats.length === 0">
                                                    <td colspan="5" class="text-center py-4 text-muted">No active agent assignments detected</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Bottom Tables: Top Performing Templates and Recent Campaigns -->
                    <div class="row g-4 mb-4">
                        <!-- Top Templates -->
                        <div class="col-lg-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0">
                                    <h5 class="fw-bold text-dark mb-0">Top Performing WhatsApp Templates</h5>
                                    <span class="text-muted small">Templates with highest customer interaction rates</span>
                                </div>
                                <div class="card-body">
                                    <div class="table-responsive">
                                        <table class="table table-borderless table-hover align-middle">
                                            <thead class="text-muted small text-uppercase bg-light rounded">
                                                <tr>
                                                    <th class="rounded-start ps-3 py-2">Template</th>
                                                    <th class="py-2 text-center">Category</th>
                                                    <th class="py-2 text-center">Usage</th>
                                                    <th class="py-2 text-center">Read Rate</th>
                                                    <th class="rounded-end py-2 text-end pe-3">CTR (Clicks)</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr t-foreach="state.data.top_templates" t-as="tpl" t-key="tpl.name" class="border-bottom" style="cursor: pointer;" t-on-click="() => this.openTemplateByName(tpl.name)">
                                                    <td class="ps-3 fw-bold text-dark text-truncate" style="max-width: 140px;" t-att-title="tpl.name">
                                                        <t t-esc="tpl.name"/>
                                                    </td>
                                                    <td class="text-center">
                                                        <span t-attf-class="badge rounded-pill px-2.5 py-1 #{tpl.category === 'Marketing' ? 'bg-pink-light' : tpl.category === 'Utility' ? 'bg-amber-light' : 'bg-purple-light'}" style="font-size: 0.72rem;">
                                                            <t t-esc="tpl.category"/>
                                                        </span>
                                                    </td>
                                                    <td class="text-center fw-semibold text-dark"><t t-esc="tpl.usage"/></td>
                                                    <td class="text-center">
                                                        <div class="d-flex align-items-center justify-content-center gap-1.5">
                                                            <div class="progress flex-grow-1" style="height: 5px; min-width: 48px; max-width: 60px;">
                                                                <div class="progress-bar bg-success rounded-pill" role="progressbar" t-attf-style="width: #{tpl.read_rate}%;"></div>
                                                            </div>
                                                            <span class="small fw-bold"><t t-esc="tpl.read_rate"/>%</span>
                                                        </div>
                                                    </td>
                                                    <td class="text-end pe-3 fw-bold text-danger">
                                                        <t t-esc="tpl.ctr_rate"/>% <span class="text-muted small font-normal">(<t t-esc="tpl.clicks"/>)</span>
                                                    </td>
                                                </tr>
                                                <tr t-if="state.data.top_templates.length === 0">
                                                    <td colspan="5" class="text-center py-4 text-muted">No template usage logs in selected period</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Recent Campaigns -->
                        <div class="col-lg-6 col-12">
                            <div class="card border-0 shadow-sm rounded-4 h-100">
                                <div class="card-header bg-white border-0 pt-4 pb-0 d-flex justify-content-between align-items-center">
                                    <div>
                                        <h5 class="fw-bold text-dark mb-0">Recent Marketing Broadcast Campaigns</h5>
                                        <span class="text-muted small">Blast logs and click success details</span>
                                    </div>
                                    <span class="badge bg-primary bg-opacity-10 text-primary rounded-pill px-3 py-1.5 fw-bold">
                                        <t t-esc="state.data.kpis.active_campaigns"/> Active Campaigns
                                    </span>
                                </div>
                                <div class="card-body">
                                    <div class="table-responsive">
                                        <table class="table table-borderless table-hover align-middle">
                                            <thead class="text-muted small text-uppercase bg-light rounded">
                                                <tr>
                                                    <th class="rounded-start ps-3 py-2">Campaign Name</th>
                                                    <th class="py-2 text-center">Status</th>
                                                    <th class="py-2 text-center">Sent</th>
                                                    <th class="py-2 text-center">Delivered</th>
                                                    <th class="rounded-end py-2 text-end pe-3">CTR (Clicks)</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr t-foreach="state.data.recent_campaigns" t-as="camp" t-key="camp.id" class="border-bottom" style="cursor: pointer;" t-on-click="() => this.openCampaign(camp.id)">
                                                    <td class="ps-3 fw-bold text-dark"><t t-esc="camp.name"/></td>
                                                    <td class="text-center">
                                                        <span t-attf-class="badge rounded-pill px-2.5 py-1 bg-#{camp.state === 'running' ? 'primary' : camp.state === 'completed' ? 'success' : camp.state === 'scheduled' ? 'warning' : 'secondary'}" style="font-size: 0.72rem;">
                                                            <t t-esc="camp.state"/>
                                                        </span>
                                                    </td>
                                                    <td class="text-center fw-semibold text-dark"><t t-esc="camp.sent"/></td>
                                                    <td class="text-center text-success fw-bold"><t t-esc="camp.delivered_rate"/>%</td>
                                                    <td class="text-end pe-3 fw-bold text-danger">
                                                        <t t-esc="camp.ctr_rate"/>% <span class="text-muted small font-normal">(<t t-esc="camp.clicks"/>)</span>
                                                    </td>
                                                </tr>
                                                <tr t-if="state.data.recent_campaigns.length === 0">
                                                    <td colspan="5" class="text-center py-4 text-muted">No marketing campaigns found</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = useState({
            loading: true,
            refreshing: false,
            dateRange: '7d', // Default to 7 days
            accountId: false,
            refreshMode: "hybrid",
            lastRefreshNote: "",
            data: this._emptyDashboardData(),
        });

        this.dashboardRootRef = useRef("dashboardRoot");
        this.canvasRef = useRef("volumeChartCanvas");
        this.categoryChartRef = useRef("categoryChartCanvas");
        this.funnelChartRef = useRef("funnelChartCanvas");

        this.chartInstance = null;
        this.categoryChartInstance = null;
        this.funnelChartInstance = null;
        this.refreshTimer = null;
        this.lastChartSignature = "";
        this.firstMotionDone = false;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            // Fix for stuck Odoo default tour: forcefully dismiss it when Dashboard loads
            try {
                if (this.env && this.env.services && this.env.services.tour) {
                    const tourService = this.env.services.tour;
                    if (typeof tourService.stopTour === "function") {
                        tourService.stopTour();
                    } else if (typeof tourService.endTour === "function") {
                        tourService.endTour();
                    }
                }
                // Cleanup hanging DOM elements from a stuck tour
                document.body.classList.remove("o_tour_active");
                const activeTourPointers = document.querySelectorAll('.o_tooltip.o_tour_pointer');
                activeTourPointers.forEach(el => el.remove());
            } catch (e) {
                console.warn("[WhatsApp] Failed to suppress tour", e);
            }

            if (!this.state.loading) {
                this.renderCharts();
                this.setupAutoRefresh();
                this.runMotion(true);
            }
        });

        onPatched(() => {
            if (!this.state.loading) {
                this.renderCharts();
            }
        });

        onWillUnmount(() => {
            this.clearAutoRefresh();
            this.destroyCharts();
        });
    }

    _emptyDashboardData() {
        return {
                meta: {
                    generated_at: "",
                    source: "hybrid",
                    sync_state: "Cached",
                    stale_seconds: 0,
                    account_id: false,
                    warnings: [],
                    data_version: "dashboard-v3",
                    refresh_seconds: 30,
                    cache_minutes: 5,
                    cache_age_seconds: null,
                    motion_enabled: true,
                    motion_level: "subtle",
                },
                kpis: {
                    total_chats: 0,
                    open_chats: 0,
                    resolved_today: 0,
                    art_hours: 0,
                    frt_minutes: 0,
                    sent: 0,
                    delivered_rate: 0,
                    read_rate: 0,
                    active_campaigns: 0,
                    ctr_rate: 0,
                    reply_rate: 0,
                    total_spend: 0,
                },
                cost_by_category: { marketing: 0, utility: 0, authentication: 0, service: 0 },
                funnel_data: { loaded: 0, sent: 0, delivered: 0, read: 0, clicked: 0, replied: 0 },
                top_templates: [],
                recent_campaigns: [],
                agent_stats: [],
                volume_trend: { dates: [], sent: [], delivered: [], read: [] },
                account_health: {
                    active_accounts: 0,
                    daily_sent: 0,
                    daily_limit: 0,
                    daily_remaining: 0,
                    usage_percent: 0,
                    limit_reached_accounts: 0,
                    accounts: [],
                },
                forms: { submissions: 0, new: 0, lead_created: 0, reply_rule_form_actions: 0, top_forms: [] },
                payments: { payment_actions: 0, payment_ready_accounts: 0, campaigns_with_payment_rules: 0 },
                sources: { tracked_chats: 0, top_sources: [] },
                reply_rules: { active_rules: 0, handled: 0, top_rules: [] },
                ai_health: { jobs: 0, completed: 0, failed: 0 },
                flow_health: { flows: 0, active_flows: 0, warning_flows: 0 },
        };
    }

    _mergeDashboardData(data) {
        const empty = this._emptyDashboardData();
        const incoming = data || {};
        return {
            ...empty,
            ...incoming,
            meta: {
                ...empty.meta,
                ...(incoming.meta || {}),
                warnings: (incoming.meta || {}).warnings || [],
            },
            kpis: {
                ...empty.kpis,
                ...(incoming.kpis || {}),
            },
            cost_by_category: {
                ...empty.cost_by_category,
                ...(incoming.cost_by_category || {}),
            },
            funnel_data: {
                ...empty.funnel_data,
                ...(incoming.funnel_data || {}),
            },
            volume_trend: {
                ...empty.volume_trend,
                ...(incoming.volume_trend || {}),
            },
            account_health: {
                ...empty.account_health,
                ...(incoming.account_health || {}),
                accounts: (incoming.account_health || {}).accounts || [],
            },
            forms: {
                ...empty.forms,
                ...(incoming.forms || {}),
                top_forms: (incoming.forms || {}).top_forms || [],
            },
            payments: {
                ...empty.payments,
                ...(incoming.payments || {}),
            },
            sources: {
                ...empty.sources,
                ...(incoming.sources || {}),
                top_sources: (incoming.sources || {}).top_sources || [],
            },
            reply_rules: {
                ...empty.reply_rules,
                ...(incoming.reply_rules || {}),
                top_rules: (incoming.reply_rules || {}).top_rules || [],
            },
            ai_health: {
                ...empty.ai_health,
                ...(incoming.ai_health || {}),
            },
            flow_health: {
                ...empty.flow_health,
                ...(incoming.flow_health || {}),
            },
            top_templates: incoming.top_templates || [],
            recent_campaigns: incoming.recent_campaigns || [],
            agent_stats: incoming.agent_stats || [],
        };
    }

    async loadData(options = {}) {
        const silent = Boolean(options.silent);
        const refreshMode = options.refreshMode || this.state.refreshMode || "hybrid";
        if (this.state.refreshing || (this.state.loading && silent)) {
            return;
        }
        const isManualLiveRefresh = refreshMode === "live";
        const startedAt = Date.now();
        if (silent) {
            this.state.refreshing = true;
        } else {
            this.state.loading = true;
        }
        if (isManualLiveRefresh) {
            this.state.lastRefreshNote = "Live refresh requested...";
            this.state.data.meta.sync_state = "Refreshing";
        }
        try {
            const data = await this.orm.call("whatsapp.analytics", "get_dashboard_data", [
                this.state.dateRange,
                this.state.accountId || false,
                refreshMode,
            ]);
            this.state.data = this._mergeDashboardData(data);
            if (isManualLiveRefresh) {
                const elapsed = Math.max((Date.now() - startedAt) / 1000, 0.1).toFixed(1);
                const source = this.state.data.meta.source || "live";
                this.state.lastRefreshNote = `Live refresh completed in ${elapsed}s (${source}).`;
            }
            this.setupAutoRefresh();
            this.runMotion(false);
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
            this.state.data.meta.sync_state = "Error";
            this.state.data.meta.warnings = ["Dashboard refresh failed. Check Odoo logs and analytics access rights."];
            this.state.lastRefreshNote = "Refresh failed. Check Odoo logs and analytics access rights.";
        } finally {
            this.state.loading = false;
            this.state.refreshing = false;
        }
    }

    async changeDateRange(range) {
        this.state.dateRange = range;
        this.lastChartSignature = "";
        await this.loadData();
    }

    async changeAccount(accountId) {
        this.state.accountId = accountId ? parseInt(accountId, 10) : false;
        this.lastChartSignature = "";
        await this.loadData();
    }

    async reloadDashboard() {
        this.lastChartSignature = "";
        await this.loadData({ silent: !this.state.loading, refreshMode: "live" });
    }

    motionOptions() {
        const meta = this.state.data.meta || {};
        return {
            enabled: meta.motion_enabled !== false,
            level: meta.motion_level || "subtle",
        };
    }

    runMotion(firstLoad = false) {
        const root = this.dashboardRootRef.el;
        if (!root) return;
        window.setTimeout(() => {
            if (firstLoad && !this.firstMotionDone) {
                this.firstMotionDone = true;
                animateDashboardIn(root, this.motionOptions());
            } else {
                pulseChangedValues(root, this.motionOptions());
                animateSyncBadge(root, this.motionOptions());
            }
        }, 0);
    }

    setupAutoRefresh() {
        this.clearAutoRefresh();
        const seconds = Number((this.state.data.meta || {}).refresh_seconds || 0);
        if (!seconds || seconds < 5) return;
        this.refreshTimer = window.setInterval(() => {
            if (!document.hidden && !this.state.loading && !this.state.refreshing) {
                this.loadData({ silent: true });
            }
        }, seconds * 1000);
    }

    clearAutoRefresh() {
        if (this.refreshTimer) {
            window.clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    destroyCharts() {
        [this.chartInstance, this.categoryChartInstance, this.funnelChartInstance].forEach((chart) => {
            if (chart && typeof chart.destroy === "function") {
                chart.destroy();
            }
        });
        this.chartInstance = null;
        this.categoryChartInstance = null;
        this.funnelChartInstance = null;
        this.lastChartSignature = "";
    }

    syncBadgeClass() {
        const state = (this.state.data.meta.sync_state || "").toLowerCase();
        if (state === "live") return "bg-success";
        if (state === "refreshing") return "bg-primary";
        if (state === "stale") return "bg-warning text-dark";
        if (state === "error") return "bg-danger";
        return "bg-secondary";
    }

    failedMessageCount() {
        const funnel = this.state.data.funnel_data || {};
        return Math.max((funnel.loaded || 0) - (funnel.sent || 0), 0);
    }

    unverifiedAccountCount() {
        const accounts = (this.state.data.account_health || {}).accounts || [];
        return accounts.filter((account) => account.webhook_status !== "verified").length;
    }

    attentionItems() {
        const data = this.state.data || {};
        const items = [];
        const warnings = (data.meta || {}).warnings || [];
        warnings.slice(0, 2).forEach((warning, index) => {
            items.push({
                id: `warning-${index}`,
                type: "warning",
                title: "Dashboard warning",
                detail: warning,
                action: "diagnostics",
                label: "Open diagnostics",
            });
        });

        const failed = this.failedMessageCount();
        if (failed) {
            items.push({
                id: "failed-messages",
                type: "danger",
                title: `${failed} failed messages`,
                detail: "Review failed sends before the next campaign.",
                action: "messages",
                label: "Open messages",
            });
        }

        const unverified = this.unverifiedAccountCount();
        if (unverified) {
            items.push({
                id: "account-webhook",
                type: "danger",
                title: `${unverified} account needs setup review`,
                detail: "Webhook or account health is not fully verified.",
                action: "accounts",
                label: "Open accounts",
            });
        }

        if ((data.forms || {}).new) {
            items.push({
                id: "forms-new",
                type: "info",
                title: `${data.forms.new} new form submission(s)`,
                detail: "Review submissions and create or update leads.",
                action: "forms",
                label: "Open forms",
            });
        }

        if ((data.flow_health || {}).warning_flows) {
            items.push({
                id: "flow-warnings",
                type: "warning",
                title: `${data.flow_health.warning_flows} flow(s) with warnings`,
                detail: "Check disconnected nodes, missing forms, payment links, or catalog IDs.",
                action: "flows",
                label: "Open flows",
            });
        }

        if ((data.ai_health || {}).failed) {
            items.push({
                id: "ai-failed",
                type: "warning",
                title: `${data.ai_health.failed} failed AI job(s)`,
                detail: "Check provider keys, timeout, model, and response path.",
                action: "ai_jobs",
                label: "Open AI jobs",
            });
        }

        if (!items.length) {
            items.push({
                id: "all-clear",
                type: "success",
                title: "No immediate action required",
                detail: "Core dashboard checks look healthy for the selected range.",
                action: "",
                label: "",
            });
        }

        return items.slice(0, 6);
    }

    attentionDotClass(type) {
        if (type === "danger") return "bg-danger";
        if (type === "warning") return "bg-warning";
        if (type === "info") return "bg-info";
        return "bg-success";
    }

    openAction(xmlId, fallbackAction = null) {
        try {
            return Promise.resolve(this.actionService.doAction(`elsx_whatsapp_marketing.${xmlId}`)).catch((error) => {
                if (fallbackAction) {
                    return this.actionService.doAction(fallbackAction);
                }
                console.warn(`[WhatsApp Dashboard] Failed to open ${xmlId}`, error);
            });
        } catch (error) {
            if (fallbackAction) {
                return this.actionService.doAction(fallbackAction);
            }
            console.warn(`[WhatsApp Dashboard] Failed to open ${xmlId}`, error);
        }
    }

    openMetaManager() {
        window.open('https://business.facebook.com/wa/manage/message-templates/', '_blank');
    }

    openNewChat() {
        this.actionService.doAction('elsx_whatsapp_marketing.action_whatsapp_new_chat_wizard');
    }

    openTeamInbox() {
        this.openAction('action_whatsapp_console_direct', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.chat',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openCampaigns() {
        this.openAction('action_whatsapp_campaign', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.campaign',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openTemplates() {
        this.openAction('action_whatsapp_template', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.template',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openForms() {
        this.openAction('action_whatsapp_form', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.form',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openFlows() {
        this.openAction('whatsapp_bot_flow_action', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.bot.flow',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openAccounts() {
        this.openAction('action_whatsapp_account', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.account',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openDiagnostics() {
        this.openAction('action_whatsapp_diagnostic_snapshot', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.diagnostic.snapshot',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openMessages() {
        this.openAction('action_whatsapp_message', {
            type: 'ir.actions.act_window',
            res_model: 'whatsapp.message',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openAIJobs() {
        this.openAction('action_elsx_ai_job', {
            type: 'ir.actions.act_window',
            res_model: 'elsx.ai.job',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openAttention(action) {
        const handlers = {
            diagnostics: () => this.openDiagnostics(),
            messages: () => this.openMessages(),
            accounts: () => this.openAccounts(),
            forms: () => this.openForms(),
            flows: () => this.openFlows(),
            ai_jobs: () => this.openAIJobs(),
        };
        if (handlers[action]) {
            handlers[action]();
        }
    }

    async renderCharts() {
        const signature = JSON.stringify({
            volume: this.state.data.volume_trend || {},
            cost: this.state.data.cost_by_category || {},
            funnel: this.state.data.funnel_data || {},
        });
        if (signature === this.lastChartSignature) {
            return;
        }

        // Safe ChartJS loading
        try {
            await loadJS("/web/static/lib/Chart/Chart.js");
        } catch (e) {
            // Path differs or loaded already
        }

        if (!window.Chart) {
            console.warn("[WhatsApp Dashboard] Chart.js not available - charts disabled.");
            return;
        }

        this.lastChartSignature = signature;
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

