import io
import wave
import numpy as np

from .config import SAMPLE_RATE


def resample(x, fs_in, fs_out):
    if fs_in == fs_out:
        return x
    if len(x) == 0:
        return np.asarray(x, dtype=np.int16)
    n_in = len(x)
    n_out = max(1, int(round(n_in * float(fs_out) / float(fs_in))))
    orig_indices = np.linspace(0, n_in - 1, num=n_in)
    target_indices = np.linspace(0, n_in - 1, num=n_out)
    y = np.interp(target_indices, orig_indices, x.astype(np.float32))
    return np.clip(y, -32768, 32767).astype(np.int16)


def slin_to_wav(pcm, rate):
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(pcm.tobytes())
    w.close()
    return buf.getvalue()


def wav_to_slin(wav_bytes):
    w = wave.open(io.BytesIO(wav_bytes))
    rate = w.getframerate()
    n = w.getnframes()
    raw = w.readframes(n)
    w.close()
    x = np.frombuffer(raw, dtype=np.int16)
    if rate != SAMPLE_RATE:
        x = resample(x, rate, SAMPLE_RATE)
    return x


def rms(frame):
    x = frame.astype(np.float32)
    return float(np.sqrt(np.mean(x * x)))
