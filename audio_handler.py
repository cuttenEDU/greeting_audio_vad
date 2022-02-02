import wave

import urllib3.exceptions

from database import BadgesDB,Wakeword
from vad import OnnxVADRuntime
from model import BCResNet

import numpy as np
import torchaudio
import torch
import requests

import tempfile
import logging
import traceback
import os

from datetime import datetime

class BadgeAudioHandler:
    def __init__(self, db: BadgesDB, badge_id: str, config, model: BCResNet, device: torch.device):
        self.db = db
        self.id = badge_id
        self.config = config
        self.chunk_size = int((config.sample_rate * config.window_duration) // 7)

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

        self.vad = OnnxVADRuntime(config.vad_model_path)

        self._reset_vad_state()

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

    def process_audiofragment(self, fragment: np.ndarray,filename:str):
        logging.info(f"Starting processing fragment {filename} on badge {self.id}, duration {round(fragment.size/self.config.sample_rate,2)}")

        vad_log_dirty = True
        vad_log_start = -1

        fragment_start_time = self.parse_time(filename)

        try:
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
                        self._finish_recording(fragment_start_time + (i//self.config.sample_rate))

                vad_res, self._h,self._c = self.vad(chunk.astype("float32"),self._h,self._c)

                #logging.debug(f"Checking fragment at {i}, samples since VAD: {self.samples_since_vad}, release: {self.vad_release_samples}, recording: {self.recording}")
                if vad_res > self.config.vad_threshold:

                    if vad_log_dirty:
                        #logging.info(f"Found voice on time {i/self.config.sample_rate}")
                        vad_log_start = i/self.config.sample_rate
                        vad_log_dirty = False

                    self.samples_since_vad = 0

                    result = self._infer_window()
                    # logging.info(f"Inferred to {result}")
                    if result > self.config.certainty_thresh:
                        if not self.recording:

                            logging.info(f"Probable greeting? result {result} on time {i/self.config.sample_rate}")
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
                else:
                    if not vad_log_dirty:
                        logging.info(f"Voice fragment from {vad_log_start} to {i/self.config.sample_rate}")
                    vad_log_dirty = True
                i += self.chunk_size
            logging.info(f"Processed fragment on badge {self.id}")
        except Exception as e:
            logging.error(f"Can't process audiofragment on badge {self.id}, exception:")
            logging.error(traceback.format_exc())


    def _reset_vad_state(self):
        self._h = np.zeros((2, 1, 64)).astype('float32')
        self._c = np.zeros((2, 1, 64)).astype('float32')

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

    def _finish_recording(self,start_time):
        duration = (len(self.recording_buffer)/2)/16000
        self.db.register_activation(self.id, Wakeword.Здравствуйте, duration)
        logging.info(
            f"Finished a recording on badge {self.id}, wakeword: {0}, duration of speech: {duration}, timestamp: {start_time}")


        with wave.open(f"/wav/{self.id}.wav","wb") as temp_wav_file:
            temp_wav_file.setnchannels(1)
            temp_wav_file.setsampwidth(2)
            temp_wav_file.setframerate(16000)
            temp_wav_file.writeframesraw(self.recording_buffer)

        with open(f"/wav/{self.id}.wav","rb") as fp:
            try:
                files = {
                    'file': fp
                }
                response = requests.post(self.config.sr_url, files=files,data={"badge_id":self.id,"time":start_time})
                logging.info(f"Sent audiofragment, got status: {response.status_code}")
            except urllib3.exceptions.HTTPError as e:
                logging.error(f"Can't send audiofragment to ASR with following exception: {e}")
                logging.error(f"Traceback:")
                logging.error(traceback.format_exc())

        self._reset_recording()

        os.remove(f"/wav/{self.id}.wav")

    def _reset_recording(self):
        self.recording_buffer = b""
        self.recording = False
        self.detect_count = 0

    def __del__(self):
        if len(self.recording_buffer) > 0:
            self._finish_recording(datetime.now().timestamp())

    @staticmethod
    def parse_time(recording_name: str):
        datetime_str = recording_name.replace(".WAV","")
        try:
            return int(datetime.strptime(datetime_str, '%Y%m%d%H%M%S').timestamp())
        except ValueError:
            return int(datetime.now().timestamp())
