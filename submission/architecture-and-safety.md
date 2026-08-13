# Architecture and safety note — OmniQuote

OmniQuote is a voice agent that interviews an Ontario driver, puts their answers on
screen for explicit confirmation, then reads twelve public rate sources concurrently and
presents the results with per-source evidence. This note describes who does what, where a
human is required, and how personal data is handled.

## Agent responsibilities

| Component | Responsibility |
| --- | --- |
| **Voice agent** (`backend/app/agents/agent.py`) | Runs the conversation (2–3 questions per turn, name first, 26 intake fields), exposes exactly one tool (`get_insurance_quote`), publishes UI state over the LiveKit data channel, and narrates results. Guarded against duplicate tool calls (`on_duplicate="reject"` plus an in-tool check), so a second call can never paint over a form being edited. |
| **Confirmation UI** (`frontend/src/components/QuoteExperience.jsx`) | Renders the editable form, per-field validation errors, streaming progress, the results carousel and comparison table. Replies to the agent over RPC. |
| **Canonical profile** (`backend/app/scrapers/profile.py`) | Normalises the confirmed form once into canonical tokens; each scraper translates tokens into its own site's wording via a declared `VALUE_MAP`. No scraper interprets raw user input. |
| **Orchestrator** (`backend/app/scrapers/registry.py`) | Fans out to all sources concurrently (shared Chromium, 4 pages at a time, 120s per-channel budget measured from work start). One source failing never affects the others. Flags exactly one recommendation — the cheapest **personalised** figure, never a cheaper population average. |
| **Scrapers** (12 modules under `backend/app/scrapers/`) | Enter the applicant's details into each site's own form where one exists, capture entry and result screenshots, and return a standard envelope: a real figure with declared personalisation basis, or `null` with a reason. There are no fallback or placeholder values anywhere in the pipeline. |
| **API** (`backend/app/main.py`, `routers/token.py`) | Mints a LiveKit token (fresh room per session, explicit agent dispatch) and serves screenshot evidence at `/artifacts`. |

## Human checkpoints

1. **Nothing touches an external site without explicit confirmation.** The tool's first
   act is to put all 24 answers on screen as an editable form and block. The user can
   correct any field, confirm, or cancel; a five-minute silence cancels. The form — not
   the model's transcription of speech — is the record of what the user authorised.
2. **The microphone is closed while the form is up and while sources run**, so ambient
   speech cannot alter answers or re-trigger the tool. A visible "tap to talk" control
   re-opens it; the agent acknowledges out loud when it is listening again.
3. **Every figure is labelled with its basis** ("Your full profile" … "Province-wide
   average") and generic figures are visually distinct, so a human sees what was matched
   before acting on a number. The spoken summary is instructed to make the same
   distinction and never to present an average as the user's rate.
4. **Screenshot evidence per source** — the result page scrolled to the exact figure, and
   the site's form showing the entered values — so a human can audit any number against
   the page it came from.
5. **The automation stops before lead generation.** No flow ever submits a name, email or
   phone number to any third-party site; funnels that require contact details to proceed
   are halted at that boundary and say so. CAPTCHA / bot-verification challenges are
   never bypassed; a blocked funnel is reported as blocked.

## Consent flow

1. The agent states its purpose at the start of the call: it will ask questions and check
   public rate sources.
2. Answers are collected conversationally; two fields (current premium, commute) are
   explicitly optional and refusable.
3. The confirmation form is displayed; **submitting it is the consent action** for using
   those values in the lookups. Cancel abandons the run and nothing is sent anywhere.
4. Results are presented with basis labels and disclaimers that these are benchmarks, not
   binding quotes, and that a real policy requires a real application through a licensed
   intermediary.

## Data storage

- **Collected:** first and last name plus the 24 quoting fields. The name exists for
  the conversation and the confirmation screen only -- it is deliberately absent from the
  canonical profile, so no scraper can enter it on a third-party site and it never
  appears in evidence artifacts or reports. The agent is instructed never to ask for a
  street address, licence number, email or phone, and no scraper needs them.
- **Application storage:** none. There is no active database (SQLAlchemy models exist as
  scaffolding but are not wired). The confirmed profile lives in process memory for the
  duration of the session.
- **Evidence artifacts:** screenshots and JSON result files are written to
  `backend/app/scrapers/screenshots/` (a named Docker volume in compose). They are
  **gitignored**, regenerated per run, and by design contain the values entered on each
  site — they are the proof of entry. They stay on the machine that produced them.
- **Voice pipeline:** audio, transcripts and session reports flow through LiveKit Cloud
  and its inference gateway (Deepgram STT, Gemini LLM, Cartesia TTS). Retention of that
  session data is governed by the LiveKit Cloud project's settings and the providers'
  terms — it is the one place data leaves the local machine.
- **Secrets:** LiveKit credentials in `backend/.env`, gitignored, injected at runtime.

## Redaction

- Reports and the market registry redact to **age band** and **forward sortation area**
  (first three postal characters); date of birth never appears in any artifact intended
  to leave the machine.
- The run report in this folder was generated from a **synthetic profile**; no real
  person's data exists anywhere in the repository.
- Names are excluded from every artifact and report at the source; the remaining
  identity fields (email, phone, street address, licence number) are **never collected**
  — the strongest form of redaction available.

## Deletion

- **Local evidence:** `rm backend/app/scrapers/screenshots/*` — or under Docker,
  `docker compose down && docker volume rm all-quote-agent-hackathon_artifacts`.
- **Session data at LiveKit Cloud:** delete through the LiveKit Cloud project console /
  retention settings; inference sub-processors are governed by their own terms.
- **The repository** contains no personal data to delete: the only profile committed
  anywhere is the synthetic test fixture.
