import re

PHONE_LEN = 10


def extract_name_letters(text):
    if not text:
        return ""
    toks = re.findall(r"[A-Za-zÀ-ÿ]+", text)
    singles = [t for t in toks if len(t) == 1]
    if not singles:
        return ""
    if len(singles) >= 3 and len(singles) * 2 >= len(toks):
        return "".join(singles).upper()
    if len(toks) == 1 and len(toks[0]) == 1:
        return singles[0].upper()
    if len(singles) >= 2 and len(singles) == len(toks):
        return "".join(singles).upper()
    return ""


def extract_phone_digits(text):
    t = text or ""
    d = re.sub(r"\D", "", t)
    if d:
        return d
    toks = _FR_NUM_RE.findall(t)
    if toks and _fr_number_turn(t, toks):
        d = _fr_number_digits(t)
        if d:
            return d
    return ""


def _fr_number_turn(text, toks):
    words = [w for w in re.findall(r"[a-zà-ÿ]+", text.lower())
             if w not in _FR_UNITS and w not in _FR_TEENS and w not in _FR_TENS and w != "et"]
    conn = {"mon", "ma", "mes", "numéro", "numero", "telephone", "téléphone", "c'est", "cest",
            "est", "le", "la", "les", "de", "du", "je", "suis", "moi", "voila", "voilà",
            "oui", "non", "a", "au", "aux", "ça", "ca", "pour"}
    leftover = [w for w in words if w not in conn]
    return len(toks) >= 4 or (len(toks) >= 1 and not leftover)


