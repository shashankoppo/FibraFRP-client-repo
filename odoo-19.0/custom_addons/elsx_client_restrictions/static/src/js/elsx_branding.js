/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

const userMenuItems = registry.category("user_menuitems");
const services = registry.category("services");

const elsxTitleService = {
    start() {
        const titleCounters = {};
        const titleParts = {};

        function getParts() {
            return Object.assign({}, titleParts);
        }

        function updateTitle() {
            const counter = Object.values(titleCounters).reduce((acc, count) => acc + count, 0);
            const name = Object.values(titleParts).join(" - ") || "ELSxGlobal";
            document.title = counter ? `(${counter}) ${name}` : name;
        }

        function setCounters(counters) {
            for (const key in counters) {
                const val = counters[key];
                if (!val) {
                    delete titleCounters[key];
                } else {
                    titleCounters[key] = val;
                }
            }
            updateTitle();
        }

        function setParts(parts) {
            for (const key in parts) {
                const val = parts[key];
                if (!val) {
                    delete titleParts[key];
                } else {
                    titleParts[key] = val;
                }
            }
            updateTitle();
        }

        updateTitle();

        return {
            get current() {
                return document.title;
            },
            getParts,
            setCounters,
            setParts,
        };
    },
};

if (services.contains("title")) {
    services.remove("title");
}
services.add("title", elsxTitleService, { force: true });

function removeOdooAccountItem() {
    if (userMenuItems.contains("odoo_account")) {
        userMenuItems.remove("odoo_account");
    }
}

userMenuItems.add(
    "support",
    () => ({
        type: "item",
        id: "support",
        description: "ELSxGlobal Support",
        href: "https://elsxglobal.com",
        callback: () => {
            browser.open("https://elsxglobal.com", "_blank");
        },
        sequence: 20,
    }),
    { force: true, sequence: 20 }
);

removeOdooAccountItem();
browser.setTimeout(removeOdooAccountItem, 0);
browser.setTimeout(removeOdooAccountItem, 500);
