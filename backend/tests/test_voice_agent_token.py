import os

from app.agents.agent import get_token


async def test_get_token_returns_livekit_credentials():
    os.environ["LIVEKIT_API_KEY"] = "test-key"
    os.environ["LIVEKIT_API_SECRET"] = "test-secret"
    os.environ["LIVEKIT_URL"] = "wss://example.livekit.cloud"

    payload = await get_token()

    assert "accessToken" in payload
    assert "url" in payload
    assert payload["url"] == "wss://example.livekit.cloud"
    assert payload["accessToken"]
