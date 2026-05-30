/** @odoo-module **/

import { loadJS } from "@web/core/assets";

const GSAP_PATH = "/elsx_whatsapp_marketing/static/lib/gsap/gsap.js";

let gsapPromise = null;

function prefersReducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

function canAnimate(options = {}) {
    if (options.enabled === false || options.level === "off") return false;
    if (prefersReducedMotion()) return false;
    if (document.hidden) return false;
    return true;
}

export async function loadElsxMotion(options = {}) {
    if (!canAnimate(options)) return null;
    if (window.gsap) return window.gsap;
    if (!gsapPromise) {
        gsapPromise = loadJS(GSAP_PATH)
            .then(() => window.gsap || null)
            .catch((error) => {
                console.warn("[ELSX Motion] GSAP could not be loaded; animations disabled.", error);
                return null;
            });
    }
    return gsapPromise;
}

export async function animateDashboardIn(root, options = {}) {
    const gsap = await loadElsxMotion(options);
    if (!gsap || !root) return;
    const cards = root.querySelectorAll(".elsx-kpi-card, .elsx-wa-sync-card, .elsx-wa-dashboard .card");
    gsap.fromTo(cards, {
        autoAlpha: 0,
        y: 10,
    }, {
        autoAlpha: 1,
        y: 0,
        duration: options.level === "standard" ? 0.28 : 0.18,
        ease: "power2.out",
        stagger: options.level === "standard" ? 0.025 : 0.012,
        overwrite: "auto",
    });
}

export async function pulseChangedValues(root, options = {}) {
    const gsap = await loadElsxMotion(options);
    if (!gsap || !root) return;
    const values = root.querySelectorAll("[data-wa-kpi-value]");
    gsap.fromTo(values, {
        scale: 0.985,
    }, {
        scale: 1,
        duration: 0.18,
        ease: "power2.out",
        overwrite: "auto",
    });
}

export async function animateSyncBadge(root, options = {}) {
    const gsap = await loadElsxMotion(options);
    const badge = root?.querySelector(".elsx-wa-sync-badge");
    if (!gsap || !badge) return;
    gsap.fromTo(badge, { autoAlpha: 0.65 }, {
        autoAlpha: 1,
        duration: 0.22,
        ease: "power1.out",
        overwrite: "auto",
    });
}

export async function animateFlowBuilderIn(root, options = {}) {
    const gsap = await loadElsxMotion(options);
    if (!gsap || !root) return;
    const targets = root.querySelectorAll(".wa-fb-palette-item, .wa-fb-node, .wa-fb-drawer");
    gsap.fromTo(targets, {
        autoAlpha: 0,
        y: 8,
    }, {
        autoAlpha: 1,
        y: 0,
        duration: options.level === "standard" ? 0.22 : 0.15,
        ease: "power2.out",
        stagger: options.level === "standard" ? 0.018 : 0.008,
        overwrite: "auto",
    });
}

export async function animateFlowNodeFocus(root, options = {}) {
    const gsap = await loadElsxMotion(options);
    const target = root?.querySelector(".wa-fb-node.selected, .wa-fb-drawer.open");
    if (!gsap || !target) return;
    gsap.fromTo(target, { scale: 0.992 }, {
        scale: 1,
        duration: 0.16,
        ease: "power2.out",
        overwrite: "auto",
    });
}

export async function animateInboxRefresh(root, options = {}) {
    const gsap = await loadElsxMotion(options);
    if (!gsap || !root) return;
    const freshItems = Array.from(root.querySelectorAll(".o_whatsapp_sidebar_item:not([data-wa-motion-seen]), .wa-message-row:not([data-wa-motion-seen])")).slice(-12);
    freshItems.forEach((item) => {
        item.dataset.waMotionSeen = "1";
    });
    if (!freshItems.length) return;
    gsap.fromTo(freshItems, {
        autoAlpha: 0,
        y: 6,
    }, {
        autoAlpha: 1,
        y: 0,
        duration: options.level === "standard" ? 0.2 : 0.13,
        ease: "power2.out",
        stagger: 0.01,
        overwrite: "auto",
    });
}
