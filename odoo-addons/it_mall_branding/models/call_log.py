# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ItMallCallLog(models.Model):
    _name = 'it_mall.call.log'
    _description = "Journal d'appels"
    _order = 'call_date desc, id desc'

    name = fields.Char(string="Référence", compute='_compute_name', store=True)
    caller_name = fields.Char(string="Nom du client", required=True, default="Inconnu")
    caller_phone = fields.Char(string="Téléphone", required=True)
    motif = fields.Text(string="Motif de l'appel", default="Inconnu", required=True)
    call_date = fields.Datetime(string="Date & Heure", default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('urgent', 'Urgent'),
        ('to_call', 'À rappeler'),
        ('done', 'Traité'),
    ], string="Statut", default='to_call', required=True)
    target_role = fields.Selection([
        ('sales', 'Commercial / Ventes'),
        ('stock', 'Logistique / Stock'),
        ('support', 'Support Technique'),
        ('account', 'Comptabilité'),
        ('all', 'Tous'),
    ], string="Rôle Destinataire", default='all', required=True)
    user_id = fields.Many2one('res.users', string="Responsable")
    assigned_user_ids = fields.Many2many(
        'res.users', 'it_mall_call_log_users_rel', 'call_id', 'user_id',
        string="Assigné à l'équipe", compute='_compute_assigned_users', store=True, readonly=False
    )
    partner_id = fields.Many2one('res.partner', string="Contact lié")
    call_uuid = fields.Char(string="UUID Appel")
    recording_file = fields.Binary(string="Enregistrement audio", attachment=True)
    recording_filename = fields.Char(string="Nom du fichier audio", default="enregistrement.mp3")
    audio_player = fields.Html(string="Lecteur Audio", compute='_compute_audio_player', sanitize=False)
    notes = fields.Text(string="Notes internes")

    @api.depends('target_role')
    def _compute_assigned_users(self):
        for record in self:
            users = self.env['res.users']
            if record.target_role == 'sales':
                users = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False).users or self.env['res.users'].search([('groups_id', 'in', self.env.ref('sales_team.group_sale_salesman').id)])
            elif record.target_role == 'stock':
                users = self.env.ref('stock.group_stock_user', raise_if_not_found=False).users or self.env['res.users'].search([('groups_id', 'in', self.env.ref('stock.group_stock_user').id)])
            elif record.target_role == 'account':
                users = self.env.ref('account.group_account_invoice', raise_if_not_found=False).users or self.env['res.users'].search([('groups_id', 'in', self.env.ref('account.group_account_invoice').id)])
            elif record.target_role == 'support':
                users = self.env['res.users'].search([('share', '=', False)])
            elif record.target_role == 'all':
                users = self.env['res.users'].search([('share', '=', False)])
            
            # Filter internal users only
            internal_users = users.filtered(lambda u: not u.share and u.id > 1) if users else self.env.user
            record.assigned_user_ids = internal_users or [self.env.user.id]

    @api.depends('recording_file')
    def _compute_audio_player(self):
        for record in self:
            att = self.env['ir.attachment'].search([
                ('res_model', '=', 'it_mall.call.log'),
                ('res_id', '=', record.id),
                ('res_field', '=', 'recording_file'),
            ], limit=1)
            if att:
                record.audio_player = (
                    f'<div class="d-flex align-items-center p-2 rounded bg-light border">'
                    f'<i class="fa fa-play-circle me-2 text-primary fs-4"></i>'
                    f'<audio controls style="width: 100%; height: 38px;" preload="metadata" src="/web/content/{att.id}"></audio>'
                    f'</div>'
                )
            else:
                record.audio_player = '<div class="text-muted fst-italic py-2"><i class="fa fa-info-circle me-1"></i> Aucun enregistrement audio disponible</div>'

    @api.depends('caller_name', 'caller_phone')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.caller_name or 'Inconnu'} ({record.caller_phone or ''})"

    def action_mark_done(self):
        self.write({'state': 'done'})

    def action_mark_to_call(self):
        self.write({'state': 'to_call'})

    def action_mark_urgent(self):
        self.write({'state': 'urgent'})

    def action_call_back(self):
        self.ensure_one()
        from .telephony import originate_call
        from odoo.exceptions import UserError
        if not self.caller_phone or self.caller_phone in ("Inconnu", "?"):
            raise UserError("Numéro de téléphone introuvable.")
        ext = self.env.user.sip_extension or '2004'
        ok, msg = originate_call(ext, self.caller_phone)
        if ok:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '📞 Appel lancé',
                    'message': f"Votre poste ({ext}) sonne. Décrochez pour joindre {self.caller_name or self.caller_phone} ({self.caller_phone}).",
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(f"Échec de l'appel : {msg}")

    def action_create_partner(self):
        self.ensure_one()
        if not self.partner_id:
            name = self.caller_name if (self.caller_name and self.caller_name != "Inconnu") else f"Contact ({self.caller_phone})"
            partner = self.env['res.partner'].create({
                'name': name,
                'phone': self.caller_phone,
                'comment': f"Contact créé depuis le journal d'appels.\nDate : {fields.Datetime.to_string(self.call_date)}\nMotif : {self.motif or ''}",
            })
            self.partner_id = partner.id
            return {
                'type': 'ir.actions.act_window',
                'name': 'Contact créé',
                'res_model': 'res.partner',
                'res_id': partner.id,
                'view_mode': 'form',
                'target': 'current',
            }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.assigned_user_ids:
                record._compute_assigned_users()
        return records

    def action_view_partner(self):
        self.ensure_one()
        if self.partner_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.partner_id.name,
                'res_model': 'res.partner',
                'res_id': self.partner_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
