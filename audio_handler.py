from database import BadgesDB,Wakeword
from vad import is_voice
from model import BCResNet

import numpy as np
import torchaudio
import torch


class BadgeAudioHandler:
    def __init__(self, db: BadgesDB, badge_id: str, config, model: BCResNet, device: torch.device):
        self.db = db
        self.id = badge_id
        self.config = config
        self.chunk_size = int((config.sample_rate * config.window_duration) // 5)

        self.detect_count = 0
        self.samples_since_vad = 0
        self.neg_samples_since_detect = 0

        self.vad_release_samples = config.sample_rate * config.vad_release

        self.recording = False

        self.window = np.zeros(config.window_duration,dtype=np.int16)

        self.recording_buffer = b""

        self.model = model
        self.device = device
        self.spectrogrammer = torch.nn.Sequential(
            torchaudio.transforms.MelSpectrogram(
                sample_rate=config.sample_rate,
                n_fft=config.n_fft,
                win_length=config.win_length,
                hop_length=config.hop_length,
                center=True,
                pad_mode="reflect",
                power=2.0,
                norm='slaney',
                onesided=True,
                n_mels=config.n_mels,
                mel_scale="htk",
            )

        )

    def process_audiofragment(self, fragment: bytes):
        i = 0
        while i < len(fragment):
            chunk = fragment[i:i + self.chunk_size]

            self._roll_window(chunk)

            self.samples_since_vad += len(chunk)

            if self.recording:
                self._append_rec_buffer(chunk)
                if self.samples_since_vad > self.vad_release_samples:
                    self._finish_recording()

            if is_voice(self.window.tobytes(), self.config.sample_rate):

                self.samples_since_vad = 0

                result = self._infer_window()

                if result > self.config.certainty_thresh:

                    if self.recording:
                        self._finish_recording()

                    self.detect_count += 1

                    if self.detect_count == 1:
                        self.recording_buffer = self.window.copy().tobytes()
                    elif self.detect_count == self.config.certainty_detects:
                        self.recording = True

                else:
                    if self.detect_count > 0:
                        if self.neg_samples_since_detect > self.config.certainty_window:
                            self.neg_samples_since_detect += 1
                        else:
                            self.neg_samples_since_detect = 0

            i += chunk

    def _roll_window(self, chunk):
        chunk_len = len(chunk)
        self.window = np.roll(self.window, -chunk_len, 0)
        self.window[-chunk_len:] = chunk

    def _append_rec_buffer(self,arr_slice):
        self.recording_buffer += arr_slice.to_bytes()

    def _infer_window(self):
        torchdata = torch.from_numpy(self.window).float()
        spec = torch.log(self.spectrogrammer(torchdata) + 1e-8)

        spec = spec.reshape(1, 1, *tuple(spec.shape))

        return torch.sigmoid(self.model(spec.to(self.device)))[0].item()

    def _finish_recording(self):
        # TODO: recording transmission
        self.recording = False
        self.recording_buffer = b""
        duration = (len(self.recording_buffer)/2)/16000
        self.db.register_activation(self.id,Wakeword.Здравствуйте,duration)



    def __del__(self):
        if len(self.recording_buffer) > 0:
            self._finish_recording()

