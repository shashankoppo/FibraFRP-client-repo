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

Dialog.defaultProps.title = "Application";
ErrorDialog.title = _t("Application Error");
ClientErrorDialog.title = _t("Client Error");
NetworkErrorDialog.title = _t("Network Error");

const rebrandTitle = (title) => String(title || "").replace(/Odoo\s+/g, "").replace(/^Odoo$/g, "Application");

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
