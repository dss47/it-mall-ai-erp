# -*- coding: utf-8 -*-
import logging
import re
import subprocess
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


import os

AMI_HOST = os.environ.get("AMI_HOST", "127.0.0.1")
AMI_PORT = int(os.environ.get("AMI_PORT", 5038))
AMI_USER = os.environ.get("AMI_USER", "odoo_ami")
AMI_SECRET = os.environ.get("AMI_SECRET", "odoo_ami_secret")


def _send_ami_action(action_dict):
    """Send an action to Asterisk AMI over TCP socket."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((AMI_HOST, AMI_PORT))
        s.recv(1024)
        s.sendall(f"Action: Login\r\nUsername: {AMI_USER}\r\nSecret: {AMI_SECRET}\r\n\r\n".encode())
        resp = s.recv(1024).decode(errors='ignore')
        if "Success" not in resp:
            s.close()
            return False, f"AMI login failed: {resp}"
        
        payload = "\r\n".join(f"{k}: {v}" for k, v in action_dict.items()) + "\r\n\r\n"
        s.sendall(payload.encode())
        action_resp = s.recv(2048).decode(errors='ignore')
        s.sendall(b"Action: Logoff\r\n\r\n")
        s.close()
        _logger.info(f"AMI action response: {action_resp}")
        return True, action_resp
    except Exception as e:
        _logger.error(f"AMI socket error: {e}")
        return False, str(e)


def originate_call(caller_ext, dest_number):
    """Originate an outbound call by directly signaling Zoiper via IPC."""
    if not caller_ext or not dest_number:
        return False, "Numéro ou extension manquant"
    clean_dest = re.sub(r"[^\d+*#]", "", str(dest_number))
    clean_ext = re.sub(r"[^\d]", "", str(caller_ext))
    if not clean_dest or not clean_ext:
        return False, "Numéro ou extension invalide"
    
    # 1. Send direct IPC Dial command to running Zoiper instance
    try:
        subprocess.run(
            ["sudo", "-u", "saad", "/opt/odoo-addons/it_mall_branding/zoiper_cli.sh", "dial", clean_dest],
            timeout=5, capture_output=True
        )
        return True, "Appel lancé"
    except Exception as e:
        _logger.warning(f"Zoiper CLI dial failed: {e}, falling back to AMI originate")
        # Fallback to AMI Originate
        ok, resp = _send_ami_action({
            "Action": "Originate",
            "Channel": f"PJSIP/{clean_ext}",
            "Context": "from-internal",
            "Exten": clean_dest,
            "Priority": "1",
            "CallerID": f'"IT Mall" <{clean_ext}>',
            "Async": "true",
        })
        return ok, "Appel lancé" if ok else resp


def get_channel_status(caller_ext):
    """Check the real-time status of an extension in Asterisk."""
    if not caller_ext:
        return {"status": "idle"}
    clean_ext = re.sub(r"[^\d]", "", str(caller_ext))
    ok, resp = _send_ami_action({
        "Action": "Command",
        "Command": "core show channels concise"
    })
    if not ok or not resp:
        return {"status": "idle"}
    
    # Check if clean_ext is present in active channels
    for line in resp.splitlines():
        if f"PJSIP/{clean_ext}-" in line or f"/{clean_ext}!" in line or f"!{clean_ext}!" in line:
            parts = line.split("!")
            state = (parts[4] if len(parts) > 4 else "").lower()
            if "up" in state:
                return {"status": "in_call", "state": "Up"}
            elif "ring" in state or "dial" in state:
                return {"status": "ringing", "state": "Ringing"}
            return {"status": "calling", "state": state}
            
    return {"status": "idle"}


def hangup_ext(caller_ext):
    """Request hangup on active channels for the extension and signal Zoiper."""
    if not caller_ext:
        return False
    clean_ext = re.sub(r"[^\d]", "", str(caller_ext))
    # 1. Signal Zoiper to hang up
    try:
        subprocess.run(
            ["sudo", "-u", "saad", "/opt/odoo-addons/it_mall_branding/zoiper_cli.sh", "hangup"],
            timeout=5, capture_output=True
        )
    except Exception:
        pass
    
    # 2. Also hangup in Asterisk
    ok, _ = _send_ami_action({
        "Action": "Command",
        "Command": f"channel request hangup PJSIP/{clean_ext}",
    })
    return True


class ResUsers(models.Model):
    _inherit = 'res.users'

    sip_extension = fields.Char(string="Poste SIP / Extension", default="2004", help="Extension SIP utilisée pour les appels sortants (ex: 2004)")


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_call_partner(self):
        self.ensure_one()
        phone = self.phone or self.mobile
        if not phone:
            raise UserError("Ce contact n'a aucun numéro de téléphone.")
        ext = self.env.user.sip_extension or '2004'
        ok, msg = originate_call(ext, phone)
        if ok:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '📞 Appel lancé',
                    'message': f"Votre poste ({ext}) sonne. Décrochez pour joindre {self.name} ({phone}).",
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(f"Échec du lancement de l'appel : {msg}")
