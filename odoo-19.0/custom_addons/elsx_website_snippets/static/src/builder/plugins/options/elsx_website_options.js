import { BuilderAction } from "@html_builder/core/builder_action";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { END } from "@html_builder/utils/option_sequence";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";

const ELSX_SECTION_SELECTOR = [
    ".s_elsx_logo_cloud",
    ".s_elsx_logo_slider",
    ".s_elsx_testimonials",
    ".s_elsx_case_studies",
    ".s_elsx_stats",
    ".s_elsx_industries",
    ".s_elsx_faq",
    ".s_elsx_cta",
    ".s_elsx_process",
    ".s_elsx_comparison",
    ".s_elsx_brochure",
    ".s_elsx_trust_badges",
].join(", ");
const LOGO_ITEM_SELECTOR = ".elsx-logo-slide, .elsx-logo-card";
const CARD_ITEM_SELECTOR = ".elsx-card, .elsx-project-card, .elsx-tile, .elsx-step, .elsx-badge";
const LOGO_SHAPE_CLASSES = [
    "elsx-logo-pill",
    "elsx-logo-square",
    "elsx-logo-circle",
    "elsx-logo-freeform",
];

function initialsFromLabel(label) {
    const initials = (label || "Logo")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((word) => word[0].toUpperCase())
        .join("")
        .slice(0, 3);
    return initials || "LG";
}

function logoTemplate(document, label = "New Logo", itemClass = "elsx-logo-slide") {
    const item = document.createElement("a");
    item.href = "#";
    item.className = `${itemClass} elsx-logo-pill text-decoration-none`;
    item.dataset.name = "Logo Item";
    item.innerHTML = `<span class="elsx-logo-media"><img class="elsx-logo-img img img-fluid" src="/website/static/src/img/snippets_thumbs/s_picture.svg" alt="${label}" loading="lazy"><span class="elsx-logo-mark">${initialsFromLabel(label)}</span></span><span class="elsx-logo-label">${label}</span>`;
    return item;
}

function ensureLogoStructure(item) {
    const document = item.ownerDocument;
    const label = item.querySelector(".elsx-logo-label")?.textContent?.trim() || item.textContent.trim() || "Logo";
    const itemClass = item.classList.contains("elsx-logo-card") ? "elsx-logo-card" : "elsx-logo-slide";
    let target = item;
    if (item.tagName !== "A") {
        target = logoTemplate(document, label, itemClass);
        target.className = item.className;
        target.classList.add("text-decoration-none");
        target.dataset.name = "Logo Item";
        item.replaceWith(target);
    } else {
        target.dataset.name = "Logo Item";
        target.classList.add("text-decoration-none");
        if (!target.querySelector(".elsx-logo-label")) {
            target.innerHTML = logoTemplate(document, label, itemClass).innerHTML;
        }
    }
    if (!LOGO_SHAPE_CLASSES.some((className) => target.classList.contains(className))) {
        target.classList.add("elsx-logo-pill");
    }
    return target;
}

function getLogoItems(editingElement) {
    const scope = editingElement.matches(LOGO_ITEM_SELECTOR)
        ? editingElement.parentElement
        : editingElement;
    return Array.from(scope?.querySelectorAll(LOGO_ITEM_SELECTOR) || []);
}

function getLogoSection(editingElement) {
    return editingElement.closest?.(".s_elsx_logo_slider, .s_elsx_logo_cloud") || editingElement;
}

function getActiveLogoIndex(editingElement) {
    if (editingElement.matches(LOGO_ITEM_SELECTOR)) {
        return Math.max(0, getLogoItems(editingElement).indexOf(editingElement));
    }
    return parseInt(getLogoSection(editingElement).dataset.elsxActiveLogo || "0");
}

function setActiveLogoIndex(editingElement, index) {
    const items = getLogoItems(editingElement);
    if (!items.length) {
        getLogoSection(editingElement).dataset.elsxActiveLogo = "0";
        return null;
    }
    const safeIndex = Math.max(0, Math.min(index, items.length - 1));
    const target = ensureLogoStructure(items[safeIndex]);
    const section = getLogoSection(target);
    section.dataset.elsxActiveLogo = String(safeIndex);
    getLogoItems(section).forEach((item) => item.classList.remove("elsx-logo-active"));
    target.classList.add("elsx-logo-active");
    return target;
}

