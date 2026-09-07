import os
import sys

sys.path.insert(0, "/opt/voice-agent")

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

# --- registry : parcours complet (exemple utilisateur) ---
r = Registry()
adv = r.advance("Je voudrais des informations sur vos routeurs wifi 6")
check("free → mode free", adv["mode"] == "free")
check("free → step free", r.step == "free")

# après une réponse produit, le moteur met step=propose_register
r.state["step"] = "propose_register"
adv = r.advance("Oui")
check("offre acceptée → ask_name", adv["mode"] == "speak" and r.step == "ask_name")
check("offre directive demande le nom", "nom" in adv["directive"].lower())

# accord formulé autrement que "Oui" (ex. "d'accord", "je veux bien")
for accord in ("D'accord", "d'accord", "Ok", "Bien sûr", "Je veux bien", "Ouais"):
    r_ok = Registry()
    r_ok.state["step"] = "propose_register"
    adv_ok = r_ok.advance(accord)
    check("accord %r → ask_name" % accord,
          adv_ok["mode"] == "speak" and r_ok.step == "ask_name")

adv = r.advance("Ahmed Benali")
check("nom capturé → confirm_name", adv["mode"] == "speak" and r.step == "confirm_name")
check("nom stocké", r.state["name"] == "Ahmed Benali")
check("directive confirme le nom", "Ahmed Benali" in adv["directive"])

# --- registry : nom en écriture non latine → llm_name ---
r_ar = Registry()
r_ar.state["step"] = "ask_name"
adv = r_ar.advance("Aحمد بن Ali")
check("nom non-latin → llm_name", adv["mode"] == "speak" and adv.get("llm_name") is True)
check("nom non-latin : pas encore confirmé", r_ar.step == "ask_name")

# --- registry : correction du nom en confirm_name ---
r_fix = Registry()
r_fix.state["step"] = "confirm_name"
r_fix.state["name"] = "Ah"
adv = r_fix.advance("Ahmed Ahmed")
check("confirm_name : nom corrigé sans 'Non'", adv["mode"] == "speak")
check("confirm_name : nom mis à jour", r_fix.state["name"] == "Ahmed")
check("confirm_name : reste en confirmation", r_fix.step == "confirm_name")
check("confirm_name : directive cite le nouveau nom", "Ahmed" in adv["directive"])

adv = r.advance("Oui, c'est ça")
check("nom confirmé → ask_phone", adv["mode"] == "speak" and r.step == "ask_phone")
check("ask_phone = recitation (haute patience)", r.expectation() == "recitation")

adv = r.advance("Zéro six")
check("dictée partielle → silent (pas de coupure)", adv["mode"] == "silent")
check("téléphone partiel '06'", r.state["phone"] == "06")

adv = r.advance("vingt-deux")
check("dictée 2 → silent", adv["mode"] == "silent" and r.state["phone"] == "0622")

adv = r.advance("quarante-quatre")
adv = r.advance("cinquante et un")
adv = r.advance("zéro trois")
check("numéro complet → confirm_phone", r.step == "confirm_phone")
check("numéro final 0622445103", r.state["phone"] == "0622445103")
check("directive répète le numéro", "répète" in adv["directive"] or "Répète" in adv["directive"])

adv = r.advance("Exact")
check("confirmation → done", adv["mode"] == "done")
check("done flag posé", r.state["done"] is True)
check("retour à free", r.step == "free")

adv = r.advance("Autre chose : vous avez des switchs ?")
check("après done, jamais re-collect (free)", adv["mode"] == "free")

# --- registry : refus d'inscription ---
r2 = Registry()
r2.state["step"] = "propose_register"
adv = r2.advance("Non merci")
check("refus → retour free", adv["mode"] == "speak" and r2.step == "free")
check("aucun nom collecté après refus", r2.state["name"] == "")

# --- registry : nom faux ---
r3 = Registry()
r3.state["step"] = "confirm_name"
r3.state["name"] = "Ahmed Benali"
adv = r3.advance("Non, c'est Ahmed Bellal")
check("nom faux → re-ask_name", adv["mode"] == "speak" and r3.step == "ask_name")
check("nom effacé", r3.state["name"] == "")

# --- registry : numéro faux ---
r4 = Registry()
r4.state["step"] = "confirm_phone"
r4.state["phone"] = "0622445103"
adv = r4.advance("Non")
check("numéro faux → re-ask_phone", adv["mode"] == "speak" and r4.step == "ask_phone")
check("numéro effacé", r4.state["phone"] == "")

# --- registry : adieu pendant enregistrement ---
r5 = Registry()
r5.state["step"] = "ask_name"
adv = r5.advance("Merci au revoir")
check("adieu → mode end", adv["mode"] == "end")

# --- registry : demande de conseiller → dossier d'abord puis clôture ---
r_h = Registry()
r_h.state["human_requested"] = True
r_h.state["step"] = "ask_name"
adv = r_h.advance("Non merci")
check("conseiller : refus du nom → clôture", adv["mode"] == "end")

r_h2 = Registry()
r_h2.state["human_requested"] = True
r_h2.state["step"] = "confirm_phone"
r_h2.state["name"] = "Saad"
r_h2.state["phone"] = "0661223344"
adv = r_h2.advance("Oui")
check("conseiller : numéro confirmé → done human_close",
      adv["mode"] == "done" and adv.get("human_close") is True)
check("conseiller : rassuré par rappel conseiller", "conseiller" in adv["directive"])

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

print("\n%d failures" % len(failures))
sys.exit(1 if failures else 0)
