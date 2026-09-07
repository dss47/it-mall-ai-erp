/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { CrmKanbanModel, CrmKanbanDynamicGroupList } from "@crm/views/crm_kanban/crm_kanban_model";
import { RelationalModel } from "@web/model/relational_model/relational_model";

if (!CrmKanbanModel.services.includes("action")) {
    CrmKanbanModel.services = [...CrmKanbanModel.services, "action"];
}

patch(CrmKanbanModel.prototype, {
    setup(params, services) {
        super.setup(...arguments);
        if (services && services.action) {
            this.action = services.action;
        }
    }
});

patch(CrmKanbanDynamicGroupList.prototype, {
    async moveRecord(dataRecordId, dataGroupId, refId, targetGroupId) {
        await super.moveRecord(...arguments);
        const sourceGroup = this.groups.find((g) => g.id === dataGroupId);
        const targetGroup = this.groups.find((g) => g.id === targetGroupId);
        if (
            dataGroupId !== targetGroupId &&
            sourceGroup &&
            targetGroup &&
            sourceGroup.groupByField &&
            sourceGroup.groupByField.name === "stage_id"
        ) {
            const targetName = (targetGroup.displayName || "").toLowerCase();
            if (targetName.includes("perdu") || targetName.includes("lost")) {
                const record = targetGroup.list.records.find((r) => r.id === dataRecordId);
                const leadId = record ? record.resId : null;
                if (leadId && this.model && this.model.action) {
                    this.model.action.doAction({
                        name: "Motif de perte",
                        type: "ir.actions.act_window",
                        view_mode: "form",
                        res_model: "crm.lead.lost",
                        views: [[false, "form"]],
                        target: "new",
                        context: {
                            active_ids: [leadId],
                            active_id: leadId,
                            default_lead_ids: [leadId],
                        },
                    }, {
                        onClose: async () => {
                            if (targetGroup.list && targetGroup.list.load) {
                                await targetGroup.list.load();
                            }
                        }
                    });
                }
            }
        }
    }
});
