# -*- coding: utf-8 -*-
from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_set_lost(self, **additional_values):
        """Keep the lead active when marked as lost so it remains visible in the Perdu column."""
        lost_stage = self.env['crm.stage'].search([
            '|', ('name', 'ilike', 'Perdu'), ('name', 'ilike', 'Lost')
        ], limit=1)
        
        vals = dict(additional_values or {})
        vals.update({
            'active': True,
            'probability': 0.0,
            'automated_probability': 0.0,
        })
        if lost_stage:
            vals['stage_id'] = lost_stage.id

        self.write(vals)
        return True
