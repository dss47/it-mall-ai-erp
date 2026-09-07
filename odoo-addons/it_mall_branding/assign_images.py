import io
import base64
from PIL import Image, ImageDraw, ImageFont

PRODUCTS = [
    (99, "Téléphone IP Yealink", "Yealink SIP-T46U", "Téléphonie IP & VoIP", "#0284c7", "PHONE"),
    (100, "Téléphone IP Cisco", "Cisco IP Phone 7841", "Téléphonie IP & VoIP", "#0369a1", "PHONE"),
    (101, "Routeur MikroTik", "MikroTik hEX S / RouterBOARD", "Réseaux & Routage", "#475569", "ROUTER"),
    (102, "Switch PoE 16 Ports", "Switch Gigabit 16x PoE+", "Commutation & Réseaux", "#0f766e", "SWITCH"),
    (103, "Borne WiFi UniFi", "Ubiquiti UniFi U6 Pro AP", "WiFi Professionnel", "#2563eb", "WIFI"),
    (104, "Serveur Dell PowerEdge", "Dell PowerEdge R450 1U/2U", "Serveurs & Datacenter", "#1e293b", "SERVER"),
    (105, "Baie de Brassage 42U", "Baie Rack 19'' 42U 800x1000", "Baies & Infrastructure", "#334155", "RACK"),
    (107, "Pare-feu Cisco Meraki", "Cisco Meraki MX68 Security", "Sécurité & Firewall", "#047857", "FIREWALL"),
    (108, "Casque sans fil Jabra", "Jabra Evolve2 65 Bluetooth", "Casques & Accessoires", "#d97706", "HEADSET"),
    (109, "Onduleur APC 1500", "APC Smart-UPS 1500VA LCD", "Énergie & Protection", "#b91c1c", "UPS"),
    (119, "Passerelle VoIP Grandstream", "Grandstream GXW4104 FXO/FXS", "Téléphonie & Passerelles", "#0891b2", "GATEWAY"),
    (120, "Standard Téléphonique Grandstream", "Grandstream UCM6302 IPBX", "Standard & IPBX", "#0284c7", "IPBX"),
    (159, "Caméra Dôme Hikvision 4MP", "Hikvision DS-2CD2143G2 Dôme", "Vidéosurveillance IP", "#be123c", "CAMERA_DOME"),
    (160, "Caméra Extérieure Dahua 4MP", "Dahua IPC-HFW2431T-AS Bullet", "Vidéosurveillance IP", "#991b1b", "CAMERA_BULLET"),
    (161, "Caméra Rotative PTZ Hikvision", "Hikvision DarkFighter 25x PTZ", "Vidéosurveillance IP", "#881337", "CAMERA_PTZ"),
    (162, "Enregistreur NVR 8 Canaux", "NVR 4K 8 Canaux PoE Ultra HD", "Enregistreurs NVR", "#111827", "NVR"),
    (167, "Disque Dur Surveillance 4 To", "WD Purple / SkyHawk 4TB 24/7", "Stockage & Disques", "#7c3aed", "HDD"),
    (172, "Routeur Cisco Entreprise", "Cisco ISR 4321 Gigabit Router", "Réseaux & Routage", "#1d4ed8", "ROUTER"),
    (173, "Switch Cisco 24 Ports", "Cisco Catalyst 2960-X 24G", "Commutation & Réseaux", "#0369a1", "SWITCH"),
    (174, "Pare-feu Fortinet FortiGate", "FortiGate 60F Next-Gen Firewall", "Sécurité & Firewall", "#dc2626", "FIREWALL")
]

