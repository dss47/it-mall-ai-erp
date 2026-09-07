import os
import re
import sqlite3
import time

import psycopg2
import psycopg2.extras

from .config import DB_DIR, DB_PATH

# ---------------------------------------------------------------------------
# SQLite schema (internal call tracking)
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT UNIQUE,
    session_dir TEXT,
    reference TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    outcome TEXT,
    client_id INTEGER,
    odoo_call_log_id INTEGER
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER,
    role TEXT,
    text TEXT,
    ts TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS demandes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER,
    client_id INTEGER,
    reference TEXT,
    motif TEXT,
    category TEXT,
    desired_outcome TEXT,
    urgency TEXT,
    sentiment TEXT,
    needs_human INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calls_uuid ON calls (uuid);
CREATE INDEX IF NOT EXISTS idx_turns_call ON turns (call_id);
CREATE INDEX IF NOT EXISTS idx_demandes_call ON demandes (call_id);
"""

# ---------------------------------------------------------------------------
# Odoo PostgreSQL connection
# ---------------------------------------------------------------------------
from .config import ODOO_DB, ODOO_HOST, ODOO_PASS, ODOO_PORT, ODOO_USER

_odoo_lock = __import__("threading").Lock()


def _odoo_conn():
    return psycopg2.connect(
        dbname=ODOO_DB, user=ODOO_USER, password=ODOO_PASS,
        host=ODOO_HOST, port=ODOO_PORT,
        connect_timeout=5, options="-c statement_timeout=5000",
    )


# ---------------------------------------------------------------------------
# SQLite helpers (internal)
# ---------------------------------------------------------------------------
_lock = __import__("threading").Lock()


def _conn():
    os.makedirs(DB_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    with _lock:
        con = _conn()
        try:
            con.executescript(_SCHEMA)
            con.commit()
        finally:
            con.close()


# ---------------------------------------------------------------------------
# Caller ID from dialplan file
# ---------------------------------------------------------------------------
_CALLER_DIR = "/opt/voice-agent/.caller_id"


def read_caller_phone(uuid_hex):
    """Read caller phone written by the dialplan before AudioSocket connect."""
    path = os.path.join(_CALLER_DIR, "%s.caller" % uuid_hex)
    try:
        with open(path) as f:
            phone = f.read().strip()
        os.unlink(path)
        return phone or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Product catalog (from Odoo)
# ---------------------------------------------------------------------------
_GENERIC_QUERY_WORDS = {
    "tous", "tout", "toute", "toutes", "catalogue", "liste", "listes", "lister",
    "produit", "produits", "stock", "stocks", "disponible", "disponibles",
    "en", "avez", "vous", "avoir", "de", "des", "du", "le", "la", "les",
    "quels", "quelles", "quelle", "quel", "equipement", "équipement",
    "équipements", "materiel", "matériel", "marchandise", "article", "articles",
    "dans", "est", "ce", "que", "pour", "sur", "avec", "un", "une", "vos",
    "votre", "nos", "notre", "bonjour", "salut", "cherche", "recherche",
}

# French → English synonyms for product search (common networking/telecom terms)
_FR_EN_SYNONYMS = {
    "passerelle": ["gateway", "fxs", "gsm"],
    "passerelles": ["gateway", "fxs", "gsm"],
    "gateway": ["gateway"],
    "gateways": ["gateway"],
    "dans le stream": ["grandstream"],
    "danstream": ["grandstream"],
    "stream": ["grandstream"],
    "pare-feu": ["firewall", "fortigate"],
    "parefeu": ["firewall", "fortigate"],
    "firewall": ["firewall", "fortigate"],
    "routeur": ["router", "mikrotik", "cisco"],
    "switch": ["switch", "poe"],
    "commutateur": ["switch", "catalyst"],
    "camera": ["camera", "cam"],
    "caméra": ["camera", "cam"],
    "cameras": ["camera", "cam"],
    "caméras": ["camera", "cam"],
    "casque": ["headset", "headphone", "jabra", "plantronics"],
    "casques": ["headset", "headphone", "jabra", "plantronics"],
    "ecouteur": ["headset", "headphone"],
    "écouteur": ["headset", "headphone"],
    "telephon": ["phone", "ip phone"],
    "téléphone": ["phone", "ip phone"],
    "telephones": ["phone", "ip phone"],
    "téléphones": ["phone", "ip phone"],
    "ipbx": ["ipbx", "ucm"],
    "pabx": ["ipbx", "ucm"],
    "standard": ["ipbx", "ucm"],
    "onduleur": ["ups", "smart-ups", "apc"],
    "onduleurs": ["ups", "smart-ups", "apc"],
    "disque": ["hdd", "skyhawk", "seagate"],
    "disques": ["hdd", "skyhawk", "seagate"],
    "disque dur": ["hdd", "skyhawk", "seagate"],
    "serveur": ["server", "poweredge", "dell"],
    "serveurs": ["server", "poweredge", "dell"],
    "baie": ["rack", "baie", "brassage"],
    "rack": ["rack", "baie"],
    "boîtier": ["box", "modem"],
    "modem": ["modem"],
    "borne": ["ap", "access point", "wifi", "unifi"],
    "bornes": ["ap", "access point", "wifi", "unifi"],
    "point d'accès": ["ap", "access point", "wifi"],
    "point d'acces": ["ap", "access point", "wifi"],
    "antenne": ["antenna", "ap"],
    "câble": ["cable", "cat6", "rj45"],
    "cable": ["cable", "cat6", "rj45"],
    "cables": ["cable", "cat6", "rj45"],
    "nvr": ["nvr", "enregistreur"],
    "enregistreur": ["nvr"],
    "panneau": ["panel", "patch"],
    "pince": ["tool", "crimping"],
    "visio": ["visioconférence", "rally", "logitech"],
    "visioconférence": ["visioconférence", "rally", "logitech"],
}


def _extract_name(name_field):
    """Extract readable name from Odoo JSONB name field."""
    if isinstance(name_field, dict):
        return name_field.get("fr_FR") or name_field.get("en_US") or next(iter(name_field.values()), "")
    return str(name_field or "")


def get_products(query):
    import unicodedata
    raw_q = (query or "").strip().lower()
    if not raw_q:
        return {"query": raw_q, "products": []}
    
    # Normalize accents (e.g. téléphone -> telephone, caméra -> camera)
    q = unicodedata.normalize('NFKD', raw_q).encode('ASCII', 'ignore').decode('utf-8')
    words = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) > 1]
    generic = bool(words) and all(w in _GENERIC_QUERY_WORDS for w in words)
    # Remove purely generic words for scoring
    specific = [w for w in words if w not in _GENERIC_QUERY_WORDS]
    if not specific:
        specific = words  # fallback: use all words
    expanded = list(specific)
    for w in specific:
        if w in _FR_EN_SYNONYMS:
            expanded.extend(_FR_EN_SYNONYMS[w])
    for term, en_words in _FR_EN_SYNONYMS.items():
        term_norm = unicodedata.normalize('NFKD', term).encode('ASCII', 'ignore').decode('utf-8')
        if term_norm in q and term_norm not in specific:
            expanded.extend(en_words)
    try:
        con = _odoo_conn()
        try:
            cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT pt.id, pt.name, pt.list_price, pt.description_sale,
                       COALESCE(SUM(sq.quantity), 0)::int AS stock
                FROM product_template pt
                LEFT JOIN product_product pp ON pp.product_tmpl_id = pt.id
                LEFT JOIN stock_quant sq ON sq.product_id = pp.id
                     AND sq.location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                WHERE pt.active = true
                GROUP BY pt.id, pt.name, pt.list_price, pt.description_sale
            """)
            hits = []
            for r in cur.fetchall():
                name = _extract_name(r["name"])
                desc = r.get("description_sale") or ""
                name_low = unicodedata.normalize('NFKD', name.lower()).encode('ASCII', 'ignore').decode('utf-8')
                desc_low = unicodedata.normalize('NFKD', desc.lower()).encode('ASCII', 'ignore').decode('utf-8')
                if generic:
                    score = 1
                else:
                    name_hits = sum(1 for w in expanded if re.search(r"\b" + re.escape(w), name_low))
                    desc_hits = sum(1 for w in expanded if re.search(r"\b" + re.escape(w), desc_low))
                    score = name_hits * 3 + desc_hits  # name matches weighted 3x
                if score > 0:
                    hits.append({
                        "name": name,
                        "description": desc[:200],
                        "price_mad": float(r["list_price"]),
                        "stock": r["stock"],
                        "_score": score,
                    })
            hits.sort(key=lambda h: h["_score"], reverse=True)
            for h in hits:
                del h["_score"]
            return {"query": q, "products": hits[:8]}
        finally:
            con.close()
    except Exception as e:
        return {"query": q, "products": [], "error": str(e)}


