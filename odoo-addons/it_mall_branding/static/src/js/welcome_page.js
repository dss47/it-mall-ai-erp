/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

export class ITMallWelcome extends Component {
    static template = "it_mall_branding.WelcomePage";

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.title = useService("title");
        this.title.setParts({ action: "Dashboard" });
        this.userName = user.name || "User";
        this.state = useState({ stats: {}, loading: true });
        this.groups = useState({ isSales: false, isStock: false, isAccount: false });

        onWillStart(async () => {
            try {
                const [isSales, isStock, isAccount] = await Promise.all([
                    user.hasGroup("sales_team.group_sale_salesman_all_leads"),
                    user.hasGroup("stock.group_stock_user"),
                    user.hasGroup("account.group_account_invoice"),
                ]);
                Object.assign(this.groups, { isSales, isStock, isAccount });
            } catch {
                Object.assign(this.groups, { isSales: false, isStock: false, isAccount: false });
            }
            await this.loadStats();
        });
    }

    async loadStats() {
        const stats = {};
        const promises = [];

        try {
            if (this.groups.isSales) {
                promises.push(
                    this.orm.searchCount("sale.order", [["state", "=", "draft"]]).then(v => stats.draftQuotations = v),
                    this.orm.searchCount("sale.order", [["state", "=", "sale"]]).then(v => stats.confirmedOrders = v),
                    this.orm.searchCount("crm.lead", [["type", "=", "opportunity"]]).then(v => stats.opportunities = v),
                );
            }

            if (this.groups.isStock) {
                promises.push(
                    this.orm.searchCount("stock.picking", [
                        ["picking_type_code", "=", "incoming"],
                        ["state", "not in", ["done", "cancel"]]
                    ]).then(v => stats.incomingPickings = v),
                    this.orm.searchCount("stock.picking", [
                        ["picking_type_code", "=", "outgoing"],
                        ["state", "not in", ["done", "cancel"]]
                    ]).then(v => stats.outgoingPickings = v),
                    this.orm.searchCount("product.product", [
                        ["is_storable", "=", true],
                        ["qty_available", "<", 10]
                    ]).then(v => stats.lowStock = v),
                );
            }

            if (this.groups.isAccount) {
                promises.push(
                    this.orm.searchCount("account.move", [
                        ["move_type", "=", "out_invoice"],
                        ["state", "=", "draft"]
                    ]).then(v => stats.draftInvoices = v),
                    this.orm.searchCount("account.move", [
                        ["move_type", "=", "out_invoice"],
                        ["state", "=", "posted"]
                    ]).then(v => stats.postedInvoices = v),
                );
            }

            // Nombre d'appels à traiter (filtré par les droits de l'utilisateur)
            promises.push(
                this.orm.searchCount("it_mall.call.log", [
                    ["state", "!=", "done"]
                ]).then(v => stats.pendingCalls = v),
                this.orm.searchCount("it_mall.call.log", [
                    ["state", "=", "urgent"]
                ]).then(v => stats.urgentCalls = v)
            );

            await Promise.all(promises);
        } catch (e) {
            // silently fail
        }

        this.state.stats = stats;
        this.state.loading = false;
    }

    openAction(actionId, context = {}) {
        this.actionService.doAction(actionId, {
            clearBreadcrumbs: true,
            additionalContext: context
        });
    }
}

registry.category("actions").add("it_mall_welcome_action", ITMallWelcome);
