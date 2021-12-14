from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import torchaudio
import torch

from multiprocessing import Queue
import logging

import database
from audio_handler import BadgeAudioHandler
from model import BCResNet
from config import Config


def main(fragments_queue: Queue, active_badges: dict):

    # Config init
    config_path = "config.yml"

    config = Config(config_path)
    print(f"Config loaded from path: {config_path}")
    print(config)

    # Logging init
    date_strftime_format = "%d-%b-%y %H:%M:%S"
    message_format = "%(asctime)s | %(levelname)s | %(module)s.py: %(message)s"
    logging.basicConfig(format=message_format, datefmt=date_strftime_format, level=logging.DEBUG)
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    logging.getLogger("fastapi").setLevel(logging.CRITICAL)

    # DB Init
    db = database.BadgesDB("tables.db")
    db.init_db()

    # NeuralNet init
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    model = BCResNet(2).to(device)
    model.eval()
    state_dict = torch.load(config.model_path, map_location=device)
    model.load_state_dict(state_dict)

    # FastAPI
    app = FastAPI()

    class BadgeInfo(BaseModel):
        BadgeID: str = ""

    @app.post("/activate", status_code=202)
    async def activate_badge(badge: BadgeInfo):
        try:
            db.enable_badge(badge.BadgeID)
            if badge.BadgeID not in active_badges:
                active_badges[badge.BadgeID] = BadgeAudioHandler(db, badge.BadgeID, config, model, device)
            logging.debug(f"Registered enabled state on badge {badge.BadgeID} in the database")
            return {"status": "success"}
        except database.BadgeNotFoundException:
            raise HTTPException(status_code=404, detail=f'Badge "{badge.BadgeID}" is not registered')

    @app.get("/upload")
    async def fragment_upload(badge: BadgeInfo, file: UploadFile = File(...)):
        wav, sr = torchaudio.load(file).numpy()
        assert sr == 16000
        fragments_queue.put((badge.BadgeID, wav))
