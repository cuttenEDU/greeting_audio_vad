import numpy as np
import torch
import torchaudio
import onnxruntime

from singleton import Singleton

class OnnxVADRuntime(Singleton):
    _instance = None

    def __init__(self, model_path = "weights/vad_onnx/silero_vad.onnx"):
        self.session = onnxruntime.InferenceSession(model_path)
        self.session.intra_op_num_threads = 1
        self.session.inter_op_num_threads = 2

    def __call__(self, x, h, c):
        if x.ndim == 1:
            x = np.expand_dims(x,0)
        if x.ndim > 2:
            raise ValueError(f"Too many dimensions for input audio chunk {x.dim()}")

        if x.shape[0] > 1:
            raise ValueError("Onnx model does not support batching")

        if h.shape != (2, 1, 64):
            raise ValueError("Wrong shape for H state array")

        if c.shape != (2, 1, 64):
            raise ValueError("Wrong shape for C state array")

        ort_inputs = {'input': x, 'h0': h, 'c0': c}
        ort_outs = self.session.run(None, ort_inputs)
        out, h, c = ort_outs

        out = torch.tensor(out).squeeze(2)[:, 1].item()  # make output type match JIT analog

        return out, h, c
