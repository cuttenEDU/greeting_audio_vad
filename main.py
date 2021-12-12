from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

import database

from database import BadgeNotFoundException

import logging


date_strftime_format = "%d-%b-%y %H:%M:%S"
message_format = "%(asctime)s | %(levelname)s | %(module)s.py: %(message)s"
logging.basicConfig(format=message_format, datefmt=date_strftime_format, level=logging.DEBUG)

db = database.BadgesDB("tables.db")
db.init_db()
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
logging.getLogger("fastapi").setLevel(logging.CRITICAL)

app = FastAPI()

class BadgeInfo(BaseModel):
    BadgeID:str = ""



@app.post("/activate",status_code=202)
async def activate_badge(badge:BadgeInfo):
    try:
        db.enable_badge(badge.BadgeID)
        logging.debug(f"Registered enabled state on badge {badge.BadgeID} in the database")
        return {"status":"success"}
    except BadgeNotFoundException:
        raise HTTPException(status_code=404, detail=f'Badge "{badge.BadgeID}" is not registered')

@app.get("/upload")
async def fragment_upload(badge:BadgeInfo,file:UploadFile):
    return {"message": f"Hello... you..."}