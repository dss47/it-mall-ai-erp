import json

from . import db, llm
from .filters import is_closing, is_farewell, is_human_request, is_pure_thanks
from .log import log

FALLBACK = "Je n'ai pas bien entendu. Pourriez-vous répéter, s'il vous plaît ?"
SATISFACTION_QUESTION = "Je vous en prie. Y a-t-il autre chose pour vous ?"
CLOSING_LINE = "Avec plaisir. Bonne journée et à bientôt."


def _capture_meta(state, reply, fallback_text=None):
    """Récolte nom, motif + analyse produits par le LLM pour les sauver en base."""
    analysis = reply.get("analysis") or {}
    motif = (reply.get("motif") or "").strip()
    if motif and not state.get("motif"):
        state["motif"] = llm._clean_motif(motif)[:300]
    elif fallback_text and not state.get("motif"):
        cleaned = llm._clean_motif(fallback_text)
        if cleaned:
            state["motif"] = cleaned[:200]

    # Capture caller name naturally if given
    c_name = analysis.get("caller_name")
    if c_name and isinstance(c_name, str) and len(c_name.strip()) > 2 and c_name.lower() not in ("null", "none", "inconnu", "client"):
        state["name"] = c_name.strip()
        state["done"] = True
    elif fallback_text and not state.get("name"):
        from .extract import extract_name
        nm = extract_name(fallback_text)
        if nm and len(nm.strip()) > 2:
            state["name"] = nm.strip()
            state["done"] = True

    for key in ("category", "desired_outcome", "urgency", "sentiment", "intent_type"):
        val = analysis.get(key)
        if val:
            state[key] = val
    if "estimated_total_revenue" in analysis and analysis["estimated_total_revenue"]:
        try:
            state["estimated_total_revenue"] = float(analysis["estimated_total_revenue"])
        except Exception:
            pass
    if "items" in analysis and isinstance(analysis["items"], list):
        state["items"] = analysis["items"]
    if analysis.get("needs_human"):
        state["needs_human"] = True


def process_turn(session, text):
    """Orchestre un tour de conversation : état → LLM → outil → persistance."""
    state = session.registry.state
    r = session.registry.advance(text)
    mode = r["mode"]

    if mode == "free":
        reply = llm.free(session, text)
        if reply is None:
            reply = {"reply_text": FALLBACK, "analysis": {}, "end_call": False}
        if reply.pop("offer", False) and not state.get("done") and not state.get("name"):
            state["step"] = "ask_name"
        _capture_meta(state, reply, text)
        if is_human_request(text) and (reply.get("analysis") or {}).get("needs_human"):
            if not state.get("done"):
                state["human_requested"] = True
                state["step"] = "ask_name"
                reply = llm.directive(
                    session, text,
                    ("Le client demande à parler à un responsable/conseiller. Accepte chaleureusement, "
                     "explique qu'un conseiller va le rappeler, puis demande son nom pour préparer son "
                     "dossier (ex. « Bien sûr, un conseiller vous rappellera. Puis-je avoir votre nom pour "
                     "préparer votre dossier, s'il vous plaît ? »)."))
                if reply is None:
                    reply = {"reply_text": ("Bien sûr, un conseiller vous rappellera. Puis-je avoir votre nom "
                                            "pour préparer votre dossier, s'il vous plaît ?"),
                             "analysis": {}}
                reply["end_call"] = False
            else:
                reply = llm.directive(
                    session, text,
                    ("Le client est déjà inscrit et demande à parler à un responsable. Rassure-le : un "
                     "conseiller va le rappeler rapidement. Formule de clôture."))
                if reply is None:
                    reply = {"reply_text": ("Un conseiller vous rappellera très rapidement. "
                                            "Merci et à bientôt."),
                             "analysis": {}}
                reply["end_call"] = True
            return reply

        # Clôture contrôlée : un congé ou une erreur raccroche proprement.
        if is_farewell(text) or is_closing(text) or llm.is_mistake_call(text):
            reply["end_call"] = True
            if not (reply.get("reply_text") or "").strip():
                reply["reply_text"] = CLOSING_LINE
        elif is_pure_thanks(text):
            if state.get("asked_satisfaction"):
                reply["end_call"] = True
                if not (reply.get("reply_text") or "").strip():
                    reply["reply_text"] = CLOSING_LINE
            else:
                state["asked_satisfaction"] = True
                reply = {"reply_text": SATISFACTION_QUESTION, "analysis": {}, "end_call": False}
        return reply

    if mode == "silent":
        return {"reply_text": "", "analysis": {}, "end_call": False}

    if mode == "end":
        reply = llm.directive(session, text, r["directive"])
        if reply is None:
            reply = {"reply_text": "Très bien. Bonne journée et à bientôt.", "analysis": {}}
        _capture_meta(state, reply)
        reply["end_call"] = True
        return reply

    if mode == "done":
        name = state.get("name") or ""
        phone = state.get("phone") or getattr(session, "caller_phone", "") or ""
        client_id = None
        if name and phone:
            client_id, _ = db.save_client(name, phone)
        if client_id:
            db.link_call_client(session.call_id, client_id)
        db.save_demande(session.call_id, client_id, session.reference or "R-0000",
                        state.get("motif") or name,
                        category=state.get("category"),
                        desired_outcome=state.get("desired_outcome"),
                        urgency=state.get("urgency"),
                        sentiment=state.get("sentiment"),
                        needs_human=bool(state.get("needs_human")))
        session.demande_saved = True
        log("dossier saved: name=%s phone=%s motif=%s cat=%s" % (
            name, phone, state.get("motif") or name, state.get("category")))
        state["asked_satisfaction"] = True
        reply = llm.directive(session, text, r["directive"])
        if reply is None:
            reply = {"reply_text": ("Parfait, c'est enregistré. Vous serez rappelé sous 24 heures. "
                                    "Autre chose pour vous ?"),
                     "analysis": {}}
        if r.get("human_close"):
            reply["end_call"] = True
        return reply

    # mode == "speak"
    reply = llm.directive(session, text, r["directive"])
    if reply is None:
        reply = {"reply_text": FALLBACK, "analysis": {}}
    _capture_meta(state, reply)
    if r.get("llm_name"):
        proposed = (reply.get("proposed_name") or "").strip()
        if proposed:
            state["name"] = proposed[:40]
            state["step"] = "confirm_name"
            log("llm proposed name=%r" % proposed)
    return reply
