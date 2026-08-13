#!/usr/bin/env bash
# Production entrypoint: API and agent worker in one container.
#
# Locally, compose runs them as two services sharing a volume. Render can't
# share a persistent disk between services, and the agent writes screenshots
# the API serves -- so in production both processes live in one container with
# the disk mounted at the screenshots path. This also keeps the "exactly one
# agent" invariant for free: one container, one worker registration.
#
# If either process dies, exit so the platform restarts the whole container --
# a half-alive pair (API up, agent gone) looks like the agent silently
# ignoring calls, which is the exact failure mode compose was built to end.
set -euo pipefail

PORT="${PORT:-8001}"

mkdir -p /app/app/scrapers/screenshots

uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
API_PID=$!

python app/agents/agent.py start &
AGENT_PID=$!

trap 'kill "$API_PID" "$AGENT_PID" 2>/dev/null' TERM INT

# Wait for whichever exits first, then take the other down with us.
wait -n "$API_PID" "$AGENT_PID"
STATUS=$?
kill "$API_PID" "$AGENT_PID" 2>/dev/null
exit "$STATUS"