function getActiveLogoItem(editingElement) {
    if (editingElement.matches(LOGO_ITEM_SELECTOR)) {
        return ensureLogoStructure(editingElement);
    }
    return setActiveLogoIndex(editingElement, getActiveLogoIndex(editingElement));
}

function getLogoLabel(item) {
    return item?.querySelector(".elsx-logo-label");
}

function getLogoMark(item) {
    return item?.querySelector(".elsx-logo-mark");
}

class ElsxSetLogoLabelAction extends BuilderAction {
    static id = "elsxSetLogoLabel";
    getValue({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        return getLogoLabel(item)?.textContent?.trim() || item?.textContent.trim() || "";
    }
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        const cleanValue = value || "Logo";
        const label = getLogoLabel(item);
        if (label) {
            label.textContent = cleanValue;
        }
        const image = item.querySelector(".elsx-logo-img");
        if (image) {
            image.alt = cleanValue;
        }
    }
}

class ElsxSetLogoInitialsAction extends BuilderAction {
    static id = "elsxSetLogoInitials";
    getValue({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        return getLogoMark(item)?.textContent?.trim() || initialsFromLabel(item?.textContent);
    }
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        const mark = getLogoMark(item);
        if (mark) {
            mark.textContent = (value || initialsFromLabel(getLogoLabel(item)?.textContent)).slice(0, 4).toUpperCase();
        }
    }
}

class ElsxSetLogoHrefAction extends BuilderAction {
    static id = "elsxSetLogoHref";
    getValue({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        return item?.getAttribute("href") || item?.dataset.elsxHref || "#";
    }
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        const href = value || "#";
        item.setAttribute("href", href);
        item.dataset.elsxHref = href;
    }
}

class ElsxSetLogoImageSrcAction extends BuilderAction {
    static id = "elsxSetLogoImageSrc";
    getValue({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        return item?.querySelector(".elsx-logo-img")?.getAttribute("src") || "";
    }
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        const image = item.querySelector(".elsx-logo-img");
        if (image && value) {
            image.setAttribute("src", value);
            item.classList.add("elsx-logo-show-image");
        }
    }
}

class ElsxSetLogoActiveAction extends BuilderAction {
    static id = "elsxSetLogoActive";
    getValue({ editingElement }) {
        return String(getActiveLogoIndex(editingElement));
    }
    isApplied({ editingElement, value }) {
        return String(getActiveLogoIndex(editingElement)) === String(value);
    }
    apply({ editingElement, value }) {
        setActiveLogoIndex(editingElement, parseInt(value || "0"));
    }
}

class ElsxSetLogoImageModeAction extends BuilderAction {
    static id = "elsxSetLogoImageMode";
    getValue({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        return item?.classList.contains("elsx-logo-show-image") ? "image" : "initials";
    }
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        item.classList.toggle("elsx-logo-show-image", value === "image");
    }
}

class ElsxSetLogoShapeAction extends BuilderAction {
    static id = "elsxSetLogoShape";
    getValue({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        return LOGO_SHAPE_CLASSES.find((className) => item?.classList.contains(className)) || "elsx-logo-pill";
    }
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        item.classList.remove(...LOGO_SHAPE_CLASSES);
        item.classList.add(value || "elsx-logo-pill");
    }
}

class ElsxUpgradeLogoItemsAction extends BuilderAction {
    static id = "elsxUpgradeLogoItems";
    apply({ editingElement }) {
        getLogoItems(editingElement).forEach((item) => ensureLogoStructure(item));
        setActiveLogoIndex(editingElement, getActiveLogoIndex(editingElement));
    }
}

class ElsxAddLogoItemAction extends BuilderAction {
    static id = "elsxAddLogoItem";
    apply({ editingElement }) {
        const track = editingElement.querySelector(".elsx-logo-track") || editingElement.querySelector(".elsx-logo-grid");
        if (!track) {
            return;
        }
        const itemClass = track.classList.contains("elsx-logo-grid") ? "elsx-logo-card" : "elsx-logo-slide";
        track.append(logoTemplate(editingElement.ownerDocument, "New Logo", itemClass));
        setActiveLogoIndex(editingElement, track.querySelectorAll(LOGO_ITEM_SELECTOR).length - 1);
    }
}

