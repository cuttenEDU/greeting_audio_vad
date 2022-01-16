from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import uvicorn
import torchaudio
import torch

from multiprocessing import Queue
import logging
import os
import time

import database
from audio_handler import BadgeAudioHandler
from model import BCResNet
from config import Config


def init_model(config: Config) -> (BCResNet, torch.device):
    # device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    device = torch.device("cpu")
    model = BCResNet(2).to(device)
    model.eval()
    state_dict = torch.load(config.model_path, map_location=device)
    model.load_state_dict(state_dict)
    return model, device


def fill_active_badges(active_badges: dict, config: Config, db: database.BadgesDB, model: BCResNet,
                       device: torch.device):
    for badge_id in db.get_active_badges():
        active_badges[badge_id] = BadgeAudioHandler(db, badge_id, config, model, device)


def init_config():
    # Config init
    config_path = os.environ.get("CONFIG")
    if config_path:
        config = Config(config_path)
        logging.info(f"Config loaded: {config_path}")
        logging.info(config)
        return config
    raise ValueError("No config environment variable!")


def main(fragments_queue: Queue, active_badges: dict):
    config = init_config()
    db = database.init_db(config)
    model, device = init_model(config)
    fill_active_badges(active_badges, config, db, model, device)

    logging.debug(f"Active badges: {list(active_badges.keys())}")
    # FastAPI
    app = FastAPI()

    class BadgeInfo(BaseModel):
        BadgeID: str = ""

    class FragmentInfo(BaseModel):
        filename: str
        duration: str
        size: int

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
            wav, sr = torchaudio.load(file, normalize=False)
            wav = wav.numpy()
            assert sr == config.sample_rate
            logging.info(f"Recieved fragment {upload_file.filename} from badge {BadgeID}, duration: {round(wav.size / sr, 2)}")
            fragments_queue.put((BadgeID, wav, upload_file.filename))
        else:
            raise HTTPException(status_code=404, detail=f'Badge "{BadgeID}" is not registered')

    @app.get("/ping")
    async def pong():
        return "pong"

    @app.get("/announce_upload", status_code=200)
    async def announce_upload(fragment_info: FragmentInfo):
        logging.info(
            f"Got upload announcement of recording fragment {fragment_info.filename}, size: {fragment_info.size}, "
            f"duration: {fragment_info.duration}")

    uvicorn.run(app, host="0.0.0.0", port=8020, log_level="info")
