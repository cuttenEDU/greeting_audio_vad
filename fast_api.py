from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import uvicorn
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
    # logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    # logging.getLogger("fastapi").setLevel(logging.CRITICAL)

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

    @app.post("/enable", status_code=201)
    async def enable_badge(badge: BadgeInfo):
        try:
            db.enable_badge(badge.BadgeID)
            if badge.BadgeID not in active_badges:
                active_badges[badge.BadgeID] = BadgeAudioHandler(db, badge.BadgeID, config, model, device)
            logging.debug(f"Registered enabled state on badge {badge.BadgeID} in the database")
            return {"status": "success"}
        except database.BadgeNotFoundException:
            raise HTTPException(status_code=404, detail=f'Badge "{badge.BadgeID}" is not registered')
        except database.BadgeAlreadyEnabled:
            raise HTTPException(status_code=304, detail=f'Badge "{badge.BadgeID} is already enabled')

    @app.post("/disable", status_code=201)
    async def disable_badge(badge: BadgeInfo):
        try:
            db.disable_badge(badge.BadgeID)
            if badge.BadgeID in active_badges:
                del active_badges[badge.BadgeID]
            logging.debug(f"Registered disabled state on badge {badge.BadgeID} in the database")
            return {"status": "success"}
        except database.BadgeNotFoundException:
            raise HTTPException(status_code=404, detail=f'Badge "{badge.BadgeID}" is not registered')
        except database.BadgeAlreadyDisabled:
            raise HTTPException(status_code=304, detail=f'Badge "{badge.BadgeID} is already disabled')

    @app.post("/upload", status_code=202)
    async def fragment_upload(BadgeID: str = Form(...), upload_file: UploadFile = File(...)):
        if db.badge_exists(BadgeID):
            file = upload_file.file
            wav, sr = torchaudio.load(file)
            wav = wav.numpy()
            assert sr == 16000
            logging.debug(f"Recieved fragment from badge {BadgeID}, duration: {round(wav.size/sr,2)}")
            fragments_queue.put((BadgeID, wav))
        else:
            raise HTTPException(status_code=404, detail=f'Badge "{BadgeID}" is not registered')

    @app.get("/ping")
    async def pong():
        return "pong"

    uvicorn.run(app, host="127.0.0.1",port=8000,log_level="info")
