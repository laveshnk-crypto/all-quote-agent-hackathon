from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
import app.models  # Ensures models are imported so Base knows about them

app = FastAPI(title="Ontario Auto Insurance Agent API")

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