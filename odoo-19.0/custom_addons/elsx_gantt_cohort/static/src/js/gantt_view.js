/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, xml, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ElsxGanttView extends Component {
    setup() {
        this.orm = useService("orm");
        this.ganttContainerRef = useRef("gantt_container");
        
        onMounted(() => {
            this.initializeGantt();
        });
    }

    async initializeGantt() {
        // Fetch data based on the current model and domain
        // Example: pulling project.task
        // const records = await this.orm.searchRead(this.props.resModel, this.props.domain, ['name', 'date_start', 'date_deadline', 'progress']);
        
        // Transform Odoo records to Frappe Gantt Format
        const tasks = [
            {
                id: 'Task 1',
                name: 'Redesign UI',
                start: '2026-04-10',
                end: '2026-04-15',
                progress: 20,
            },
            {
                id: 'Task 2',
                name: 'Deploy Parity Modules',
                start: '2026-04-15',
                end: '2026-04-20',
                progress: 0,
                dependencies: 'Task 1'
            }
        ];

        // Initialize the Open-Source Frappe Gantt library
        // Note: frappe-gantt.js must be loaded in the assets bundle
        if (typeof Gantt !== "undefined" && this.ganttContainerRef.el) {
            this.gantt = new Gantt(this.ganttContainerRef.el, tasks, {
                header_height: 50,
                column_width: 30,
                step: 24,
                view_modes: ['Quarter Day', 'Half Day', 'Day', 'Week', 'Month'],
                bar_height: 20,
                bar_corner_radius: 3,
                arrow_curve: 5,
                padding: 18,
                view_mode: 'Day',
                on_date_change: (task, start, end) => {
                    console.log(task.name + ' dates changed');
                    // RPC call back to Odoo server to save new dates
                },
                on_progress_change: (task, progress) => {
                    console.log(task.name + ' progress updated');
                    // RPC call back to Odoo server to save progress
                }
            });
        } else {
            console.warn("ELSX Gantt Error: Frappe Gantt library not found or container missing.");
        }
    }
}

ElsxGanttView.template = xml`
    <div class="elsx_gantt_wrapper overflow-auto p-3 h-100 bg-white">
        <div class="d-flex justify-content-between mb-3">
            <h3>Project Timeline</h3>
            <div class="btn-group">
                <button class="btn btn-outline-secondary btn-sm" t-on-click="() => this.gantt.change_view_mode('Day')">Day</button>
                <button class="btn btn-outline-secondary btn-sm" t-on-click="() => this.gantt.change_view_mode('Week')">Week</button>
                <button class="btn btn-outline-secondary btn-sm" t-on-click="() => this.gantt.change_view_mode('Month')">Month</button>
            </div>
        </div>
        <div t-ref="gantt_container"></div>
    </div>
`;

// Register as a View Type in Odoo 19
registry.category("views").add("elsx_gantt", ElsxGanttView);
