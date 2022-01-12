import wave

import urllib3.exceptions

from database import BadgesDB,Wakeword
from vad import is_voice
from model import BCResNet

import numpy as np
import torchaudio
import torch
import requests


import tempfile
import logging
import traceback

class BadgeAudioHandler:
    def __init__(self, db: BadgesDB, badge_id: str, config, model: BCResNet, device: torch.device):
        self.db = db
        self.id = badge_id
        self.config = config
        self.chunk_size = int((config.sample_rate * config.window_duration) // 10)

        self.detect_count = 0
        self.samples_since_vad = 0
        self.samples_since_activation = 0
        self.neg_samples_since_detect = 0


        self.vad_release_samples = config.sample_rate * config.vad_release
        self.activation_release_samples = config.sample_rate * 20

        self.recording = False

        self.window = np.zeros(int(config.window_duration*config.sample_rate),dtype=np.int16)

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

    def process_audiofragment(self, fragment: np.ndarray):
        i = 0
        fragment = fragment[0]
        while i < fragment.size:
            chunk = fragment[i:i + self.chunk_size]

            self._roll_window(chunk)

            chunk_len = len(chunk)

            self.samples_since_vad += chunk_len
            self.samples_since_activation += chunk_len

            if self.recording:
                self._append_rec_buffer(chunk)
                if self.samples_since_vad > self.vad_release_samples:
                    self._finish_recording()

            #logging.debug(f"Checking fragment at {i}, samples since VAD: {self.samples_since_vad}, release: {self.vad_release_samples}, recording: {self.recording}")
            if is_voice(self.window.tobytes(), self.config.sample_rate):
                #logging.debug("Found voice")
                self.samples_since_vad = 0

                result = self._infer_window()
                logging.info(f"Inferred to {result}")
                if result > self.config.certainty_thresh:
                    if not self.recording:
                        # if self.recording:
                        #     if self.samples_since_activation > self.activation_release_samples:
                        #         self._finish_recording()

                        self.detect_count += 1

                        if self.detect_count == 1:
                            self.recording_buffer = self.window.copy().tobytes()
                        elif self.detect_count == self.config.certainty_detects:
                            self._start_recording()
                        else:
                            self._append_rec_buffer(chunk)

                else:
                    if self.detect_count > 0:
                        if self.neg_samples_since_detect > self.config.certainty_window:
                            self.neg_samples_since_detect += 1
                        else:
                            self.neg_samples_since_detect = 0

            i += self.chunk_size

    def _roll_window(self, chunk):
        chunk_len = len(chunk)
        self.window = np.roll(self.window, -chunk_len, 0)
        self.window[-chunk_len:] = chunk

    def _append_rec_buffer(self,arr_slice):
        self.recording_buffer += arr_slice.tobytes()

    def _infer_window(self):
        torchdata = torch.from_numpy(self.window).float()
        spec = torch.log(self.spectrogrammer(torchdata) + 1e-8)
        spec -= spec.max()
        spec = spec.reshape(1, 1, *tuple(spec.shape))

        return torch.sigmoid(self.model(spec.to(self.device)))[0].item()

    def _start_recording(self):
        self.recording = True
        self.samples_since_activation = 0
        logging.info(f"Found a keyword on badge {self.id}, started recording...")

    def _finish_recording(self):
        duration = (len(self.recording_buffer)/2)/16000
        self.db.register_activation(self.id, Wakeword.Здравствуйте, duration)
        logging.info(
            f"Finished a recording on badge {self.id}, wakeword: {0}, duration of speech {duration}")
        # with open("/wav/test.wav","wb") as fp:

        with wave.open("/wav/test.wav","wb") as temp_wav_file:
            temp_wav_file.setnchannels(1)
            temp_wav_file.setsampwidth(2)
            temp_wav_file.setframerate(16000)
            temp_wav_file.writeframesraw(self.recording_buffer)

        with open("/wav/test.wav","rb") as fp:
            try:
                files = {
                    'file': fp
                }
                response = requests.post(self.config.sr_url, files=files,data={"item":self.id})
                logging.info(f"Sent audiofragment, got status: {response.status_code}")
            except urllib3.exceptions.HTTPError as e:
                logging.error(f"Can't send audiofragment to ASR with following exception: {e}")
                logging.error(f"Traceback:")
                logging.error(traceback.format_exc())

            finally:
                self._reset_recording()

    def _reset_recording(self):
        self.recording_buffer = b""
        self.recording = False

    def __del__(self):
        if len(self.recording_buffer) > 0:
            self._finish_recording()

