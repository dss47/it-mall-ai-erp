/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import {
    ErrorDialog,
    ClientErrorDialog,
    NetworkErrorDialog,
    RPCErrorDialog,
    WarningDialog,
} from "@web/core/errors/error_dialogs";

const ODOO_PATTERNS = [/^Odoo /, /\bOdoo\b/];

function cleanTitle(title) {
    if (!title) {
        return title;
    }
    let cleaned = title.replace(/\bOdoo\b/g, "IT Mall");
    cleaned = cleaned.replace(/^IT Mall /, "");
    return cleaned;
}

function debrandStaticTitle(Cls) {
    const originalTitle = Cls.title;
    Object.defineProperty(Cls, "title", {
        configurable: true,
        get() {
            return cleanTitle(originalTitle);
        },
    });
}

debrandStaticTitle(ErrorDialog);
debrandStaticTitle(ClientErrorDialog);
debrandStaticTitle(NetworkErrorDialog);
patch(WarningDialog.prototype, {
    inferTitle() {
        const title = super.inferTitle(...arguments);
        return cleanTitle(title);
    },
});
patch(RPCErrorDialog.prototype, {
    inferTitle() {
        const title = super.inferTitle(...arguments);
        return cleanTitle(title);
    },
});

import { registry } from "@web/core/registry";

const customTitleService = {
    start() {
        const titleCounters = {};
        const titleParts = {};

        function getParts() {
            return Object.assign({}, titleParts);
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
                    titleParts[key] = typeof val === "string" ? val.replace(/\bOdoo\b/g, "IT Mall") : val;
                }
            }
            updateTitle();
        }

        function updateTitle() {
            const counter = Object.values(titleCounters).reduce((acc, count) => acc + count, 0);
            let name = Object.values(titleParts).join(" - ") || "IT Mall";
            name = name.replace(/\bOdoo\b/g, "IT Mall");
            if (!counter) {
                document.title = name;
            } else {
                document.title = `(${counter}) ${name}`;
            }
        }

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

registry.category("services").add("title", customTitleService, { force: true });

// Clean any residual Odoo text references in settings panes
function scrubOdooText() {
    try {
        const settingPanes = document.querySelectorAll(".o_setting_right_pane, .text-muted, label, .o_form_label, .btn-link");
        for (const el of settingPanes) {
            if (el.childNodes.length > 0) {
                for (const node of el.childNodes) {
                    if (node.nodeType === Node.TEXT_NODE && node.textContent && node.textContent.includes("Odoo")) {
                        node.textContent = node.textContent
                            .replace(/accéder à Odoo avec/g, "accéder à la plateforme avec")
                            .replace(/périodique Odoo/g, "périodique d'activité")
                            .replace(/\bOdoo\b/g, "IT Mall");
                    }
                }
            }
        }
    } catch (e) {}
}

if (typeof window !== "undefined") {
    setInterval(scrubOdooText, 1000);
}

