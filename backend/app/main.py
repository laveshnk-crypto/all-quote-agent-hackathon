from typing import Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.database import engine, Base
import app.models  # Ensures models are imported so Base knows about them
from app.scrapers.fsra_benchmark import FSRABenchmarkScraper

app = FastAPI(title="Ontario Auto Insurance Agent API")


class FSRARequest(BaseModel):
    age: int
    gender: str
    marital_status: str
    postal_code: str
    annual_mileage: int
    vehicle_model_year: int
    vehicle_make: str
    years_licensed: int
    years_claim_free: int
    multi_vehicle_discount: str = "Not Applied"
    multi_policy_discount: str = "Not Applied"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Adjust this to your frontend's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Auto-create missing tables in PostgreSQL
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
def read_root():
    return {"status": "online", "system": "Ontario Auto Insurance Agent API"}