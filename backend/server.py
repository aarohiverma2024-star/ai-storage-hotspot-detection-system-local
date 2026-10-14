"""Predictive Storage Guardian — FastAPI entrypoint."""
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import os
import logging

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from routers import router as v1_router
from state import STATE

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger("psg")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Predictive Storage Guardian API", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/api/")
async def root():
    return {"service": "Predictive Storage Guardian", "docs": "/docs", "api": "/api/v1"}


@app.on_event("shutdown")
async def shutdown():
    STATE.stop()
    client.close()
