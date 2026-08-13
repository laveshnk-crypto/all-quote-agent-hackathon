# Pre-existing materials and third-party licences — OmniQuote

## Pre-existing materials

- **Vite React starter template** (MIT) — the frontend began from the standard
  `create-vite` React scaffold; its residual assets (`vite.svg`, `react.svg`) remain in
  `frontend/src/assets/`. `hero.png` and `bot.svg` are project assets not currently used
  by the app.
- **Lucide icon** — the bot mark (`lucide--bot.svg`) is from the Lucide icon set, ISC
  licence.
- **Development tooling disclosure** — the codebase was built with substantial use of
  Claude Code (Anthropic) as an AI pair-programming tool during the hackathon.
- No other pre-existing application code was incorporated beyond the dependencies listed
  below.

## Backend dependencies (Python, `backend/requirements.txt`)

| Package | Version | Licence |
| --- | --- | --- |
| FastAPI | 0.111.0 | MIT |
| Uvicorn | 0.30.1 | BSD-3-Clause |
| SQLAlchemy | 2.0.31 | MIT |
| asyncpg | 0.29.0 | Apache-2.0 |
| Pydantic / pydantic-settings | 2.7.4 / 2.3.4 | MIT |
| Playwright (Python) | 1.45.0 | Apache-2.0 — downloads and drives Chromium (BSD-3-Clause and bundled component licences) |
| pandas | 2.2.2 | BSD-3-Clause |
| HTTPX | 0.27.0 | BSD-3-Clause |
| python-dotenv | 1.0.1 | BSD-3-Clause |
| livekit-agents (+ openai/deepgram/cartesia extras) | 1.6.9 | Apache-2.0 |
| livekit-plugins-ai-coustics | 0.3.0 | Apache-2.0 (plugin); the ai-coustics enhancement service itself is commercial |

## Frontend dependencies (`frontend/package.json`)

| Package | Licence |
| --- | --- |
| React / React DOM 19 | MIT |
| livekit-client | Apache-2.0 |
| @livekit/components-react, @livekit/components-styles | Apache-2.0 |
| Vite, @vitejs/plugin-react | MIT |
| ESLint and plugins, globals, @types/* | MIT |

Fonts are system-stack only; no webfonts are bundled or fetched.

## Container images (`docker-compose.yml`)

| Image | Licensing |
| --- | --- |
| `python:3.11-slim` | Python (PSF-2.0) on Debian (various OSS licences) |
| `node:22-alpine` | Node.js (MIT-style) on Alpine (MIT/various) |
| `nginx:1.27-alpine` | nginx (BSD-2-Clause) |

## Models and hosted services (commercial API terms, via LiveKit Cloud)

No model weights are shipped in this repository. At call time the LiveKit Cloud
inference gateway invokes:

- **Deepgram `nova-3`** — speech-to-text
- **Google `gemini-3-flash`** — conversation and tool-calling LLM
- **Cartesia `sonic-3`** — text-to-speech
- **LiveKit turn detector / VAD** and **ai-coustics QUAIL** noise enhancement
- **LiveKit Cloud** itself for rooms, dispatch and session transport

Each is used under its provider's commercial terms through the operator's LiveKit
Cloud account; no provider content is redistributed here.

## Datasets and third-party content

- **No third-party datasets are shipped.** The only profile in the repo is a synthetic
  test fixture.
- **Rate figures are read at runtime** from twelve public websites (listed with URLs in
  `market-registry.json`). Copyright in that content remains with its publishers,
  including the FSRA Rate Ranger (an Ontario regulator's public tool). Figures are used
  transiently for comparison with screenshot evidence; no scraped corpus is stored in or
  redistributed with this repository, and several sites' terms would require permission
  for commercial use (see `known-limitations.md`).