def get_active_catalog_summary():
    """Charge dynamiquement la liste de tous les produits actifs depuis PostgreSQL Odoo."""
    try:
        con = _odoo_conn()
        try:
            cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT pt.id, pt.name, pt.list_price 
                FROM product_template pt
                WHERE pt.active = true
                ORDER BY pt.name
            """)
            items = []
            for r in cur.fetchall():
                name = _extract_name(r["name"])
                price = float(r["list_price"])
                items.append(f"{name} ({price:.0f} DH)")
            return ", ".join(items)
        finally:
            con.close()
    except Exception:
        return ""


def lookup_client(phone):
    """Look up a customer by phone number in Odoo contacts or past call history. Returns dict or None."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if not digits:
        return None
    suffix = digits[-8:] if len(digits) >= 6 else digits
    try:
        con = _odoo_conn()
        try:
            cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            partner = None
            # 1. Search in official contacts (res_partner)
            cur.execute("""
                SELECT id, name, phone, mobile, email, function, company_name
                FROM res_partner
                WHERE phone IS NOT NULL AND (active = true OR active IS NULL) AND id > 1
            """)
            for row in cur.fetchall():
                stored = re.sub(r"\D", "", row["phone"] or "")
                stored_m = re.sub(r"\D", "", row.get("mobile") or "")
                if stored and (stored == digits or (len(digits) >= 6 and (stored.endswith(suffix) or suffix.endswith(stored[-8:])))):
                    partner = dict(row)
                    break
                if stored_m and (stored_m == digits or (len(digits) >= 6 and (stored_m.endswith(suffix) or suffix.endswith(stored_m[-8:])))):
                    partner = dict(row)
                    break

            # 2. Search in call history (it_mall_call_log) for past callers and their last meaningful motif
            cur.execute("""
                SELECT id, caller_name AS name, caller_phone AS phone, motif, partner_id
                FROM it_mall_call_log
                WHERE caller_phone IS NOT NULL
                ORDER BY id DESC
            """)
            last_call = None
            found_motif = None
            for row in cur.fetchall():
                stored = re.sub(r"\D", "", row["phone"] or "")
                if stored and (stored == digits or (len(digits) >= 6 and (stored.endswith(suffix) or suffix.endswith(stored[-8:])))):
                    if not last_call:
                        last_call = row
                    m = (row.get("motif") or "").strip()
                    m_lower = m.lower()
                    # Mots-clés de produits ou demandes commerciales concrètes OBLIGATOIRES
                    PRODUCT_KEYWORDS = (
                        "switch", "cisco", "borne", "unifi", "routeur", "mikrotik", "serveur", "poweredge",
                        "caméra", "camera", "dahua", "hikvision", "onduleur", "apc", "baie", "42u", "ipbx",
                        "standard", "disque", "casque", "jabra", "téléphone", "telephone", "yealink", "meraki",
                        "fortigate", "fortinet", "nvr", "ptz", "devis", "commande"
                    )
                    # Mots-clés interdits (bavardage, fin de conversation, statut générique)
                    FORBIDDEN_KEYWORDS = (
                        "fin de conversation", "fin d'appel", "sans achat", "clôture", "cloture", "inconnu",
                        "appel ia", "aucun", "erreur", "faux numéro", "plus tard", "merci", "au revoir",
                        "renseignement", "renseignements", "information", "informations", "assistance",
                        "discussion", "conversation", "demande"
                    )
                    has_product = any(k in m_lower for k in PRODUCT_KEYWORDS)
                    has_forbidden = any(k in m_lower for k in FORBIDDEN_KEYWORDS)

                    if m and not found_motif and has_product and not has_forbidden and len(m) > 4:
                        found_motif = m

            if partner:
                if found_motif:
                    partner["last_motif"] = found_motif
                return partner

            if last_call and last_call.get("name") and last_call["name"] not in ('Inconnu', 'Anonymous', 'unknown', ''):
                res = {
                    "id": last_call.get("partner_id"),
                    "name": last_call["name"],
                    "phone": last_call["phone"],
                    "is_history": True,
                }
                if found_motif:
                    res["last_motif"] = found_motif
                return res

            return None
        finally:
            con.close()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Customer save (upsert into Odoo res_partner)
