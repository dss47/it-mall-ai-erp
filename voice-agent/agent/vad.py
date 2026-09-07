import numpy as np
import onnxruntime as ort

from .config import VAD_MODEL


class SileroVAD:
    def __init__(self, model_path=VAD_MODEL):
        self.sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros(32, dtype=np.float32)

    def prob(self, frame):
        x = np.concatenate([self.context, frame.astype(np.float32) / 32768.0])
        self.context = x[-32:]
        x = x[np.newaxis, :]
        sr = np.array([8000], dtype=np.int64)
        out, st = self.sess.run(None, {"input": x, "state": self.state, "sr": sr})
        self.state = st
        return float(out[0][0])
