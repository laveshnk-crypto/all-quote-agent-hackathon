import os
from pathlib import Path
from dotenv import load_dotenv

# Explicitly load backend/.env relative to main.py
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import token

app = FastAPI(title="Ontario Auto Insurance Agent API")

# Setup CORS to allow your frontend on port 5174
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://10.0.0.234:5173",
        "http://10.0.0.234:5174",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(token.router)

@app.get("/")
def read_root():
    return {"status": "online"}