# ---------------------------------------------------------------------------
def save_client(name, phone):
    """Upsert client into Odoo res_partner. Returns (partner_id, created: bool)."""
    name = (name or "").strip()
    phone = (phone or "").strip()
    if not name and not phone:
        return None, False
    digits = re.sub(r"\D", "", phone)
    suffix = digits[-8:] if len(digits) >= 6 else digits
    try:
        con = _odoo_conn()
        try:
            cur = con.cursor()
            # Look for existing partner by phone
            if phone and suffix:
                cur.execute("""
                    SELECT id, phone, mobile FROM res_partner
                    WHERE active = true AND id > 1
                """)
                for row in cur.fetchall():
                    stored = re.sub(r"\D", "", row[1] or "")
                    stored_m = re.sub(r"\D", "", row[2] or "")
                    if (stored and stored.endswith(suffix)) or (stored_m and stored_m.endswith(suffix)):
                        pid = row[0]
                        if name:
                            cur.execute("UPDATE res_partner SET name=%s WHERE id=%s", (name, pid))
                        cur.execute("UPDATE res_partner SET write_date=NOW() WHERE id=%s", (pid,))
                        con.commit()
                        return pid, False
            # Insert new partner
            cur.execute("""
                INSERT INTO res_partner (name, phone, is_company, customer_rank, autopost_bills, active, create_date, write_date)
                VALUES (%s, %s, false, 1, 'manual', true, NOW(), NOW())
                RETURNING id
            """, (name or "Inconnu", phone or None))
            pid = cur.fetchone()[0]
            con.commit()
            return pid, True
        finally:
            con.close()
    except Exception as e:
        return None, False


