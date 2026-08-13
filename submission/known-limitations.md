# Known limitations — OmniQuote

Ordered by how much they constrain the product, with the dependency named in bold.
Every entry below was observed during development, not hypothesised.

## Binding quotes require a licensed human

- **Licensed intermediary.** In Ontario, selling or binding an auto policy requires a
  licensed broker or agent (RIBO/FSRA licensing). Everything OmniQuote returns is a
  benchmark or published average with evidence — deliberately *not* a bindable quote.
  The end of our flow is where a licensed human's work begins.
- **Human at the checkout.** Every direct-insurer funnel probed (Sonnet, Onlia, CAA,
  and the aggregator funnels behind LowestRates / InsuranceHotline / Rates.ca) requires
  name, email and phone before pricing. Submitting those would create a real broker
  lead for a real person, so the automation stops at that boundary by design. A truly
  personal per-insurer price therefore depends on a human choosing to enter the funnel.

## Blocked or unavailable integrations

- **Rates.ca live funnel:** `quotes.rates.ca` answers HTTP 403 behind a Cloudflare
  "verify you are human" challenge that does not self-clear. We do not defeat bot
  protection; the channel reads their public postal-area rate table instead.
- **Forbes Advisor and RateLab:** block automated access outright (HTTP 403). Excluded.
- **No official rate APIs.** None of the twelve sources offers a public quoting API;
  partnership or **terms permission** would be needed for production-grade access.
  Seven probed candidate sites were dead links and one (Kanetix) duplicates another
  source's data — details in `market-registry.json`.
- **Membership-gated pricing** (e.g. CAA member rates) is unavailable without a
  membership relationship.

## Terms of service

- Several sources' terms restrict automated access even where `robots.txt` permits the
  paths. Acceptable for a hackathon demonstration with evidence screenshots; running
  this commercially depends on **permission from each site's terms** or a data
  partnership. This is the single largest gap between demo and product.

## Data and matching limits

- **Five of twelve sources publish only broad averages** (region or province). They are
  labelled "generic" in the UI rather than dressed up as personal quotes, and each
  carries a note explaining why it cannot go closer.
- **Published pages drift.** Seven channels parse figures out of editorial copy that the
  sites rewrite on their own schedule; parsers will break silently in meaning even when
  they succeed mechanically. Mitigations: per-figure screenshot evidence, a
  $700–$15,000 plausibility band on annual figures, and a per-scraper live test
  (`python -m tests.test_scrapers_live`) that names the broken source.
- **Bucketing loses precision.** Sites take mileage, age and vehicle year in fixed
  buckets; answers are snapped to the nearest bucket and the match is disclosed.
- Two site controls resist automation (MyChoice's model dropdown, LowestRates' winter
  tire select): they are recorded as skipped rather than guessed.

## Operational dependencies

- **One agent worker, restarted by a human after edits.** The LiveKit Python CLI no
  longer hot-reloads; stale workers compete for job dispatches and answer calls with old
  code. Docker Compose pins one replica, but bare-metal runs depend on operator
  discipline (`pkill -9 -f "agent.py dev"` before starting).
- **Shared machine contention.** The scrapers and the voice pipeline share CPU; browser
  concurrency is capped at 4 because six simultaneous page renders made speech stutter.
- **LLM behaviour is prompt-bound.** Tool-calling reliability required switching models
  once (Gemma has no native function calling); narration quality depends on prompt
  adherence and is not formally verified.

## Scope

- **Ontario, English, auto insurance only.** City-level matching assumes Ontario
  geography; postal-area matching exists only where a source publishes FSA-level data.
- Run-to-run wall clock varies (≈19–80s observed) with the sites' own latency; the UI
  shows a live estimate rather than promising a fixed time.
