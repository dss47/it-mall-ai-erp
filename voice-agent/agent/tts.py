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
    # Pronounce IT Mall as Aïti Mall in French TTS
    t = re.sub(r"\bIT\s*Mall\b", "Aïti Mall", text, flags=re.IGNORECASE)
    t = re.sub(r"\bIT\b", "Aïti", t)
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
