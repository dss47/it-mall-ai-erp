import re

REG_AFFIRM = re.compile(
    r"\b(oui|ouais|exactement|voilà|voila|c'est ça|c'est ca|c'est bon|c'est exact|"
    r"c'est correct|c'est bien|correct|tout à fait|tout a fait|je confirme|confirme|"
    r"confirmé|bien reçu|bien recu|exact|oui oui|d'accord|daccord|ok|bien sûr|biensur|"
    r"je veux bien|volontiers|avec plaisir|carrément)\b",
    re.IGNORECASE)

REG_NEGATE = re.compile(
    r"\b(non|nan|jamais|c'est faux|c'est erroné|c'est pas ça|c'est pas ca|"
    r"ce n'est pas|ce n est pas|c'est pas|pas ça|pas ca|erreur|"
    r"recommençons|recommencez|recommencer|faux)\b",
    re.IGNORECASE)

REG_GOODBYE = re.compile(
    r"\b(?:au revoir|aurevoir|bonne journ|bonne soir|bonne nuit|bonne continuation|"
    r"bon apr|bonne apr|à bient|a bient|c'est tout(?!\s*ce\b)|c est tout(?!\s*ce\b)|"
    r"je vous laisse|je te laisse|je raccroche|bisous)",
    re.IGNORECASE)

_NOISE_RE = re.compile(
    r"sous[- ]titrage|sous[- ]titre|sous[- ]titres|réalisé[- ]?s? par|realisé[- ]?s? par|"
    r"radio[- ]?canada|société radio|societe radio|abonnez[- ]?vous|abonne[- ]?vous|"
    r"abonnez[- ]?toi|abonne[- ]?toi|"
    r"\bpépé\b|\bpepé\b|\bpepè\b|"
    r"subtitle|closed capti|sous titre|sous-titre",
    re.IGNORECASE)

_FILLER_WORDS = {"merci", "oui", "non", "bonjour", "bonsoir", "ok", "d'accord",
                 "au revoir", "aurevoir", "salut", "allo", "allô", "monsieur",
                 "madame", "mademoiselle", "hein", "euh", "voilà", "voila"}

_OFFER_RE = re.compile(
    r"(\s*(?:souhaitez[- ]vous|souhaiteriez[- ]vous|voulez[- ]vous|voudriez[- ]vous|"
    r"aimeriez[- ]vous|puis[- ]je|seriez[- ]vous|est[- ]ce que vous (?:souhaitez|voulez))\b"
    r"[^.!?\n]*?(?:inscr|rappell?[ée]|rappel|recontact)[^.!?\n]*[.!?]?)",
    re.IGNORECASE)


_COMPLAINT_RE = re.compile(
    r"\b(en panne|est panne|ne marche|ne fonctionne|ne s'allume|ne s allume|ne s'allument|"
    r"ne s allument|cassé|cassée|casses|defectueux|défectueux|problème|probleme|souci|"
    r"réclamation|reclamation|rembours|déçu|decu|insatisfait|service après-vente|sav|"
    r"abîmé|abime|endommagé|endommage|ne charge|ne répond|ne repond|plus rien"
    r")\b",
    re.IGNORECASE)


_HUMAN_RE = re.compile(
    r"\b(humain|une personne|quelqu'un|quelqu un|un conseiller|un agent|parler à|parler a|"
    r"transférer|transferer|transfère|transfere|responsable|vrai(e)? personne|opérateur|operateur)\b",
    re.IGNORECASE)


def is_human_request(text):
    return bool(text and _HUMAN_RE.search(text))


def is_complaint(text):
    return bool(text and _COMPLAINT_RE.search(text))


def strip_offer(text):
    """Retire une proposition d'inscription/rappel rédigée par le LLM en mode libre.

    L'offre n'est légitime que si le serveur l'a autorisée (offer=True, via l'outil ou
    needs_callback). Tout énoncé non autorisé qui ressemble à une offre est supprimé.
    """
    out = _OFFER_RE.sub("", text or "")
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def is_noise(text):
    return bool(text and _NOISE_RE.search(text))


def is_farewell(text):
    return bool(text and REG_GOODBYE.search(text))


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[?!.,;:]+", " ", text or "")).strip()


_PURE_THANKS_RE = re.compile(
    r"^(?:merci\w*(?:\s+(?:beaucoup|bien|de tout|encore|à vous|a vous|"
    r"monsieur|madame|mademoiselle))?\s*){1,3}$",
    re.IGNORECASE)

_REG_CLOSING_TOKENS = (
    "merci beaucoup|merci bien|merci de tout|merci encore|"
    "non merci|non c'est tout|non c est tout|non rien d'autre|non rien d autre|"
    "au revoir|aurevoir|bonne journ\\w*|bonne soir\\w*|bonne nuit|bonne continuation|"
    "à bient\\w*|a bient\\w*|"
    "c'est tout|c est tout|ce sera tout|ça sera tout|ca sera tout|"
    "rien d'autre|rien de plus|rien d autre|j'ai rien d'autre|j ai rien d autre|"
    "j'ai rien de plus|j ai rien de plus|j'ai tout ce qu'il me faut|j ai tout ce qu il me faut|"
    "tout ce qu'il me faut|tout ce qu il me faut|"
    "je vous laisse|je te laisse|je raccroche|je dois raccrocher|je vous laisse raccrocher|"
    "ça ira|ca ira|ça va merci|ca va merci|sans façon|allez au revoir|"
    "erreur|mauvais numéro|mauvais numero|trompé\\w*|trompe\\w*|"
    "ok merci au revoir|d'accord merci au revoir"
)
_REG_CLOSING = re.compile(r"^(?:(?:" + _REG_CLOSING_TOKENS + r")\s*){1,8}$", re.IGNORECASE)


def is_pure_thanks(text):
    return bool(text and _PURE_THANKS_RE.match(_norm(text)))


def is_closing(text):
    return bool(text and _REG_CLOSING.match(_norm(text)))


def is_filler_word(text):
    return (text or "").strip("?.! ").lower() in _FILLER_WORDS


def is_trivial_motif(text):
    return (text or "").strip("?.! \t\r\n").lower() in (
        "oui", "ouais", "non", "nan", "ok", "d'accord", "daccord")
