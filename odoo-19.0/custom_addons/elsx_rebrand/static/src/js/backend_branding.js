/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import {
    ClientErrorDialog,
    ErrorDialog,
    NetworkErrorDialog,
    RPCErrorDialog,
    RedirectWarningDialog,
    WarningDialog,
} from "@web/core/errors/error_dialogs";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const BRAND_NAME = "ELSxGlobal";

const rebrandTitle = (title) =>
    String(title || BRAND_NAME)
        .replace(/Odoo\.com/gi, BRAND_NAME)
        .replace(/Odoo\s+Server\s+Error/gi, "Server Error")
        .replace(/Odoo\s+Client\s+Error/gi, "Client Error")
        .replace(/Odoo\s+Network\s+Error/gi, "Network Error")
        .replace(/Odoo\s+Session\s+Expired/gi, "Session Expired")
        .replace(/Odoo\s+Warning/gi, "Warning")
        .replace(/\s*\(Community Edition\)/gi, "")
        .replace(/\bOdoo\b/gi, BRAND_NAME)
        .trim() || BRAND_NAME;

Dialog.defaultProps.title = BRAND_NAME;
ErrorDialog.title = _t("Application Error");
ClientErrorDialog.title = _t("Client Error");
NetworkErrorDialog.title = _t("Network Error");

const originalRpcInferTitle = RPCErrorDialog.prototype.inferTitle;
RPCErrorDialog.prototype.inferTitle = function () {
    originalRpcInferTitle.call(this);
    this.title = rebrandTitle(this.title);
};

const originalWarningInferTitle = WarningDialog.prototype.inferTitle;
WarningDialog.prototype.inferTitle = function () {
    return rebrandTitle(originalWarningInferTitle.call(this));
};

const originalRedirectSetup = RedirectWarningDialog.prototype.setup;
RedirectWarningDialog.prototype.setup = function () {
    originalRedirectSetup.call(this);
    this.title = rebrandTitle(this.title);
};

const sessionExpired = {
    title: _t("Session Expired"),
    message: _t("Your session expired. The current page is about to be refreshed."),
    buttons: [
        {
            text: _t("Ok"),
            click: () => window.location.reload(true),
            close: true,
        },
    ],
};

registry.category("error_notifications").add("odoo.http.SessionExpiredException", sessionExpired, { force: true });
registry.category("error_notifications").add("werkzeug.exceptions.Forbidden", sessionExpired, { force: true });

const removeOdooAccountMenu = () => {
    const userMenuItems = registry.category("user_menuitems");
    if (userMenuItems.contains("odoo_account")) {
        userMenuItems.remove("odoo_account");
    }
};
const userMenuItems = registry.category("user_menuitems");
userMenuItems.addEventListener("UPDATE", () => setTimeout(removeOdooAccountMenu, 0));
removeOdooAccountMenu();
setTimeout(removeOdooAccountMenu, 0);

const scrubDocumentTitle = () => {
    if (typeof document !== "undefined") {
        document.title = rebrandTitle(document.title);
    }
};

const serviceRegistry = registry.category("services");
const originalTitleService = serviceRegistry.get("title", null);
if (originalTitleService) {
    serviceRegistry.add(
        "title",
        {
            ...originalTitleService,
            start() {
                const service = originalTitleService.start(...arguments);
                return {
                    ...service,
                    get current() {
                        return rebrandTitle(service.current);
                    },
                    setCounters(counters) {
                        const result = service.setCounters(counters);
                        scrubDocumentTitle();
                        return result;
                    },
                    setParts(parts) {
                        const result = service.setParts(parts);
                        scrubDocumentTitle();
                        return result;
                    },
                };
            },
        },
        { force: true }
    );
}
