/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";

registry.category("user_menuitems").add("my_activities", function (env) {
    return {
        type: "item",
        id: "my_activities",
        description: _t("Mes activités"),
        callback: async function () {
            await env.services.action.doAction("mail.mail_activity_action_my", {
                clearBreadcrumbs: true,
            });
        },
        sequence: 45,
    };
});

registry.category("user_menuitems").add("profile", function (env) {
    return {
        type: "item",
        id: "settings",
        description: _t("Mon compte"),
        callback: async function () {
            const actionDescription = await env.services.orm.call("res.users", "action_get");
            actionDescription.res_id = user.userId;
            env.services.action.doAction(actionDescription);
        },
        sequence: 50,
    };
}, { force: true });

registry.category("user_menuitems").add("general_settings", function (env) {
    return {
        type: "item",
        id: "general_settings",
        description: _t("Paramètres"),
        callback: async function () {
            await env.services.action.doAction("base_setup.action_general_configuration");
        },
        sequence: 55,
        show: () => user.hasGroup("base.group_system"),
    };
});

registry.category("user_menuitems").add("dark_mode", function () {
    return {
        type: "item",
        id: "dark_mode",
        description: _t("Mode sombre / clair"),
        callback: function () {},
        sequence: 60,
    };
});