class ElsxDuplicateLogoItemAction extends BuilderAction {
    static id = "elsxDuplicateLogoItem";
    apply({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        item.after(item.cloneNode(true));
        setActiveLogoIndex(editingElement, getLogoItems(item).indexOf(item) + 1);
    }
}

class ElsxRemoveLogoItemAction extends BuilderAction {
    static id = "elsxRemoveLogoItem";
    apply({ editingElement }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        const parent = item.parentElement;
        if (parent && parent.querySelectorAll(LOGO_ITEM_SELECTOR).length > 1) {
            const index = getLogoItems(item).indexOf(item);
            item.remove();
            setActiveLogoIndex(getLogoSection(parent), index);
        }
    }
}

class ElsxMoveLogoItemAction extends BuilderAction {
    static id = "elsxMoveLogoItem";
    apply({ editingElement, value }) {
        const item = getActiveLogoItem(editingElement);
        if (!item) {
            return;
        }
        const items = getLogoItems(item);
        const currentIndex = items.indexOf(item);
        const nextIndex = currentIndex + parseInt(value || "0");
        if (nextIndex < 0 || nextIndex >= items.length) {
            return;
        }
        if (nextIndex < currentIndex) {
            items[nextIndex].before(item);
        } else {
            items[nextIndex].after(item);
        }
        setActiveLogoIndex(editingElement, nextIndex);
    }
}

class ElsxDuplicateCardItemAction extends BuilderAction {
    static id = "elsxDuplicateCardItem";
    apply({ editingElement }) {
        const column = editingElement.closest("[class*='col-']");
        const clone = (column || editingElement).cloneNode(true);
        (column || editingElement).after(clone);
    }
}

class ElsxRemoveCardItemAction extends BuilderAction {
    static id = "elsxRemoveCardItem";
    apply({ editingElement }) {
        const column = editingElement.closest("[class*='col-']");
        const siblings = column?.parentElement?.querySelectorAll(":scope > [class*='col-']");
        if (column && siblings?.length > 1) {
            column.remove();
        } else {
            editingElement.remove();
        }
    }
}

export class ElsxWebsiteSectionOption extends BaseOptionComponent {
    static template = "elsx_website_snippets.ElsxWebsiteSectionOption";
    static selector = ELSX_SECTION_SELECTOR;
}

export class ElsxLogoSliderOption extends BaseOptionComponent {
    static template = "elsx_website_snippets.ElsxLogoSliderOption";
    static selector = ".s_elsx_logo_slider, .s_elsx_logo_cloud";
}

export class ElsxLogoItemOption extends BaseOptionComponent {
    static template = "elsx_website_snippets.ElsxLogoItemOption";
    static selector = LOGO_ITEM_SELECTOR;
}

export class ElsxCardItemOption extends BaseOptionComponent {
    static template = "elsx_website_snippets.ElsxCardItemOption";
    static selector = CARD_ITEM_SELECTOR;
}

class ElsxWebsiteOptionsPlugin extends Plugin {
    static id = "elsxWebsiteOptions";
    resources = {
        builder_options: [
            withSequence(END, ElsxWebsiteSectionOption),
            withSequence(END, ElsxLogoSliderOption),
            withSequence(END, ElsxLogoItemOption),
            withSequence(END, ElsxCardItemOption),
        ],
        builder_actions: {
            ElsxSetLogoLabelAction,
            ElsxSetLogoInitialsAction,
            ElsxSetLogoHrefAction,
            ElsxSetLogoImageSrcAction,
            ElsxSetLogoActiveAction,
            ElsxSetLogoImageModeAction,
            ElsxSetLogoShapeAction,
            ElsxUpgradeLogoItemsAction,
            ElsxAddLogoItemAction,
            ElsxDuplicateLogoItemAction,
            ElsxRemoveLogoItemAction,
            ElsxMoveLogoItemAction,
            ElsxDuplicateCardItemAction,
            ElsxRemoveCardItemAction,
        },
    };
}

registry.category("website-plugins").add(ElsxWebsiteOptionsPlugin.id, ElsxWebsiteOptionsPlugin);
