# OmniQuote

A voice agent that interviews an Ontario driver, puts their answers on screen to
confirm, then prices them against **ten public rate sources at once** — entering their
details into each site's own form and screenshotting the page every figure came from.

Ask it for a quote out loud. About thirty seconds later you have ten numbers, the
cheapest highlighted, and a screenshot proving each one.

---

## How a call goes

1. **The agent asks.** Two or three questions at a time — date of birth and gender, then
   postal code and city, then the car, and so on. Twenty-four fields, about ten questions.
2. **The details go on screen.** An editable form appears and the microphone closes; the
   form *is* the confirmation. Correct anything, hit confirm. A "tap to talk" button is
   there if you'd rather say something.
3. **Ten sources run at once.** Each one gets your details typed into its own quote form,
   and cards fill in as they land. The agent stays silent through this.
4. **The agent talks you through it.** Best rate first, how closely it actually matches
   you, and the spread across all ten. Swipe the cards, or open the table to compare them
   side by side with the cheapest in gold and a screenshot behind every row.

---

## Quick start

```bash
cp backend/.env.example backend/.env   # add your LiveKit keys
docker compose up --build
```

Open <http://localhost:5173> and press the bot.

| Service | Port | What it is |
| --- | --- | --- |
| `web` | 5173 | React UI, built and served by nginx |
| `api` | 8001 | LiveKit token endpoint, and `/artifacts` for screenshot proof |
| `agent` | – | LiveKit worker: joins the room, runs the ten scrapers |

### Running it without Docker

Three processes, three terminals. All of them have to be up for a call to work.

```bash
# 1. API
cd backend && uvicorn app.main:app --port 8001

# 2. Agent worker
cd backend && python app/agents/agent.py dev

# 3. UI
cd frontend && npm run dev
```

> **Restart the worker after any backend edit.** LiveKit removed in-process
> auto-reload from the Python CLI, so `dev` does *not* pick up your changes — you will
> be testing old code without knowing it. And kill strays before starting:
> `pkill -9 -f "agent.py dev"`. Several workers registering under the same
> `agent_name` compete for job dispatches, so a call can land on a stale one and
> nothing answers. This is the single most common way to lose an hour on this project.

---

## The ten sources

| Source | Type | Needs |
| --- | --- | --- |
| FSRA Regulator Rate Ranger | Regulatory | age, gender, marital status, postal code, mileage, vehicle year + make, years licensed, years claim-free |
| LowestRates.ca | Aggregator | city, age |
| Rates.ca | Aggregator | city |
| Ratehub.ca | Aggregator | city |
| InsuranceHotline.com | Broker | – |
| MyChoice.ca Calculator | Aggregator | age, vehicle year + make, postal code, current premium |
| MyChoice.ca Rate Index | Aggregator | – |
| HelloSafe.ca | Aggregator | – |
| Surex.com | Broker | age |
| isure.ca | Broker | – |

A source that lacks what it needs returns `REJECTED` with a reason. It never substitutes
a placeholder — a missing answer must not become a confident-looking quote for somebody
else's profile.

**Rates.ca's live funnel is not reachable.** Entering a postal code on rates.ca and
pressing "Get My Quote" hands off to `quotes.rates.ca/autoquote`, which answers HTTP 403
behind a Cloudflare "Verify you are human" challenge that does not clear on its own. This
project does not defeat bot protection, so that channel reads their public city rate page
instead — which carries the figure we want anyway. Tested and documented in
[`rates_ca.py`](backend/app/scrapers/rates_ca.py) so it is not re-attempted.

**How much each one actually takes.** Two sites run a real quote form: FSRA's calculator,
and LowestRates' funnel, which takes twelve fields including overnight parking, anti-theft,
ownership and commute distance. MyChoice's calculator takes a full profile too. The rest
publish rate data and only expose a postal-code box, so that is what gets entered —
everything past it on those sites collects a name, email and phone, and **the automation
deliberately stops before any step that would generate a real broker lead.**

---

## What's in the box

```
backend/app/
  agents/agent.py          the voice agent: prompt, 24-field intake, the one quote tool
  scrapers/
    registry.py            the ten channels, concurrent fan-out, result ordering
    profile.py             canonical answer format + per-site translation
    browser.py             one shared Chromium, contexts per channel
    base_scraper.py        result envelope, screenshot capture, value mapping
    rate_page.py           shared shape for the published-rate sources
    <ten channel modules>
  routers/token.py         LiveKit token, fresh room per session
  main.py                  FastAPI: token + /artifacts

frontend/src/components/
  QuoteExperience.jsx      phase machine: form -> loading -> results
  QuoteCarousel.jsx        swipeable cards, gold winner
  QuoteTable.jsx           side-by-side comparison, screenshot lightbox
```

### One answer, ten dialects

Every site words the same question differently. Overnight parking is `Garage` on the
form, `Private Garage` on LowestRates; marital status is `Not Married` on FSRA and
`Single` elsewhere. So the form is normalised **once** into canonical tokens
([`profile.py`](backend/app/scrapers/profile.py)), and each scraper declares a `VALUE_MAP`
from those tokens to its own site's wording:

```python
VALUE_MAP = {
    "parking": {"garage": "Private Garage", "driveway": "Private Driveway", ...},
    "ownership": {"owned": "Owned - Paid in Cash / Completed Financing", ...},
}
```

Binary answers are booleans; multi-valued ones are tokens, so a site offering a sixth
parking option is a new row in a table rather than a schema change. Adding a source means
a `parse` method and a value map — not another dialect of if-statements.

### Screenshot proof

Every channel screenshots the page it read, **scrolled to the figure it is reporting** —
a screenshot of a site's hero banner proves nothing about a number halfway down it.
Channels that fill a form screenshot that too, so you can see your own answers sitting in
the site's fields. Failures are screenshotted as well. The API serves them from
`/artifacts` and every table row links to its own.

---

## Testing

```bash
cd backend

# Every scraper on its own, against the live sites — timing, entered fields,
# screenshot check. Name channels to run a subset.
python -m tests.test_scrapers_live
python -m tests.test_scrapers_live lowestrates fsra_regulatory_benchmark

# Parsing unit tests (no network)
python -m unittest discover tests
```

`test_scrapers_live` is the one that earns its keep. It runs each channel in isolation so
a slow or broken source is *named* instead of hiding inside an aggregate — and it has
caught real bugs that a full-run test missed, including a source reporting a monthly
figure as an annual premium, which would have won it the "cheapest" badge by a factor of
ten.

A full concurrent run is around **20–25 seconds** for all ten, with the first card on
screen in about 7.

---

## Things worth knowing

**Published data drifts.** Seven of the ten channels parse figures out of page copy that
the sites rewrite on their own schedule. Parsers will break. The screenshots are what make
that detectable — if a number starts looking wrong, the framed proof shows it immediately.
Annual figures are sanity-checked against a $700–15,000 band so a monthly rate cannot
masquerade as an annual one, but that is a floor, not a guarantee.

**These are benchmarks, not binding quotes.** Regulatory averages and published rate data.
A real policy needs a real application.

**Terms of service.** Scraping these pages is against several sites' terms even though
`robots.txt` doesn't disallow the paths. Fine for a hackathon demo; worth a proper look
before anything public.

**Requirements are pinned**, `livekit-agents` in particular — it moves fast enough that an
unpinned rebuild can change the session API out from under the agent.

---

## Tech

Python 3.11 · LiveKit Agents 1.6.9 (Deepgram STT, Gemini 3 Flash, Cartesia TTS) ·
Playwright · FastAPI · React 19 · Vite · Docker Compose
