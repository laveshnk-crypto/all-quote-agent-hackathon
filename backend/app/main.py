import os
from pathlib import Path
from dotenv import load_dotenv

# Explicitly load backend/.env relative to main.py
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import token

app = FastAPI(title="Ontario Auto Insurance Agent API")

# Screenshot proof for each quote channel. The scrapers write here and hand the
# UI a /artifacts/<file> URL so every figure can be checked against its source.
ARTIFACT_DIR = Path(__file__).resolve().parent / "scrapers" / "screenshots"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# ALLOWED_ORIGINS is a comma-separated list of frontend origins (scheme + host,
# no trailing slash). Unset means local development against the Vite dev server.
_default_origins = "http://localhost:5173,http://localhost:5174"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(token.router)
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACT_DIR)), name="artifacts")

@app.get("/")
def read_root():
    return {"status": "online"}