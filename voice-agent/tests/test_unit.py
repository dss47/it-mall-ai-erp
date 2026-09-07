import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent import db
from agent.engine import _capture_meta
from agent.extract import (extract_name, extract_phone_digits, has_non_latin_letters,
                           merge_phone, phone_to_spoken, valid_phone)
from agent.filters import (is_closing, is_complaint, is_farewell, is_filler_word,
                           is_noise, is_pure_thanks, is_trivial_motif, strip_offer)
from agent.registry import Registry

failures = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        failures.append(label)


# --- extract: nom ---
check("nom 'Je m'appelle Ahmed Benali'", extract_name("Je m'appelle Ahmed Benali") == "Ahmed Benali")
check("nom simple 'Sade'", extract_name("Sade") == "Sade")
check("nom sans chiffre-parole",
      extract_name("Je m'appelle Sophie Vois et mon numéro c'est zéro six") == "Sophie Vois")
check("nom épelé 'S O P H I E'", extract_name("S O P H I E") == "Sophie")
check("hésitation 'Ah,' pas un nom", extract_name("Ah,") == "")
check("hésitation 'As ?' pas un nom", extract_name("As ?") == "")
check("dédup 'Ahmed Ahmed'", extract_name("Ahmed Ahmed") == "Ahmed")
check("non-latin 'Aحمد بن Ali'", has_non_latin_letters("Aحمد بن Ali") is True)
check("latin pur 'Karim'", has_non_latin_letters("Karim Mansouri") is False)

# --- extract: numéro ---
check("chiffres directs", extract_phone_digits("0 6 22 44 51 03") == "0622445103")
check("dictée FR 'zéro six vingt-deux'", extract_phone_digits("zéro six vingt-deux") == "0622")
check("dictée FR 'quarante-quatre'", extract_phone_digits("quarante-quatre") == "44")
check("dictée FR 'cinquante et un'", extract_phone_digits("cinquante et un") == "51")
check("dictée FR 'zéro trois'", extract_phone_digits("zéro trois") == "03")

# --- extract: merge / validité ---
check("merge 06+22", merge_phone("06", "22") == "0622")
check("merge fragment complet", merge_phone("0622445103", "") == "0622445103")
check("merge +212 9 chiffres → 0 restauré", merge_phone("", "212661223344") == "0661223344")
check("merge +212 avec 0 présent", merge_phone("", "2120661223344") == "0661223344")
check("merge 12 chiffres commençant par 0 garde le 0", merge_phone("", "066122334455") == "0661223344")
check("merge indicatif sur numéro en cours", merge_phone("0661", "223344") == "0661223344")
check("valid 0622445103", valid_phone("0622445103") is True)
check("valid 11 chiffres", valid_phone("06224451031") is False)
check("valid sans 0 initial", valid_phone("6112131414") is False)
check("valid court", valid_phone("062244") is False)

# --- extract: réitération parlée ---
check("phone_to_spoken 0622445103",
      phone_to_spoken("0622445103") == "zéro six, vingt-deux, quarante-quatre, cinquante-et-un, zéro trois")
check("phone_to_spoken avec préfixe +33 fallback", len(phone_to_spoken("3362244510")) > 0)

# --- filters ---
check("noise 'Sous-titrage Société Radio-Canada'", is_noise("Sous-titrage Société Radio-Canada"))
check("pas bruit 'répète' (client demande de répéter)", not is_noise("répète"))
check("noise 'Pépé?'", is_noise("Est-ce que vous pouvez répondre à Pépé"))
check("noise 'abonnez-vous'", is_noise("abonnez-vous à la chaîne"))
check("pas bruit 'prix box fibre'", not is_noise("quel est le prix de la box fibre"))
check("filler 'Merci.'", is_filler_word("Merci."))
check("filler 'Monsieur ?'", is_filler_word("Monsieur ?"))
check("pas filler 'Je veux la box'", not is_filler_word("Je veux la box"))
check("trivial 'Oui ?'", is_trivial_motif("Oui ?"))
check("trivial 'oui.'", is_trivial_motif("oui."))
check("adieu 'c'est tout'", is_farewell("C'est tout merci"))
check("pas adieu 'c'est tout ce que vous avez ?'",
      not is_farewell("c'est tout ce que vous avez comme routeurs ?"))
check("adieu 'au revoir'", is_farewell("au revoir"))

