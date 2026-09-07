/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { session } from "@web/session";

const ITEM_ICONS = {
    my_activities: "fa-clock-o",
    settings: "fa-user",
    general_settings: "fa-gear",
    dark_mode: "fa-moon-o",
    logout: "fa-sign-out",
};

const ALLOWED_IDS = ["my_activities", "settings", "general_settings", "dark_mode", "logout"];

if (typeof window !== "undefined" && window.localStorage?.getItem("it_mall_dark_mode") === "dark") {
    if (document.body) {
        document.body.classList.add("o_dark_mode");
    }
    document.documentElement.setAttribute("data-bs-theme", "dark");
}

const NAV = [
    {
        key: "dashboard",
        label: "Tableau de bord",
        icon: "fa-home",
        home: true,
    },
    {
        key: "crm",
        label: "CRM",
        icon: "fa-address-card",
        show: (g) => g.isSales,
        items: [
            { label: "Pipeline", action: "crm.crm_lead_action_pipeline" },
            { label: "Étapes", action: "crm.crm_stage_action" },
            { label: "Motifs de perte", action: "crm.crm_lost_reason_action" },
        ],
    },
    {
        key: "sales",
        label: "Ventes",
        icon: "fa-shopping-cart",
        show: (g) => g.isSales,
        items: [
            { label: "Devis", action: "sale.action_quotations_with_onboarding" },
            { label: "Bons de commande", action: "sale.action_orders" },
            { label: "Articles", action: "product.product_template_action_all" },
        ],
    },
    {
        key: "inventory",
        label: "Livraisons",
        icon: "fa-cubes",
        show: (g) => g.isStock,
        action: "stock.action_picking_tree_outgoing",
    },
    {
        key: "accounting",
        label: "Comptabilité",
        icon: "fa-book",
        show: (g) => g.isAccount,
        items: [
            { label: "Factures", action: "account.action_move_out_invoice" },
            { label: "Paiements", action: "account.action_account_payments" },
        ],
    },
    {
        key: "contacts",
        label: "Contacts",
        icon: "fa-address-book",
        show: (g) => g.isContacts,
        action: "contacts.action_contacts",
    },
    {
        key: "calls",
        label: "Appels",
        icon: "fa-phone",
        items: [
            { label: "Journal des appels", action: "it_mall_branding.action_it_mall_call_log" },
            {
                label: "IT Mall PBX",
                url: "http://" + (typeof window !== "undefined" && window.location.hostname ? window.location.hostname : "localhost") + ":80",
                show: (g) => g.isAdmin
            },
        ],
    },
];

export class Sidebar extends Component {
    static template = "it_mall_branding.Sidebar";

    setup() {
        this.actionService = useService("action");
        const isDark = typeof window !== "undefined" && window.localStorage?.getItem("it_mall_dark_mode") === "dark";
        if (isDark && document.body) {
            document.body.classList.add("o_dark_mode");
            document.documentElement.setAttribute("data-bs-theme", "dark");
        }
        this.state = useState({ collapsed: false, expanded: {}, isDark });
        this.user = user;
        this.session = session;
        this.menuItems = [];
        this.groups = useState({ isSales: false, isStock: false, isAccount: false, isPurchase: false, isAdmin: false, isContacts: false });
        onWillStart(async () => {
            try {
                const [isSales, isStock, isAccount, isPurchase, isAdmin, isContacts] = await Promise.all([
                    user.hasGroup("sales_team.group_sale_salesman_all_leads"),
                    user.hasGroup("stock.group_stock_user"),
                    user.hasGroup("account.group_account_invoice"),
                    user.hasGroup("purchase.group_purchase_user"),
                    user.hasGroup("base.group_system"),
                    user.hasGroup("base.group_partner_manager"),
                ]);
                Object.assign(this.groups, { isSales, isStock, isAccount, isPurchase, isAdmin, isContacts });
            } catch {
                Object.assign(this.groups, { isSales: false, isStock: false, isAccount: false, isPurchase: false, isAdmin: false, isContacts: false });
            }
            try {
                const allItems = registry.category("user_menuitems").getAll();
                const resolved = await Promise.all(allItems.map(async (fn) => {
                    const item = fn(this.env);
                    const show = item.show ? await item.show(this.env) : true;
                    return show ? item : null;
                }));
                this.menuItems = resolved
                    .filter(Boolean)
                    .filter((item) => ALLOWED_IDS.includes(item.id))
                    .sort((a, b) => (a.sequence ?? Infinity) - (b.sequence ?? Infinity));
            } catch {
                this.menuItems = [];
            }
        });
    }

    toggle() {
        this.state.collapsed = !this.state.collapsed;
    }

    toggleNav(key) {
        this.state.expanded[key] = !this.state.expanded[key];
    }

    isExpanded(key) {
        return !!this.state.expanded[key];
    }

    getNavItems() {
        return NAV.filter((nav) => !nav.show || nav.show(this.groups));
    }

    getSubItems(nav) {
        if (!nav.items) return [];
        return nav.items.filter((item) => !item.show || item.show(this.groups));
    }

    navigateHome() {
        this.actionService.doAction({
            tag: "it_mall_welcome_action",
            type: "ir.actions.client",
            target: "current",
        });
    }

    navTo(action) {
        if (action) {
            this.actionService.doAction(action);
        }
    }

    onSubItemClick(item) {
        if (item.url) {
            window.open(item.url, "_blank");
        } else if (item.action) {
            this.navTo(item.action);
        }
    }

    toggleDarkMode() {
        this.state.isDark = !this.state.isDark;
        if (this.state.isDark) {
            document.body.classList.add("o_dark_mode");
            document.documentElement.setAttribute("data-bs-theme", "dark");
            localStorage.setItem("it_mall_dark_mode", "dark");
        } else {
            document.body.classList.remove("o_dark_mode");
            document.documentElement.removeAttribute("data-bs-theme");
            localStorage.setItem("it_mall_dark_mode", "light");
        }
    }

    onMenuItemClick(item) {
        if (item.id === "dark_mode") {
            this.toggleDarkMode();
            return;
        }
        if (item.callback) {
            item.callback();
        }
    }

    getItemIcon(item) {
        if (item.id === "dark_mode") {
            return this.state.isDark ? "fa-sun-o" : "fa-moon-o";
        }
        return ITEM_ICONS[item.id] || "fa-circle-o";
    }

    getItemTitle(item) {
        if (item.id === "dark_mode") {
            return this.state.isDark ? "Light Mode" : "Dark Mode";
        }
        return item.description;
    }
}

registry.category("main_components").add("it_mall_branding.sidebar", {
    Component: Sidebar,
});