# ---------------------------------------------------------------------------
# Call log (write to Odoo it_mall_call_log)
# ---------------------------------------------------------------------------
def save_call_log(caller_name, caller_phone, motif, state="to_call", partner_id=None, notes=None, call_uuid=None, target_role="sales"):
    """Insère un appel directement dans it_mall.call.log de Odoo."""
    try:
        con = _odoo_conn()
        try:
            cur = con.cursor()
            display = "%s (%s)" % (caller_name or "Inconnu", caller_phone or "?") if (caller_name or caller_phone) else "Appel IA"
            role = target_role or "sales"
            cur.execute("""
                INSERT INTO it_mall_call_log
                    (name, caller_name, caller_phone, motif, call_date, state, target_role,
                     partner_id, notes, call_uuid, create_date, write_date)
                VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (display, caller_name or "Inconnu", caller_phone or "Inconnu",
                  motif or "Inconnu", state, role, partner_id, notes, call_uuid))
            rid = cur.fetchone()[0]

            # Populate assigned users relation directly for instant display in UI
            group_name = 'sales_team.group_sale_salesman' if role == 'sales' else ('stock.group_stock_user' if role == 'stock' else ('account.group_account_invoice' if role == 'account' else None))
            if group_name:
                cur.execute("""
                    SELECT u.id FROM res_users u
                    JOIN res_groups_users_rel rel ON rel.uid = u.id
                    JOIN ir_model_data imd ON imd.res_id = rel.gid
                    WHERE imd.module = %s AND imd.name = %s AND u.share = false AND u.id > 1
                """, group_name.split('.'))
            else:
                cur.execute("SELECT id FROM res_users WHERE share = false AND id > 1")
            
            uids = [r[0] for r in cur.fetchall()] or [2]
            for uid in uids:
                cur.execute("INSERT INTO it_mall_call_log_users_rel (call_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (rid, uid))

            con.commit()
            return rid
        finally:
            con.close()
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Internal SQLite functions (calls, turns, demandes)
# ---------------------------------------------------------------------------
def create_call(uuid, session_dir, reference):
    with _lock:
        con = _conn()
        try:
            cur = con.execute(
                "INSERT INTO calls (uuid, session_dir, reference) VALUES (?,?,?)",
                (uuid, session_dir, reference))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()


def end_call(call_id, outcome):
    with _lock:
        con = _conn()
        try:
            con.execute("UPDATE calls SET ended_at=datetime('now'), outcome=? WHERE id=?",
                        (outcome or "", call_id))
            con.commit()
        finally:
            con.close()


def link_call_client(call_id, client_id):
    if not call_id or not client_id:
        return
    with _lock:
        con = _conn()
        try:
            con.execute("UPDATE calls SET client_id=? WHERE id=?", (client_id, call_id))
            con.commit()
        finally:
            con.close()


def log_turn(call_id, role, text):
    if not text:
        return
    with _lock:
        con = _conn()
        try:
            con.execute("INSERT INTO turns (call_id, role, text) VALUES (?,?,?)",
                        (call_id, role, text))
            con.commit()
        finally:
            con.close()


def save_demande(call_id, client_id, reference, motif, category=None,
                 desired_outcome=None, urgency=None, sentiment=None, needs_human=False):
    with _lock:
        con = _conn()
        try:
            con.execute(
                "INSERT INTO demandes (call_id, client_id, reference, motif, category, desired_outcome, "
                "urgency, sentiment, needs_human) VALUES (?,?,?,?,?,?,?,?,?)",
                (call_id, client_id, reference, motif, category, desired_outcome,
                 urgency, sentiment, 1 if needs_human else 0))
            con.commit()
        finally:
            con.close()