# --- filters : réclamation / offre ---
check("réclamation 'ne s'allume plus'", is_complaint("le routeur ne s'allume plus"))
check("réclamation 'en panne'", is_complaint("ma box est en panne"))
check("pas réclamation 'répéteur en stock ?'", not is_complaint("vous avez un répéteur en stock ?"))
check("strip_offer retire l'offre",
      strip_offer("Je suis navré. Souhaitez-vous que je vous inscrive pour qu'on vous rappelle avec plus de détails ?")
      == "Je suis navré.")
check("strip_offer garde une phrase normale",
      strip_offer("Nous avons le Répéteur wifi 6 à 49€ en stock.") == "Nous avons le Répéteur wifi 6 à 49€ en stock.")

# --- registry : navigation fluide et clôture ---
r = Registry()
adv = r.advance("Je voudrais des informations sur vos routeurs wifi 6")
check("free → mode free", adv["mode"] == "free")
check("free → step free", r.step == "free")

adv_bye = r.advance("Au revoir et merci")
check("adieu → mode end", adv_bye["mode"] == "end")

# --- extraction naturelle du nom & analyse via _capture_meta ---
state = {"name": "", "motif": "", "done": False}
_capture_meta(state, {
    "reply_text": "Très bien M. Karim Mansouri, je note votre demande de devis.",
    "analysis": {"caller_name": "Karim Mansouri", "category": "produit", "intent_type": "devis"}
}, fallback_text="Je m'appelle Karim Mansouri")

check("nom capturé depuis analysis", state["name"] == "Karim Mansouri")
check("done marqué à True", state["done"] is True)
check("category enregistrée", state["category"] == "produit")
check("intent_type enregistré", state["intent_type"] == "devis")


# --- filters : clôture contrôlée ---
check("is_farewell au revoir", is_farewell("au revoir"))
check("is_farewell bonne journée", is_farewell("bonne journée monsieur"))
check("is_farewell merci au revoir", is_farewell("merci au revoir"))
check("is_farewell c'est tout", is_farewell("c'est tout"))
check("c'est tout ce que vous avez ≠ farewell",
      not is_farewell("c'est tout ce que vous avez"))

check("merci = pur remerciement", is_pure_thanks("merci"))
check("merci beaucoup = pur remerciement", is_pure_thanks("merci beaucoup"))
check("merci à vous = pur remerciement", is_pure_thanks("merci à vous"))
check("merci ponctué = pur remerciement", is_pure_thanks("Merci."))
check("merci beaucoup ponctué = pur remerciement", is_pure_thanks("Merci beaucoup !"))
check("merci au revoir ≠ pur remerciement", not is_pure_thanks("merci au revoir"))
check("non merci ≠ pur remerciement", not is_pure_thanks("non merci"))

check("non merci = clôture", is_closing("non merci"))
check("non, merci. ponctué = clôture", is_closing("Non, merci."))
check("OK. = clôture", is_closing("OK."))
check("Non ? = clôture", is_closing("Non ?"))
check("rien d'autre = clôture", is_closing("rien d'autre"))
check("c'est bon. = clôture", is_closing("c'est bon."))
check("non = clôture", is_closing("non"))
check("bonne journée = clôture", is_closing("bonne journée à bientôt"))
check("Au revoir ! = clôture", is_closing("Au revoir !"))
check("non c'est tout. = clôture", is_closing("Non, c'est tout."))
check("merci ≠ clôture (géré par pure_thanks)", not is_closing("merci"))
check("pas clôture : prix du routeur",
      not is_closing("je veux le prix du routeur"))
check("non + info ≠ clôture",
      not is_closing("non je veux le prix du routeur"))
check("c'est tout ce que vous avez ≠ clôture",
      not is_closing("c'est tout ce que vous avez"))

# --- engine : motif = première raison (jamais écrasé) ---
_mst = {"motif": ""}
_capture_meta(_mst, {"motif": "demande de prix routeur AX3000",
                     "analysis": {"category": "produit"}}, "texte brut")
check("motif = première raison", _mst["motif"] == "demande de prix routeur AX3000")
_capture_meta(_mst, {"motif": "Confirmation du numéro",
                     "analysis": {"category": "service"}})
check("motif jamais écrasé", _mst["motif"] == "demande de prix routeur AX3000")
check("category mise à jour", _mst["category"] == "service")

if __name__ == "__main__":
    print("\n%d failures" % len(failures))
    sys.exit(1 if failures else 0)