def create_product_image(tmpl_id, name, model, category, bg_accent, icon_type):
    W, H = 800, 800
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([(30, 30), (W-30, H-30)], radius=32, fill="#f8fafc", outline="#e2e8f0", width=3)
    draw.rounded_rectangle([(30, 30), (W-30, 150)], radius=32, fill=bg_accent)
    draw.rectangle([(30, 120), (W-30, 150)], fill=bg_accent)

    try:
        font_logo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_cat = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        font_model = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_footer = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except Exception:
        font_logo = font_cat = font_title = font_model = font_badge = font_footer = ImageFont.load_default()

    draw.text((60, 55), "IT MALL", fill="#ffffff", font=font_logo)
    draw.text((60, 100), f"EQUIPEMENT OFFICIEL • {category.upper()}", fill="#e0f2fe", font=font_cat)

    draw.rounded_rectangle([(160, 190), (640, 540)], radius=24, fill="#ffffff", outline="#cbd5e1", width=2)
    
    for gx in range(200, 620, 60):
        draw.line([(gx, 210), (gx, 520)], fill="#f1f5f9", width=1)
    for gy in range(230, 520, 60):
        draw.line([(180, gy), (620, gy)], fill="#f1f5f9", width=1)

    if "PHONE" in icon_type or "IPBX" in icon_type or "GATEWAY" in icon_type:
        draw.rounded_rectangle([(230, 260), (570, 480)], radius=18, fill="#334155", outline="#1e293b", width=3)
        draw.rounded_rectangle([(260, 285), (420, 410)], radius=8, fill="#38bdf8", outline="#0284c7", width=2)
        draw.text((275, 335), "IT MALL\nVOIP OK", fill="#0f172a", font=font_badge)
        for bx in range(450, 550, 32):
            for by in range(290, 410, 30):
                draw.rounded_rectangle([(bx, by), (bx+22, by+20)], radius=4, fill="#64748b")
        draw.rounded_rectangle([(200, 240), (250, 500)], radius=14, fill="#1e293b")
    elif "SWITCH" in icon_type:
        draw.rounded_rectangle([(200, 320), (600, 430)], radius=10, fill="#1e293b", outline="#0f172a", width=3)
        draw.text((225, 335), "CISCO CATALYST 24G PoE+", fill="#38bdf8", font=font_badge)
        for px in range(225, 575, 15):
            draw.rectangle([(px, 375), (px+10, 390)], fill="#22c55e" if px%30==0 else "#0284c7")
            draw.rectangle([(px, 398), (px+10, 413)], fill="#22c55e" if px%45==0 else "#0284c7")
    elif "ROUTER" in icon_type or "FIREWALL" in icon_type:
        draw.rounded_rectangle([(220, 310), (580, 430)], radius=12, fill="#1e293b", outline="#0f172a", width=3)
        draw.line([(260, 310), (230, 220)], fill="#64748b", width=8)
        draw.line([(540, 310), (570, 220)], fill="#64748b", width=8)
        draw.circle((230, 220), 7, fill="#334155")
        draw.circle((570, 220), 7, fill="#334155")
        draw.rounded_rectangle([(240, 335), (560, 405)], radius=6, fill="#0f172a")
        draw.text((260, 345), "ENTERPRISE SECURITY", fill="#ef4444" if "FIREWALL" in icon_type else "#38bdf8", font=font_badge)
        draw.circle((530, 370), 8, fill="#22c55e")
    elif "CAMERA" in icon_type:
        if "DOME" in icon_type:
            draw.ellipse([(280, 260), (520, 480)], fill="#f8fafc", outline="#64748b", width=4)
            draw.ellipse([(330, 310), (470, 440)], fill="#0f172a")
            draw.ellipse([(360, 340), (440, 410)], fill="#1e293b", outline="#38bdf8", width=3)
            draw.ellipse([(385, 360), (415, 390)], fill="#0284c7")
        elif "PTZ" in icon_type:
            draw.rounded_rectangle([(340, 230), (460, 290)], radius=8, fill="#64748b")
            draw.ellipse([(290, 280), (510, 490)], fill="#f8fafc", outline="#334155", width=4)
            draw.ellipse([(340, 330), (460, 440)], fill="#0f172a")
            draw.ellipse([(370, 360), (430, 415)], fill="#38bdf8")
        else:
            draw.polygon([(250, 320), (520, 300), (520, 410), (250, 400)], fill="#f8fafc", outline="#475569")
            draw.polygon([(520, 290), (560, 270), (560, 440), (520, 420)], fill="#334155")
            draw.ellipse([(545, 320), (575, 390)], fill="#38bdf8")
            draw.rectangle([(230, 380), (280, 460)], fill="#64748b")
    elif "WIFI" in icon_type:
        draw.ellipse([(270, 240), (530, 490)], fill="#ffffff", outline="#cbd5e1", width=4)
        draw.ellipse([(370, 335), (430, 395)], fill="#ffffff", outline="#2563eb", width=6)
        draw.text((365, 415), "UniFi 6", fill="#2563eb", font=font_badge)
    elif "SERVER" in icon_type or "RACK" in icon_type:
        draw.rounded_rectangle([(230, 240), (570, 500)], radius=12, fill="#0f172a", outline="#334155", width=4)
        for ry in range(260, 480, 42):
            draw.rounded_rectangle([(250, ry), (550, ry+32)], radius=4, fill="#1e293b", outline="#475569")
            draw.circle((270, ry+16), 5, fill="#22c55e")
            draw.circle((290, ry+16), 5, fill="#0284c7")
    elif "HEADSET" in icon_type:
        draw.arc([(280, 240), (520, 460)], start=180, end=0, fill="#334155", width=16)
        draw.rounded_rectangle([(260, 340), (310, 440)], radius=18, fill="#d97706")
        draw.rounded_rectangle([(490, 340), (540, 440)], radius=18, fill="#d97706")
        draw.line([(490, 410), (410, 470)], fill="#475569", width=6)
        draw.circle((400, 475), 10, fill="#0f172a")
    elif "HDD" in icon_type:
        draw.rounded_rectangle([(260, 240), (540, 490)], radius=16, fill="#e2e8f0", outline="#475569", width=3)
        draw.rounded_rectangle([(280, 260), (520, 380)], radius=8, fill="#7c3aed")
        draw.text((300, 290), "SURVEILLANCE\n4TB PURPLE 24/7", fill="#ffffff", font=font_badge)
        draw.ellipse([(350, 400), (450, 470)], fill="#94a3b8", outline="#475569", width=2)
    elif "UPS" in icon_type:
        draw.rounded_rectangle([(280, 230), (520, 500)], radius=12, fill="#1e293b", outline="#0f172a", width=3)
        draw.rounded_rectangle([(320, 260), (480, 340)], radius=6, fill="#0284c7")
        draw.text((345, 285), "1500VA\n100% OK", fill="#ffffff", font=font_badge)
        draw.circle((400, 400), 22, fill="#22c55e")
        draw.text((393, 390), "I", fill="#ffffff", font=font_badge)

    draw.text((60, 580), name, fill="#0f172a", font=font_title)
    draw.text((60, 635), f"Modèle Référence : {model}", fill="#64748b", font=font_model)

    draw.line([(60, 690), (W-60, 690)], fill="#e2e8f0", width=2)
    
    draw.rounded_rectangle([(60, 715), (250, 760)], radius=12, fill="#dcfce7", outline="#86efac")
    draw.text((80, 725), "✔ EN STOCK", fill="#15803d", font=font_footer)

    draw.rounded_rectangle([(270, 715), (480, 760)], radius=12, fill="#e0f2fe", outline="#7dd3fc")
    draw.text((290, 725), "GARANTIE 1 AN", fill="#0369a1", font=font_footer)

    draw.rounded_rectangle([(500, 715), (W-60, 760)], radius=12, fill="#f1f5f9", outline="#cbd5e1")
    draw.text((520, 725), "ORIGINAL 100%", fill="#334155", font=font_footer)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode('utf-8')

# Execute directly in Odoo ORM with commit
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '-d', 'it_mall_db'])

with odoo.registry('it_mall_db').cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    ProductTemplate = env['product.template']
    
    for tmpl_id, name, model, category, bg_accent, icon_type in PRODUCTS:
        tmpl = ProductTemplate.browse(tmpl_id)
        if tmpl.exists():
            b64_img = create_product_image(tmpl_id, name, model, category, bg_accent, icon_type)
            tmpl.write({'image_1920': b64_img})
            for variant in tmpl.product_variant_ids:
                variant.write({'image_1920': b64_img})
            print(f"✅ Enregistré & Validé : [{tmpl_id}] {name}")

    cr.commit()
    print("🎉 TOUTES LES IMAGES SONT COMMITTÉES DANS ODOO !")
