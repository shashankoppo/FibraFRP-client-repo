/** @odoo-module **/

const BRAND_NAME = "ELSxGlobal";
const BRAND_URL = "https://elsxglobal.com";
const REPLACEMENTS = [
    [/Powered by\s*Odoo/gi, `Powered by ${BRAND_NAME}`],
    [/My\s+Odoo\.com\s+Account/gi, `My ${BRAND_NAME} Account`],
    [/Odoo\.com/gi, BRAND_NAME],
    [/Odoo Enterprise/gi, `${BRAND_NAME} Enterprise`],
    [/Odoo Community/gi, `${BRAND_NAME} Community`],
    [/Odoo Server Error/gi, `${BRAND_NAME} Server Error`],
    [/Odoo Client Error/gi, `${BRAND_NAME} Client Error`],
    [/Odoo Network Error/gi, `${BRAND_NAME} Network Error`],
    [/Odoo Session Expired/gi, `${BRAND_NAME} Session Expired`],
    [/Odoo Warning/gi, `${BRAND_NAME} Warning`],
    [/\bOdoo\b/g, BRAND_NAME],
];

function branded(value) {
    if (!value || typeof value !== "string") {
        return value;
    }
    return REPLACEMENTS.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value);
}

function rebrandTextNodes(root) {
    if (!root || root.nodeType !== Node.ELEMENT_NODE) {
        return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
        const next = walker.nextNode();
        const value = branded(node.nodeValue);
        if (value !== node.nodeValue) {
            node.nodeValue = value;
        }
        node = next;
    }
}

function rebrandAttributes(root) {
    if (!root || root.nodeType !== Node.ELEMENT_NODE) {
        return;
    }
    const attrs = ["title", "aria-label", "alt", "placeholder", "content"];
    const selector = "[title], [aria-label], [alt], [placeholder], meta[content], a[href*='odoo.com']";
    const nodes = [root, ...root.querySelectorAll(selector)];
    for (const node of nodes) {
        for (const attr of attrs) {
            if (node.hasAttribute?.(attr)) {
                const current = node.getAttribute(attr);
                const value = branded(current);
                if (value !== current) {
                    node.setAttribute(attr, value);
                }
            }
        }
        if (node.tagName === "A" && /odoo\.com/i.test(node.getAttribute("href") || "")) {
            node.setAttribute("href", BRAND_URL);
        }
    }
}

function rebrandDocument(root = document.body) {
    document.title = branded(document.title || BRAND_NAME) || BRAND_NAME;
    rebrandTextNodes(root);
    rebrandAttributes(root);
}

function startRebrand() {
    if (!document.body) {
        return;
    }
    rebrandDocument();
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === "childList") {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        rebrandDocument(node);
                    } else if (node.nodeType === Node.TEXT_NODE) {
                        node.nodeValue = branded(node.nodeValue);
                    }
                }
            } else if (mutation.type === "characterData") {
                mutation.target.nodeValue = branded(mutation.target.nodeValue);
            } else if (mutation.type === "attributes") {
                rebrandAttributes(mutation.target);
            }
        }
        document.title = branded(document.title || BRAND_NAME) || BRAND_NAME;
    });
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ["title", "aria-label", "alt", "placeholder", "content", "href"],
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startRebrand, { once: true });
} else {
    startRebrand();
}
