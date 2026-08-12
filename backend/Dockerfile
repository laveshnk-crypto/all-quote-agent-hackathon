# Python 3.11 to match the interpreter this project was developed and tested on.
# The Playwright base images track Ubuntu's system Python (3.10 on jammy), and
# livekit-agents is sensitive enough that matching the tested runtime is worth
# the extra build step for browsers.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Requirements first so the dependency layer caches across code edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --with-deps pulls the system libraries Chromium needs on slim images.
# Only chromium: the scrapers never touch firefox or webkit.
RUN playwright install --with-deps chromium

COPY . .

# Screenshots are written by the agent and served by the API, so the directory
# is a shared volume in compose. Create it here so either service can start first.
RUN mkdir -p /app/app/scrapers/screenshots

EXPOSE 8001

# Overridden per service in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
