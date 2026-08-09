# OmniQuote ON

OmniQuote ON is an automated, multi-channel rate aggregation and evidence-auditing platform built for Ontario drivers. By pairing Playwright browser automation with real-time FSRA regulatory benchmarks, OmniQuote ON queries direct insurers, aggregators, and provincial rate ranger databases in parallel.

It transforms disjointed quoter forms into a unified, single-intake pipeline that captures price estimates, logs visual screenshot proofs, and guarantees complete auditability across all market channels.

---

## Key Features

1. **Single-Intake Data Standard:** A unified React frontend and FastAPI/Pydantic validation layer mapping complex Ontario driver parameters—such as parking location, daily commute distance, license history, and coverage tiers—directly to real-world quoter forms.
2. **Multi-Channel Coverage:** Ingests rate data across direct insurers, aggregators (e.g., Rates.ca), and provincial regulatory reference engines (FSRA Regulator Rate Ranger and RIBO broker frameworks) to eliminate silent market gaps.
3. **Auditable Visual Evidence & Proof:** Every run automatically records full-page PNG screenshots, raw DOM payloads, and step-by-step audit summaries to verify quoted prices and capture bot-detection checkpoints.
4. **Asynchronous Persistence Architecture:** Built with FastAPI, SQLAlchemy (AsyncIO), and PostgreSQL to manage applicant data, log historical execution runs, and serve visual audit artifacts in real time.

---

## Tech Stack

* **Frontend:** React, TypeScript, Tailwind CSS
* **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2.0 (AsyncIO)
* **Database:** PostgreSQL (`asyncpg`)
* **Browser Automation & Scraping:** Playwright Async API
* **Integrated Channels & References:**
  * **Regulatory:** Financial Services Regulatory Authority of Ontario (FSRA) Regulator Rate Ranger, Registered Insurance Brokers of Ontario (RIBO) Broker Registry
  * **Aggregators:** Rates.ca
  * **Direct Insurers:** Sonnet, Belairdirect, TD Insurance

---

## System Architecture Flow

```text
[ React Frontend ]  --->  ( Single Intake Driver Profile )
                                   |
                                   v
                       [ FastAPI Intake Endpoint ]
                                   |
                         ( PostgreSQL Database )
                                   |
        +--------------------------+--------------------------+
        |                          |                          |
        v                          v                          v
[ FSRA Scraper ]          [ Rates.ca Scraper ]      [ Direct Carrier Scrapers ]
  (Playwright)                (Playwright)                 (Playwright)
        |                          |                          |
        +--------------------------+--------------------------+
                                   |
                                   v
             [ Standardized Evidence Payload + Screenshot PNGs ]
                                   |
                        [ PostgreSQL Quote Runs ]
                                   |
                                   v
                 [ React Audit & Comparison Dashboard ]