_FR_UNITS = {"zéro": 0, "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3,
             "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9}
_FR_TEENS = {"onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
             "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19}
_FR_TENS = {"dix": 10, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
            "soixante": 60, "soixante-dix": 70, "quatre-vingt": 80, "quatre-vingt-dix": 90}
_FR_NUM_RE = re.compile(
    r"quatre-vingt-dix|soixante-dix|dix-sept|dix-huit|dix-neuf|quatre-vingt|"
    r"soixante|cinquante|quarante|trente|vingt|dix|onze|douze|treize|quatorze|"
    r"quinze|seize|zéro|zero|une|un|deux|trois|quatre|cinq|six|sept|huit|neuf|et",
    re.IGNORECASE)

_FR_NUMBER_WORDS = (set(_FR_UNITS) | set(_FR_TEENS) | set(_FR_TENS)
                    | {"quatre-vingt-dix", "soixante-dix", "dix-sept", "dix-huit",
                       "dix-neuf", "quatre-vingt"})


def _fr_number_digits(text):
    tokens = _FR_NUM_RE.findall(text or "")
    out = []
    i = 0
    while i < len(tokens):
        tok = tokens[i].lower()
        if tok == "et":
            i += 1
            continue
        if tok in _FR_TENS:
            total = _FR_TENS[tok]
            i += 1
            while i < len(tokens):
                t = tokens[i].lower()
                if t == "et":
                    i += 1
                    continue
                if t in _FR_UNITS:
                    total += _FR_UNITS[t]
                    i += 1
                elif t in _FR_TEENS:
                    total += _FR_TEENS[t]
                    i += 1
                break
            out.append("%02d" % total if total >= 10 else str(total))
        elif tok in _FR_TEENS:
            out.append(str(_FR_TEENS[tok]))
            i += 1
        elif tok in _FR_UNITS:
            out.append(str(_FR_UNITS[tok]))
            i += 1
        else:
            i += 1
    return "".join(out)


def _strip_country(d):
    """Retire l'indicatif marocain 212 et restaure le 0 local si nécessaire."""
    if d.startswith("212") and len(d) >= 11:
        r = d[3:]
        if len(r) == 9 and not r.startswith("0"):
            return "0" + r
        return r
    return d


def _truncate(d):
    """Réduit à PHONE_LEN chiffres en gardant un éventuel 0 initial."""
    if len(d) <= PHONE_LEN:
        return d
    if d.startswith("0"):
        return d[:PHONE_LEN]
    return d[-PHONE_LEN:]


def merge_phone(cur, newd):
    if not newd:
        return cur
    newd = _strip_country(newd)
    if not newd:
        return cur
    if not cur:
        return _truncate(newd)
    if len(newd) >= PHONE_LEN:
        return _truncate(newd)
    if newd in cur:
        return cur
    if cur in newd:
        return newd
    m = min(len(cur), len(newd), 4)
    for k in range(m, 2, -1):
        if cur[-k:] == newd[:k]:
            return _truncate(cur + newd[k:])
        if newd[-k:] == cur[:k]:
            return _truncate(newd + cur[k:])
    return _truncate(cur + newd)


def valid_phone(phone):
    return len(phone or "") == PHONE_LEN and phone.startswith("0")


_NAME_INTRO = re.compile(
    r"(je\s+m'?appelle|je\s+m'?apelle|je\s+suis|moi\s+c'est|mon\s+nom\s+(c'est|est)|"
    r"j'appelle|c'est|le\s+nom\s+c'est)",
    re.IGNORECASE)

_NAME_FILLER_WORDS = {
    "je", "j", "c", "m", "d", "l", "s", "n", "t", "suis", "mon", "ma", "mes",
    "moi", "appelle", "m'appelle", "apelle", "nom", "numéro", "numero",
    "telephone", "téléphone", "c'est", "cest", "ca", "ça", "est", "et", "de", "du",
    "des", "le", "la", "les", "un", "une", "au", "aux", "merci", "bonjour", "bonsoir",
    "salut", "oui", "non", "ok", "d'accord", "voila", "voilà", "ou", "à", "a", "chez",
    "monsieur", "madame", "mademoiselle", "excusez", "pardon", "alors", "voudrais",
    "veux", "veut", "souhaite", "souhaiterais", "peux", "pouvez", "puis", "aider",
    "inscrire", "inscris", "enregistrer", "avoir", "obtenir", "demander", "demande",
    "appeler", "rappeler", "laisser", "message", "compte", "pour", "avec", "sans",
    "sur", "dans", "pas", "plus", "bien", "très", "tres", "s'il", "sil", "vous",
    "votre", "svp", "please", "appelle",
    "inconnu", "inconnue", "inconnus", "unknown", "nan", "none", "null",
    "quoi", "que", "qu", "qu'est-ce", "comment", "pourquoi", "exact", "exactement",
    "ce", "cet", "cette", "ces", "parce", "pardon", "excuse", "excusez",
    "répète", "repete", "répéter", "repeter", "répétez", "répété",
    "ah", "as", "euh", "hmm", "hum", "bah", "oh", "ben",
}


def _name_words(s):
    parts = []
    for tok in re.findall(r"[A-Za-zÀ-ÿ'\-]+", s):
        for sub in re.split(r"['-]", tok):
            if sub:
                parts.append(sub)
    return [p for p in parts if p.lower() not in _NAME_FILLER_WORDS
            and p.lower() not in _FR_NUMBER_WORDS]


def _name_words_keep_all(s):
    parts = []
    for tok in re.findall(r"[A-Za-zÀ-ÿ'\-]+", s):
        for sub in re.split(r"['-]", tok):
            if sub:
                parts.append(sub)
    return parts


_NON_LATIN_RE = re.compile(r"[^\x00-\x7FÀ-ÿ]")


def has_non_latin_letters(text):
    """True si le texte contient des lettres hors alphabet latin (ex. arabe)."""
    return bool(text and _NON_LATIN_RE.search(text))


def _dedupe(words):
    out = []
    for w in words:
        if not out or out[-1].lower() != w.lower():
            out.append(w)
    return out


def extract_name(text):
    """Nom saisi naturellement : lettres épelées OU mots parlés, bruit filtré."""
    t = text or ""
    letters = extract_name_letters(t)
    if letters:
        return letters.title()
    m = _NAME_INTRO.search(t)
    if m:
        kept = _name_words(t[m.end():])
        if kept:
            return " ".join(_dedupe(kept)[-2:]).title()[:40]
        return ""
    kept = _name_words(t)
    if not kept:
        return ""
    kept_u = _dedupe(kept)
    if len(kept_u) <= 3 and kept_u == _dedupe(_name_words_keep_all(t)):
        return " ".join(kept_u).title()[:40]
    return ""


_DIGIT_WORDS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"]
_FR_UNITS_W = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"]
_FR_TEENS_W = ["dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
               "dix-sept", "dix-huit", "dix-neuf"]
_FR_TENS_W = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}


def digits_to_words(d):
    return " ".join(_DIGIT_WORDS[int(ch)] for ch in (d or "") if ch.isdigit())


def _fr_number(n):
    """0-69 en toutes lettres ; au-delà → None (repli sur les chiffres un à un)."""
    if 0 <= n < 10:
        return _FR_UNITS_W[n]
    if 10 <= n < 20:
        return _FR_TEENS_W[n - 10]
    if n in _FR_TENS_W:
        return _FR_TENS_W[n]
    if 20 < n < 70:
        t = n // 10 * 10
        r = n % 10
        if r == 1:
            return _FR_TENS_W[t] + "-et-un"
        return _FR_TENS_W[t] + "-" + _FR_UNITS_W[r]
    return None


def phone_to_spoken(phone):
    """Réitération parlée d'un numéro par paires (ex. 0622445103 → zéro six, vingt-deux, ...)."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) != PHONE_LEN:
        return digits_to_words(d)
    words = []
    for i in range(0, 10, 2):
        pair = d[i:i + 2]
        if pair[0] == "0":
            words.append(" ".join(_DIGIT_WORDS[int(ch)] for ch in pair))
            continue
        n = int(pair)
        w = _fr_number(n)
        if w is None:
            w = " ".join(_DIGIT_WORDS[int(ch)] for ch in pair)
        words.append(w)
    return ", ".join(words)
