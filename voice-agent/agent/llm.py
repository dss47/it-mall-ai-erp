import json
import subprocess

from .config import GEMINI_KEY, GEMINI_MAX_TOKENS, GEMINI_URL
from .filters import is_complaint, strip_offer
from .log import log
from .prompt import DIRECTIVE_SYSTEM_PROMPT, SYSTEM_PROMPT


import requests

_http_session = requests.Session()


def _gemini_api(payload):
    url = GEMINI_URL + "?key=" + GEMINI_KEY
    try:
        r = _http_session.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        if r.status_code == 200:
            return r.json()
        log("gemini http %d: %s" % (r.status_code, r.text[:200]))
        return {}
    except Exception as e:
        log("gemini request error: %r" % e)
        return {}


def parse_json(text):
    text = (text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start >= 0:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
                continue
            if in_str:
                if c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
    return None


def _extract_text(d):
    if "candidates" not in d or not d["candidates"]:
        log("gemini no candidate: %s" % json.dumps(d, ensure_ascii=False)[:300])
        return None
    parts = d["candidates"][0]["content"].get("parts", [])
    texts = [p.get("text", "") for p in parts if "text" in p]
    if not texts:
        return None
    return parse_json(texts[0])


def _build_payload(system, history, new_text, extra_user=None, session=None):
    from . import db
    live_catalog = db.get_active_catalog_summary()
    catalog_instruction = ""
    if live_catalog:
        catalog_instruction = (
            f"\n\nCATALOGUE ACTIF EN TEMPS RÉEL (Issu directement de la base de données Odoo) :\n"
            f"Les produits commercialisés actuellement par IT Mall sont : {live_catalog}.\n"
            f"RÈGLE STRICTE : Si le client demande un article qui n'est PAS dans cette liste issue de la base, indique clairement qu'il n'est pas disponible en catalogue et propose les articles disponibles associés.\n"
        )
    sys_text = system + catalog_instruction
    if session and hasattr(session, "product_memory") and session.product_memory:
        mem_lines = ["\n\nPRODUITS RÉCUPÉRÉS DEPUIS LA BASE ODOO (En mémoire pour cet appel) :"]
        for cat, items in session.product_memory.items():
            mem_lines.append(f"• Catégorie '{cat}' :\n{items}")
        sys_text += "\n" + "\n".join(mem_lines) + "\n(Utilise ces données en mémoire pour répondre directement aux questions suivantes sans ré-appeler d'outil !)"
    contents = []
    for h in history[-12:]:
        role = "user" if h.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": new_text}]})
    if extra_user:
        contents.append({"role": "user", "parts": [{"text": extra_user}]})
    return {
        "system_instruction": {"parts": [{"text": sys_text}]},
        "generationConfig": {
            "maxOutputTokens": GEMINI_MAX_TOKENS,
            "responseMimeType": "application/json",
        },
        "contents": contents,
    }


def _call(payload, retries=2):
    for attempt in range(retries):
        try:
            d = _gemini_api(payload)
        except Exception as e:
            log("gemini error (attempt %d): %r" % (attempt + 1, e))
            continue
        result = _extract_text(d)
        if result is not None:
            return result
        log("gemini returned None (attempt %d)" % (attempt + 1))
    return None


def _finalize(parsed, session):
    parsed.pop("needs_tool", None)
    parsed.pop("tool_args", None)
    if parsed.get("registered") is not None:
        parsed.pop("registered", None)
    if not (parsed.get("reply_text") or "").strip():
        parsed["reply_text"] = "Je n'ai pas bien entendu. Pourriez-vous répéter, s'il vous plaît ?"
    return parsed


def directive(session, text, directive):
    payload = _build_payload(DIRECTIVE_SYSTEM_PROMPT, session.history, text,
                             extra_user="DIRECTIVE : " + directive)
    parsed = _call(payload)
    if parsed is None:
        return None
    return _finalize(parsed, session)


def _clean_motif(text):
    if not text:
        return ""
    import re
    t = text.strip().strip('"\'')
    t = re.sub(r"^(bonjour|bonsoir|salut|allo|allô|merci|s'il vous plaît|svp)[,\.\s]+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(je vous appelle pour|j'appelle pour|est-ce que vous avez|avez-vous|je cherche|je voudrais|je veux|j'aimerais savoir si vous avez)[,\.\s]+", "Demande de ", t, flags=re.IGNORECASE)
    t = re.sub(r"\?+$", "", t)
    return t.strip()


_FILLER_TEXT = "Laissez-moi vérifier notre système, s'il vous plaît."
_filler_audio = None


def _get_filler_audio():
    global _filler_audio
    if _filler_audio is None:
        try:
            from .tts import piper_tts
            _filler_audio = piper_tts(_FILLER_TEXT)
        except Exception:
            _filler_audio = None
    return _filler_audio


def is_mistake_call(text):
    low = (text or "").lower()
    # Erreur sur le produit / quantité (ex: "erreur de ma part, je voulais 10") -> Ce n'est PAS un faux numéro !
    if any(k in low for k in ("voulais", "commande", "quantité", "quantite", "article", "produit", "disque", "switch", "camera")):
        return False
    # Mauvais numéro ou appel d'entreprise erroné
    wrong_number_patterns = [
        "mauvais numéro", "mauvais numero", "mauvaise entreprise", "mauvaise société", "mauvaise societe",
        "ce n'est pas vous", "faux numéro", "faux numero", "pas le bon numéro", "pas le bon numero",
        "trompé de numéro", "trompe de numero", "trompé d'entreprise", "erreur de numéro", "erreur de numero",
        "erreur de ma part", "me suis trompé", "me suis trompe", "trompé d'endroit", "c'était une erreur", "c etait une erreur"
    ]
    return any(p in low for p in wrong_number_patterns)


def free(session, text):
    """Réponse libre avec outils (get_product_info). Retourne le dict réponse avec une
    clé interne 'offer' si une proposition d'inscription doit suivre."""
    if is_mistake_call(text):
        return {
            "reply_text": "Pas de souci, aucun problème. Je vous souhaite une excellente journée !",
            "end_call": True,
            "motif": "Appel par erreur",
            "reference": session.reference,
            "analysis": {"category": "autre", "desired_outcome": "Fin d'appel (erreur de numéro)", "needs_human": False}
        }

    payload = _build_payload(SYSTEM_PROMPT, session.history, text, session=session)
    parsed = _call(payload)
    if parsed is None:
        return None

    needs_tool = parsed.get("needs_tool") or "none"
    offer = False
    analysis = parsed.get("analysis") or {}
    state = session.registry.state

    complaint = is_complaint(text)
    if needs_tool == "get_product_info":
        filler = _get_filler_audio()
        if filler is not None and getattr(session, "play", None):
            session.play(filler)

        from . import tools
        query = (parsed.get("tool_args") or {}).get("query", "")
        result = tools.get_product_info(query)
        log("tool get_product_info -> %s" % json.dumps(result, ensure_ascii=False)[:300])

        products_list = result.get("products", [])
        if products_list:
            if not hasattr(session, "product_memory"):
                session.product_memory = {}
            summary_items = [f"• {p['name']}: {p['price_mad']} DH" for p in products_list]
            session.product_memory[query.lower()] = "\n".join(summary_items)

        known_name = state.get("name") or (session.caller_partner.get("name") if getattr(session, "caller_partner", None) else None)
        if known_name:
            first_n = known_name.split()[0]
            closing_instr = (
                f"Le prénom du client est DÉJÀ connu ({first_n}) : ne lui redemande SURTOUT PAS son nom ! "
                "Demande simplement s'il souhaite passer commande ou s'il y a autre chose pour lui."
            )
        elif complaint:
            closing_instr = "Rassure le client sur la prise en charge et demande son nom pour créer son dossier."
        else:
            closing_instr = "Termine en demandant poliment son nom pour noter sa demande : « Quel est votre nom s'il vous plaît ? »."

        clean_products = [{"name": p["name"], "price_mad": p["price_mad"]} for p in products_list]
        follow = ("Résultat des produits en base Odoo : %s\n"
                  "Rédige maintenant TA réponse finale au client dans le même JSON "
                  "(needs_tool \"none\", n'appelle plus d'outil). "
                  "Donne l'information produit demandée (prix exact en dirhams marocains, sans mentionner de chiffre de stock).\n"
                  "Dans le champ JSON \"motif\", donne un RÉSUMÉ synthétique et professionnel du besoin (max 8 mots, ex: « Demande devis switch Cisco »).\n"
                  "%s"
                  % (json.dumps(clean_products, ensure_ascii=False)[:900], closing_instr))
        payload2 = dict(payload)
        payload2["contents"] = payload["contents"] + [{"role": "user", "parts": [{"text": follow}]}]
        final = _call(payload2)
        if final is None:
            parsed.pop("needs_tool", None)
            parsed.pop("tool_args", None)
            return parsed
        parsed = final
        parsed.pop("needs_tool", None)
        parsed.pop("tool_args", None)
        if not state.get("done") and not complaint and not state.get("name"):
            offer = True
            m = (parsed.get("motif") or "").strip()
            if m and not state.get("motif"):
                state["motif"] = _clean_motif(m)
    elif analysis.get("needs_callback") and not state.get("done") and not complaint and not state.get("name"):
        offer = True
        m = (parsed.get("motif") or "").strip()
        if m and not state.get("motif"):
            state["motif"] = _clean_motif(m)

    m = (parsed.get("motif") or "").strip()
    if m and not state.get("motif"):
        state["motif"] = _clean_motif(m)

    if not offer:
        cleaned = strip_offer(parsed.get("reply_text") or "")
        if cleaned:
            parsed["reply_text"] = cleaned

    parsed["offer"] = offer
    return parsed


def post_call_analyze(history, caller_name="Client"):
    """Analyse complète et structurée de la transcription à la fin de l'appel pour Odoo & n8n."""
    from . import db
    catalog_summary = db.get_active_catalog_summary()
    transcript_lines = []
    for h in history:
        role = "Client" if h.get("role") == "user" else "Assistant"
        cnt = (h.get("content") or "").strip()
        if cnt and not cnt.startswith("Contexte client :"):
            transcript_lines.append(f"{role}: {cnt}")
    transcript_text = "\n".join(transcript_lines)

    prompt = (
        "Tu es l'analyseur CRM & ERP expert de l'entreprise IT Mall.\n"
        "Voici la transcription complète de l'appel téléphonique qui vient de s'achever :\n"
        f"\"\"\"\n{transcript_text}\n\"\"\"\n\n"
        f"CATALOGUE OFFICIEL ODOO EN TEMPS RÉEL :\n{catalog_summary}\n\n"
        "TÂCHE :\n"
        "1. Identifie l'intention principale (\"intent_type\") :\n"
        "   - \"quote_request\" : UNIQUEMENT pour les commandes standard (quantités <= 20 unités par produit).\n"
        "   - \"general_inquiry\" : pour les simples renseignements OU pour les COMMANDES EN GROS (> 20 unités, ex: 50, 100, 300 unités) car elles nécessitent l'intervention humaine d'un commercial (dans ce cas : items=[], needs_human=true, pas de devis automatique).\n"
        "   - \"order_cancellation\" : si le client demande d'annuler ou modifier une commande.\n"
        "   - \"support_urgent\" : en cas de panne critique ou coupure technique.\n"
        "2. Dans \"items\", liste TOUS les articles demandés/commandés (seulement si intent_type == 'quote_request'). Si la quantité d'un article dépasse 20, items DOIT être une liste vide [].\n"
        "3. Calcule \"estimated_total_revenue\" (somme des quantités * prix unitaire). 0 si annulation, commande en gros ou simple info.\n"
        "4. Rédige un \"motif\" clair et ultra-synthétique (max 8 mots, ex: « Devis 2 switchs Cisco et 2 bornes WiFi »).\n\n"
        "Réponds STRICTEMENT en JSON avec ce format :\n"
        "{\n"
        "  \"intent_type\": \"quote_request|order_cancellation|general_inquiry|support_urgent\",\n"
        "  \"category\": \"produit|livraison|paiement|service|autre\",\n"
        "  \"motif\": \"...\",\n"
        "  \"items\": [\n"
        "    {\n"
        "      \"product_name\": \"Nom exact du produit\",\n"
        "      \"quantity\": 1,\n"
        "      \"unit_price\": 0,\n"
        "      \"total_price\": 0\n"
        "    }\n"
        "  ],\n"
        "  \"estimated_total_revenue\": 0,\n"
        "  \"urgency\": \"normal|high\",\n"
        "  \"needs_human\": false\n"
        "}"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 600,
            "responseMimeType": "application/json"
        }
    }
    res = _call(payload)
    return res if isinstance(res, dict) else {}

