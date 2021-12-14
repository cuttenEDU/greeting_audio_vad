from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import torchaudio

from multiprocessing import Queue,Process
import queue
import logging

import database
from audio_handler import BadgeAudioHandler




date_strftime_format = "%d-%b-%y %H:%M:%S"
message_format = "%(asctime)s | %(levelname)s | %(module)s.py: %(message)s"
logging.basicConfig(format=message_format, datefmt=date_strftime_format, level=logging.DEBUG)
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
logging.getLogger("fastapi").setLevel(logging.CRITICAL)

db = database.BadgesDB("tables.db")
db.init_db()


app = FastAPI()

fragments_queue = Queue()

active_badges = {}

class BadgeInfo(BaseModel):
    BadgeID: str = ""

def process_badge_fragment(fragments_queue : Queue, active_badges: dict):
    while True:
        try:
            badge_id,fragment = fragments_queue.get()
        except queue.Empty:
            continue
        badge_handler = active_badges[badge_id]
        badge_handler.process_audiofragment(fragment)


p = Process(target=process_badge_fragment,args=(fragments_queue,active_badges))
p.start()

@app.post("/activate", status_code=202)
async def activate_badge(badge: BadgeInfo):
    try:
        db.enable_badge(badge.BadgeID)
        # TODO: config
        # TODO: model and device
        active_badges[badge.BadgeID] = BadgeAudioHandler(db,badge.BadgeID,None,None,None)
        logging.debug(f"Registered enabled state on badge {badge.BadgeID} in the database")
        return {"status": "success"}
    except database.BadgeNotFoundException:
        raise HTTPException(status_code=404, detail=f'Badge "{badge.BadgeID}" is not registered')


@app.get("/upload")
async def fragment_upload(badge: BadgeInfo, file: UploadFile = File(...)):
    wav,sr = torchaudio.load(file).numpy()
    assert sr == 16000
    fragments_queue.put((badge.BadgeID,wav))
