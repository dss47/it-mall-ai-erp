import time

from .config import RECITATION_BUDGET_S
from .extract import (extract_name, extract_phone_digits, has_non_latin_letters,
                      merge_phone, phone_to_spoken, valid_phone)
from .filters import REG_AFFIRM, REG_NEGATE, is_farewell, is_trivial_motif

# step -> expectation type (drives VAD patience)
STEP_EXPECTATION = {
    "free": "free",
    "propose_register": "yes_no",
    "ask_name": "short_free",
    "confirm_name": "yes_no",
    "ask_phone": "recitation",
    "confirm_phone": "yes_no",
}

QUESTION_STEPS = ("propose_register", "ask_name", "confirm_name", "ask_phone", "confirm_phone")


class Registry:
    """Machine à états déterministe de la collecte nom/numéro.

    Le LLM ne décide jamais de l'enregistrement : le serveur pilote l'étape et
    la patience, le LLM ne fait que rédiger la phrase demandée.
    """

    def __init__(self):
        self.state = {
            "step": "free",
            "name": "",
            "phone": "",
            "motif": "",
            "done": False,
            "recitation_start": None,
            "human_requested": False,
        }

    @property
    def step(self):
        return self.state["step"]

    def expectation(self):
        return STEP_EXPECTATION.get(self.state["step"], "free")

    def advance(self, text):
        """Analyse le tour du client et maintient une conversation fluide et libre."""
        text = (text or "").strip()
        if is_farewell(text):
            return {"mode": "end", "directive": "Le client prend congé. Remercie-le chaleureusement et souhaite-lui une excellente journée."}
        return {"mode": "free"}

        if step == "ask_phone":
            digits = extract_phone_digits(text)
            if digits:
                s["phone"] = merge_phone(s["phone"], digits)
            if valid_phone(s["phone"]):
                s["step"] = "confirm_phone"
                spoken = phone_to_spoken(s["phone"])
                return {"mode": "speak",
                        "directive": ("Répète le numéro par paires et demande confirmation : "
                                      "« Je répète votre numéro : %s. C'est bien ça ? »" % spoken)}
            if s.get("recitation_start") and time.time() - s["recitation_start"] > RECITATION_BUDGET_S:
                s["recitation_start"] = time.time()
                return {"mode": "speak",
                        "directive": ("Le client dicte un numéro incomplet depuis longtemps. Demande-lui "
                                      "poliment de répéter son numéro en entier, doucement.")}
            if digits:
                return {"mode": "silent"}
            return {"mode": "speak",
                    "directive": ("On attendait le numéro de téléphone. Guide doucement le client à dicter "
                                  "son numéro en parlant, chiffre par chiffre.")}

        if step == "confirm_phone":
            if affirmed:
                s["step"] = "free"
                s["done"] = True
                first = s["name"].split()[0] if s["name"] else s["name"]
                if s.get("human_requested"):
                    return {"mode": "done", "human_close": True,
                            "directive": ("Le client est enregistré et attendait un conseiller. Confirme "
                                          "l'enregistrement puis rassure-le : « C'est noté, %s. Un conseiller "
                                          "vous rappellera très rapidement pour votre demande. Merci et à "
                                          "bientôt. »" % first)}
                return {"mode": "done",
                        "directive": ("Confirme l'enregistrement et le rappel sous 24 heures, puis demande s'il y "
                                      "autre chose (ex. « Parfait, %s, c'est enregistré. Vous serez rappelé "
                                      "sous 24 heures. Autre chose pour vous ? »)." % first)}
            if negated:
                s["phone"] = ""
                s["step"] = "ask_phone"
                s["recitation_start"] = time.time()
                return {"mode": "speak",
                        "directive": ("Le numéro était faux. Excuse-toi brièvement et redemande le numéro "
                                      "en entier.")}
            return {"mode": "speak",
                    "directive": ("Confirme à nouveau le numéro : « %s, c'est bien ça ? »"
                                  % phone_to_spoken(s["phone"]))}

        return {"mode": "free"}
