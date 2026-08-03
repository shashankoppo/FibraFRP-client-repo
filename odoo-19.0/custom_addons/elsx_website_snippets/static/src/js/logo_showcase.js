(function () {
    "use strict";

    const SECTION_SELECTOR = ".s_elsx_logo_slider.elsx-logo-showcase";
    const ITEM_SELECTOR = ".elsx-logo-slide:not(.elsx-logo-clone)";

    function isEditing() {
        return document.body.classList.contains("editor_enable") || document.body.classList.contains("o_editable");
    }

    function cloneLogoItems(section) {
        if (isEditing()) {
            return;
        }
        const track = section.querySelector(".elsx-logo-track");
        if (!track) {
            return;
        }
        track.querySelectorAll(".elsx-logo-clone").forEach((clone) => clone.remove());
        const items = Array.from(track.querySelectorAll(ITEM_SELECTOR));
        if (!items.length) {
            return;
        }
        const appendCloneSet = () => {
            items.forEach((item) => {
                const clone = item.cloneNode(true);
                clone.classList.add("elsx-logo-clone");
                clone.setAttribute("aria-hidden", "true");
                clone.setAttribute("tabindex", "-1");
                track.append(clone);
            });
        };
        appendCloneSet();
        if (track.scrollWidth < window.innerWidth * 2.4) {
            appendCloneSet();
        }
    }

    function hydrateLogoShowcases() {
        document.querySelectorAll(SECTION_SELECTOR).forEach(cloneLogoItems);
    }

    let resizeTimer;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(hydrateLogoShowcases, 180);
    });
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", hydrateLogoShowcases);
    } else {
        hydrateLogoShowcases();
    }
})();