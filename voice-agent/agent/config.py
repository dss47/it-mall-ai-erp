import os

BASE = "/opt/voice-agent"
DB_ENV = os.path.join(BASE, "db.env")
DB_DIR = os.path.join(BASE, "db")
DB_PATH = os.path.join(DB_DIR, "agent.db")

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8300

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"

GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-3.5-flash-lite:generateContent")
GEMINI_MAX_TOKENS = 400

TTS_URL = "http://127.0.0.1:5000/synthesize"
TTS_LENGTH_SCALE = 1.08

VAD_MODEL = os.path.join(BASE, "vad", "silero_vad.onnx")
SESS_DIR = os.path.join(BASE, "sessions")
LOG = "/var/log/asterisk/ai_agent.log"

SAMPLE_RATE = 8000
VAD_FRAME = 256               # 32 ms at 8 kHz
SPEECH_PROB = 0.6             # Silero speech threshold
ENERGY_MIN = 200              # int16 RMS floor
MIN_UTTERANCE_S = 0.5
SILENCE_HANGUP_S = 30.0
MAX_SPEECH_TURNS = 30

BARG_PROB = 0.55
BARG_IN_FRAMES = 4            # 128 ms sustained speech cuts TTS (barge-in)
POST_TTS_HOLD = 1.2           # silence après TTS avant de ré-écouter

# Adaptive turn-taking: patience = silence needed to close a turn.
EXPECTATIONS = {
    "free":         {"patience": 0.9, "max_utter": 10.0},
    "yes_no":       {"patience": 0.6, "max_utter": 5.0},
    "short_free":   {"patience": 0.7, "max_utter": 8.0},
    "recitation":   {"patience": 2.5, "max_utter": 30.0},
}
RECITATION_BUDGET_S = 40.0

DB_PASS = ""


def _load_env():
    env = {}
    try:
        with open(DB_ENV) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


_ENV = _load_env()
GROQ_KEY = _ENV.get("GROQ_KEY", "")
GEMINI_KEY = _ENV.get("GEMINI_KEY", "")
DB_PASS = _ENV.get("DB_PASS", "")
ODOO_DB = _ENV.get("ODOO_DB", "it_mall_db")
ODOO_USER = _ENV.get("ODOO_USER", "odoo")
ODOO_PASS = _ENV.get("ODOO_PASS", "odoo")
ODOO_HOST = _ENV.get("ODOO_HOST", "localhost")
ODOO_PORT = int(_ENV.get("ODOO_PORT", "5432"))

