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

