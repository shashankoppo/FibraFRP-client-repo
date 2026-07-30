// Keep the native Website Editor entry inside the Odoo backend action route.
// Some domains/browsers can block Odoo's public /@/ bridge URL before Odoo can
// redirect it, so the top-left Editor button uses the same final action URL
// directly.
document.addEventListener("DOMContentLoaded", () => {
    if (window.frameElement) {
        return;
    }
    const editorButton = document.querySelector(".o_frontend_to_backend_edit_btn");
    if (!editorButton) {
        return;
    }

    const currentUrl = new URL(window.location.href);
    const path = `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}` || "/";
    const previewUrl = new URL("/odoo/action-website.website_preview", window.location.origin);
    previewUrl.searchParams.set("path", path);

    editorButton.href = previewUrl.pathname + previewUrl.search;
});