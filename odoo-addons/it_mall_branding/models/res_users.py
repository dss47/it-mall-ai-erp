from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def it_mall_set_password(self, new_password):
        self.ensure_one()
        new_password = new_password.strip()
        if not new_password:
            return
        hashed = self._crypt_context().hash(new_password)
        self._set_encrypted_password(self.id, hashed)
