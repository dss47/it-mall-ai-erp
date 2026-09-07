from odoo import _, fields, models
from odoo.exceptions import UserError


class ItMallPasswordWizard(models.TransientModel):
    _name = 'it_mall.password.wizard'
    _description = 'Set User Password'

    user_id = fields.Many2one('res.users', string='User', required=True, readonly=True)
    new_password = fields.Char(string='New Password', required=True)
    confirm_password = fields.Char(string='Confirm Password', required=True)

    def action_set_password(self):
        self.ensure_one()
        if not self.new_password:
            raise UserError(_('Password cannot be empty.'))
        if self.new_password != self.confirm_password:
            raise UserError(_('Passwords do not match.'))
        self.user_id.it_mall_set_password(self.new_password)
        return {'type': 'ir.actions.act_window_close'}
