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
# no trailing slash). Unset means local development, where Vite hops to the next
# free port when 5173 is taken -- so dev accepts any localhost port rather than
# pinning a list that goes stale the moment a second dev server is running.
_origins_env = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=(
        None if ALLOWED_ORIGINS else r"http://(localhost|127\.0\.0\.1)(:\d+)?"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(token.router)
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACT_DIR)), name="artifacts")

@app.get("/")
def read_root():
    return {"status": "online"}