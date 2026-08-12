import os
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants, RoomConfiguration, RoomAgentDispatch

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

router = APIRouter(prefix="/api", tags=["livekit"])


def build_livekit_token():
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")
    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "assistant-1-ge-1")

    if not api_key or not api_secret or not livekit_url:
        raise HTTPException(
            status_code=500,
            detail="LiveKit environment variables missing in backend .env file",
        )

    # A fresh room per session. Agent dispatch declared in RoomConfiguration only
    # fires when the room is created, so reusing one fixed room name means the
    # agent is dispatched to the first caller and nobody after that -- the room
    # already exists, so joining it never triggers a new dispatch.
    room_name = f"quote-{uuid.uuid4().hex[:12]}"
    identity = f"user-{uuid.uuid4().hex[:8]}"

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("Web User")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
        .with_room_config(
            RoomConfiguration(
                agents=[RoomAgentDispatch(agent_name=agent_name)]
            )
        )
    )

    return {
        "accessToken": token.to_jwt(),
        "url": livekit_url,
        "room": room_name,
    }


@router.get("/token")
async def get_livekit_token():
    try:
        return build_livekit_token()
    except Exception as exc:
        print("[TOKEN EXCEPTION] Error generating LiveKit token:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc