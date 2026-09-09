import json
import re
import subprocess

from .audio import wav_to_slin
from .config import TTS_LENGTH_SCALE, TTS_URL
from .log import log


def ensure_tts():
    try:
        subprocess.run(["/opt/voice-agent/piper/start.sh"], timeout=15)
    except Exception:
        pass


def _phonetic_fixes(text):
    if not text:
        return text
    t = text
    # 1. Nom de l'entreprise
    t = re.sub(r"\bIT\s*Mall\b", "Aïti Mall", t, flags=re.IGNORECASE)
    t = re.sub(r"\bIT\b", "Aïti", t)
    
    # 2. Monnaies (DH / MAD) -> dirhams
    t = re.sub(r"(\b1(?:\.0+)?)\s*(?:DH|DHS|MAD)\b", r"\1 dirham", t, flags=re.IGNORECASE)
    t = re.sub(r"(\d+)\s*(?:DH|DHS|MAD)\b", r"\1 dirhams", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:DH|DHS|MAD)\b", "dirhams", t, flags=re.IGNORECASE)
    
    # 3. Unités de mesure & Capacités techniques
    t = re.sub(r"\b(\d+)\s*MP\b", r"\1 mégapixels", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d+)\s*To\b", r"\1 téraoctets", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d+)\s*Go\b", r"\1 gigaoctets", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d+)\s*U\b", r"\1 U", t)  # Baie 42U
    
    # 4. Sigles réseaux & télécoms
    t = re.sub(r"\bVoIP\b", "Vo-IP", t, flags=re.IGNORECASE)
    t = re.sub(r"\bPoE\b", "P-O-E", t, flags=re.IGNORECASE)
    t = re.sub(r"\bPTZ\b", "P-T-Z", t, flags=re.IGNORECASE)
    t = re.sub(r"\bNVR\b", "N-V-R", t, flags=re.IGNORECASE)
    t = re.sub(r"\bDVR\b", "D-V-R", t, flags=re.IGNORECASE)
    t = re.sub(r"\bIP\b", "I-P", t)
    t = re.sub(r"\bAPC\b", "A-P-C", t)
    t = re.sub(r"\bWiFi\b|\bWifi\b", "Ouifi", t, flags=re.IGNORECASE)
    t = re.sub(r"\bUniFi\b|\bUnifi\b", "Younifaï", t, flags=re.IGNORECASE)
    t = re.sub(r"\bMikroTik\b|\bMikrotik\b", "Mikrotik", t, flags=re.IGNORECASE)
    t = re.sub(r"\bYealink\b", "Yialink", t, flags=re.IGNORECASE)
    t = re.sub(r"\bJabra\b", "Djabrah", t, flags=re.IGNORECASE)
    
    return t


def piper_tts(text):
    text = _phonetic_fixes(text)
    data = json.dumps({"text": text, "length_scale": TTS_LENGTH_SCALE}).encode()
    try:
        out = subprocess.run(
            ["curl", "-s", "-m", "20", "-X", "POST", TTS_URL,
             "-H", "Content-Type: application/json", "-d", data, "-o", "-"],
            capture_output=True, timeout=25, check=True,
        ).stdout
        if len(out) < 100:
            return None
        return wav_to_slin(out)
    except Exception as e:
        log("tts error: %r" % e)
        return None
