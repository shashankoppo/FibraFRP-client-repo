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

const ABOUT_BLOCK_SELECTORS = [
    '[name="about_setting_container"]',
    '[data-name="about_setting_container"]',
    '[data-key="about_setting_container"]',
];

function isSettingsView() {
    const path = window.location.pathname || "";
    return path.includes("/settings") || Boolean(document.querySelector(".o_base_settings, .app_settings_block"));
}

const SETTINGS_ROOT_SELECTORS = [
    ".o_action_manager",
    ".o_content",
    ".o_base_settings",
    ".o_form_view",
    ".o_form_sheet",
    ".o_renderer",
    ".app_settings_block",
];

function isProtectedSettingsRoot(element) {
    return SETTINGS_ROOT_SELECTORS.some((selector) => element?.matches?.(selector));
}

function hideElement(element) {
    if (!element || element.classList?.contains("o_elsx_hidden_about") || isProtectedSettingsRoot(element)) {
        return;
    }
    element.classList?.add("o_elsx_hidden_about");
    element.setAttribute("hidden", "hidden");
    element.style.display = "none";
}

function hideOnlySmallAboutBlock(element) {
    if (!element || isProtectedSettingsRoot(element)) {
        return;
    }
    const text = (element.textContent || "").replace(/\s+/g, " ").trim();
    if (!/(Community Edition|Copyright|Licensed|GNU|LGPL)/i.test(text)) {
        return;
    }
    const nestedSettingCount = element.querySelectorAll?.(".app_settings_block, .o_setting_box, .o_setting_container").length || 0;
    if (nestedSettingCount > 1) {
        return;
    }
    hideElement(element);
}

function hideSettingsAboutBlock() {
    if (!document.body || !isSettingsView()) {
        return;
    }

    for (const selector of ABOUT_BLOCK_SELECTORS) {
        document.querySelectorAll(selector).forEach(hideOnlySmallAboutBlock);
    }

    document.querySelectorAll(".o_setting_box").forEach((block) => {
        const text = (block.textContent || "").replace(/\s+/g, " ").trim();
        if (/\bAbout\b/.test(text) && /(Community Edition|Copyright|Licensed)/i.test(text)) {
            hideElement(block);
        }
    });

    document.querySelectorAll("h1, h2, h3, h4, h5, .o_horizontal_separator, .o_setting_title").forEach((heading) => {
        const headingText = (heading.textContent || "").replace(/\s+/g, " ").trim();
        if (headingText !== "About") {
            return;
        }
        const block = heading.closest(".o_setting_box, [name='about_setting_container'], [data-name='about_setting_container'], [data-key='about_setting_container']");
        const blockText = (block?.textContent || "").replace(/\s+/g, " ").trim();
        if (/(Community Edition|Copyright|Licensed)/i.test(blockText)) {
            hideOnlySmallAboutBlock(block);
        }
    });
}

function startSettingsBrandingObserver() {
    hideSettingsAboutBlock();
    const observer = new MutationObserver(() => {
        browser.clearTimeout(startSettingsBrandingObserver.timer);
        startSettingsBrandingObserver.timer = browser.setTimeout(hideSettingsAboutBlock, 100);
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startSettingsBrandingObserver, { once: true });
} else {
    startSettingsBrandingObserver();
}
