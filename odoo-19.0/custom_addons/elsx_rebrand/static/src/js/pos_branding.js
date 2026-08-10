/** @odoo-module **/

import { registry } from "@web/core/registry";
import { odooExceptionTitleMap, ErrorDialog } from "@web/core/errors/error_dialogs";
import { ConnectionLostError, RPCError } from "@web/core/network/rpc";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

const rebrandText = (value) =>
    String(value || "")
        .replace(/Odoo\s+Server\s+Error/gi, "Server Error")
        .replace(/Odoo\s+Point\s+of\s+Sale/gi, "Point of Sale")
        .replace(/\bOdoo\b/gi, "ELSxGlobal");

function handleRPCError(error, dialog) {
    const { data } = error;
    if (odooExceptionTitleMap.has(error.exceptionName)) {
        const title = rebrandText(odooExceptionTitleMap.get(error.exceptionName).toString());
        dialog.add(AlertDialog, { title, body: data.message });
    } else if (odoo.debug === "assets") {
        dialog.add(ErrorDialog, {
            traceback: data.message + "\n" + data.debug + "\n",
        });
    } else {
        dialog.add(AlertDialog, {
            title: _t("Server Error"),
            body: data.message,
        });
    }
}

function rpcErrorHandler(env, error, originalError) {
    if (originalError instanceof RPCError) {
        handleRPCError(originalError, env.services.dialog);
        return true;
    }
}

function offlineErrorHandler(env, error, originalError) {
    if (originalError instanceof ConnectionLostError) {
        if (!env.services.pos.data.network.warningTriggered) {
            env.services.dialog.add(AlertDialog, {
                title: _t("Connection Lost"),
                body: _t(
                    "Until the connection is reestablished, Point of Sale will operate with limited functionality."
                ),
                confirmLabel: _t("Continue with limited functionality"),
            });
            env.services.pos.data.network.warningTriggered = true;
        }
        return true;
    }
}

function defaultErrorHandler(env, error) {
    if (error instanceof Error) {
        env.services.dialog.add(ErrorDialog, {
            traceback: error.traceback,
        });
    } else {
        env.services.dialog.add(AlertDialog, {
            title: _t("Unknown Error"),
            body: _t("Unable to show information about this error."),
            showReloadButton: true,
        });
    }
    return true;
}

registry.category("error_handlers").add("pos-rpcErrorHandler", rpcErrorHandler, { force: true });
registry.category("error_handlers").add("pos-offlineErrorHandler", offlineErrorHandler, { force: true });
registry.category("error_handlers").add("pos-defaultErrorHandler", defaultErrorHandler, { force: true, sequence: 99 });
