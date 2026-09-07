/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ControlPanel } from "@web/search/control_panel/control_panel";

patch(ControlPanel.prototype, {
    get canGoBack() {
        return this.breadcrumbs?.length > 1;
    },
    goBack() {
        this.env.config.historyBack?.();
    },
});
