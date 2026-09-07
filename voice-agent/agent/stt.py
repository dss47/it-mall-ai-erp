import json
import subprocess

from .audio import resample, slin_to_wav
from .config import GROQ_KEY, GROQ_MODEL, GROQ_URL, SAMPLE_RATE
from .log import log


def groq_stt(audio8):
    wav16 = slin_to_wav(resample(audio8, SAMPLE_RATE, 16000), 16000)
    cmd = [
        "curl", "-s", "-m", "30", "-X", "POST", GROQ_URL,
        "-H", "Authorization: Bearer " + GROQ_KEY,
        "-F", "model=" + GROQ_MODEL,
        "-F", "language=fr",
        "-F", "prompt=IT Mall, Grandstream, Yealink, Cisco, Fortinet, Ubiquiti, Mikrotik, Dahua, Hikvision, Jabra, Plantronics, Polycom, VoIP, passerelle, routeur, switch, firewall, FXS, GSM, IPBX, UCM, RJ45",
        "-F", "response_format=json",
        "-F", "file=@-;filename=stt_in.wav;type=audio/wav",
    ]
    try:
        out = subprocess.run(cmd, input=wav16, capture_output=True, timeout=35).stdout
        d = json.loads(out)
        return (d.get("text") or "").strip()
    except json.JSONDecodeError as e:
        log("stt bad json: %r" % e)
        return ""
    except Exception as e:
        log("stt error: %r" % e)
        return ""
