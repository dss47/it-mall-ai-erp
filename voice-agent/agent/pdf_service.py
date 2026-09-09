import os
import sys
import json
import uuid
import urllib.request
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

# ─── Credentials loaded from db.env (never hardcoded) ───────────────────────
def _load_env(path="/opt/voice-agent/db.env"):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env

_ENV = _load_env()
TOKEN = _ENV.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = _ENV.get("WHATSAPP_PHONE_ID", "")


def generate_odoo_pdf(order_id):
    """Génère le devis Odoo en Français (fr_FR) directement en mémoire.
    
    FIX C-01: order_id est validé comme entier — aucune injection possible.
    FIX M-01: subprocess exécuté en tant que user 'odoo' pour accéder au bon filestore.
    """
    # ── Validation stricte : order_id doit être un entier positif ──────────
    try:
        order_id = int(order_id)
        if order_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, None

    tmp_path = f"/tmp/Devis_Odoo_{order_id}.pdf"

    script = (
        "import odoo\n"
        "from odoo import api, SUPERUSER_ID\n"
        "odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', 'it_mall_db'])\n"
        f"with odoo.registry('it_mall_db').cursor() as cr:\n"
        "    env = api.Environment(cr, SUPERUSER_ID, {})\n"
        f"    order = env['sale.order'].browse({order_id})\n"
        "    order.partner_id.lang = 'fr_FR'\n"
        f"    pdf_bytes, _ = env['ir.actions.report'].with_context(lang='fr_FR')._render_qweb_pdf('sale.report_saleorder', [{order_id}])\n"
        f"    open('{tmp_path}', 'wb').write(pdf_bytes)\n"
    )

    # ── subprocess avec liste d'arguments (pas os.system) ───────────────────
    # ── Exécuté en tant qu'utilisateur 'odoo' pour le bon filestore ─────────
    try:
        result = subprocess.run(
            ["sudo", "-u", "odoo", "/usr/share/odoo/venv/bin/python", "-c", script],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            return None, None
    except subprocess.TimeoutExpired:
        return None, None
    except Exception:
        return None, None

    if os.path.exists(tmp_path):
        with open(tmp_path, "rb") as f:
            data = f.read()
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return data, tmp_path
    return None, None


def send_pdf_to_whatsapp(order_id, phone, quote_ref="Devis", customer_name="Client", amount=""):
    """Téléverse le PDF vers Meta et l'envoie sur le WhatsApp du client."""
    if not TOKEN or not PHONE_NUMBER_ID:
        return {"success": False, "error": "WhatsApp credentials not configured in db.env"}

    try:
        clean_phone = ''.join(c for c in str(phone) if c.isdigit())
        if not clean_phone:
            return {"success": False, "error": "Invalid phone number"}
        if clean_phone.startswith('0') and len(clean_phone) == 10:
            clean_phone = '212' + clean_phone[1:]
        elif clean_phone.startswith('2120'):
            clean_phone = '212' + clean_phone[4:]

        pdf_bytes, file_path = generate_odoo_pdf(order_id)
        if not pdf_bytes:
            return {"success": False, "error": "Could not generate Odoo PDF"}

        filename = f"Devis_IT_Mall_{quote_ref}.pdf"

        # 1. Upload to Meta Media API
        boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="messaging_product"\r\n\r\n'
            f'whatsapp\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="type"\r\n\r\n'
            f'application/pdf\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: application/pdf\r\n\r\n'
        ).encode('utf-8') + pdf_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

        upload_req = urllib.request.Request(
            f'https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/media',
            data=body,
            headers={
                'Authorization': f'Bearer {TOKEN}',
                'Content-Type': f'multipart/form-data; boundary={boundary}'
            }
        )

        with urllib.request.urlopen(upload_req, timeout=20) as resp:
            media_id = json.loads(resp.read().decode()).get('id')

        if not media_id:
            return {"success": False, "error": "Failed to get media_id from Meta"}

        # 2. Send Document using approved template or fallback to document message
        # Format payload with template and uploaded media_id in header
        template_payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': clean_phone,
            'type': 'template',
            'template': {
                'name': 'devis_itmall_fr',
                'language': {'code': 'fr'},
                'components': [
                    {
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': customer_name or 'Client'},
                            {'type': 'text', 'text': quote_ref or 'S000XX'}
                        ]
                    }
                ]
            }
        }

        # Send the official approved template with attached PDF Document Header
        template_payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': clean_phone,
            'type': 'template',
            'template': {
                'name': 'devis_client_itmall',
                'language': {'code': 'fr'},
                'components': [
                    {
                        'type': 'header',
                        'parameters': [
                            {
                                'type': 'document',
                                'document': {
                                    'id': media_id,
                                    'filename': filename
                                }
                            }
                        ]
                    },
                    {
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': customer_name or 'Client'},
                            {'type': 'text', 'text': quote_ref or 'S000XX'}
                        ]
                    }
                ]
            }
        }

        req = urllib.request.Request(
            f'https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages',
            data=json.dumps(template_payload).encode('utf-8'),
            headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            res = json.loads(resp.read().decode())
            return {"success": True, "result": res, "mode": "official_template_document"}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


class PDFHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/send_quote_pdf":
            content_len = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_len)
            try:
                data = json.loads(post_body.decode('utf-8'))
                order_id = data.get("order_id")
                phone = data.get("phone")
                quote_ref = data.get("quote_ref", "S000XX")
                name = data.get("name", "Client")
                amount = data.get("amount", "")

                if not order_id or not phone:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "order_id and phone are required"}).encode())
                    return

                res = send_pdf_to_whatsapp(order_id, phone, quote_ref, name, amount)
                self.send_response(200 if res.get("success") else 500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_pdf_server(port=8301):
    # Bind on 0.0.0.0 so n8n running in Docker container can reach it via gateway
    server = HTTPServer(('0.0.0.0', port), PDFHandler)
    server.serve_forever()


if __name__ == "__main__":
    start_pdf_server(8301)
