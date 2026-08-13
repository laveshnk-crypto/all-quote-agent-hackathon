# Redacted run report — OmniQuote

- **Run started:** 2026-08-13T02:37:43+00:00
- **Run finished:** 2026-08-13T02:38:06+00:00 (22.4s wall clock)
- **Sources attempted:** 12  ·  **priced:** 12  ·  **personalised:** 7  ·  **generic averages:** 5  ·  **failed:** 0
- **Evidence captured:** 22 screenshots (stored locally, gitignored; not in this repo)

## Profile used (redacted)

This run used the project's **synthetic test fixture** — no real person's data.

- **age_band:** 30-39
- **postal_area:** M5V
- **city:** Toronto
- **vehicle:** 2021 HYUNDAI
- **redactions:** date_of_birth -> age band; postal_code -> forward sortation area (3 chars); no name / email / phone / street address (never collected)

## Coverage ledger

| Source | Status | Annual figure | Basis | Matched on | Landed at |
| --- | --- | --- | --- | --- | --- |
| Surex.com | SUCCESS | $1,296 | Province-wide average (generic) | closest Ontario quote: Male, 72, Markham · 2014 TOYOTA SIENNA CE V6 | 20.5s |
| InsurEye.com | SUCCESS | $1,920 | Province-wide average (generic) | Ontario average | 21.0s |
| HelloSafe.ca | SUCCESS | $1,953 | Your city | HelloSafe city average for Toronto | 16.3s |
| isure.ca | SUCCESS | $2,006 | Province-wide average (generic) | isure Ontario average | 22.0s |
| RateSupermarket.ca | SUCCESS | $2,235 | Province-wide average (generic) | Ontario average | 22.3s |
| MyChoice.ca Calculator | SUCCESS | $2,671 | Your full profile | age band 2, HYUNDAI 2021, M5V | 15.2s |
| MyChoice.ca Rate Index | SUCCESS | $2,677 | Your age band | age band 25-34 | 15.9s |
| Rates.ca | SUCCESS | $2,702 | Your postal area | postal area M5V | 6.3s |
| Ratehub.ca | SUCCESS | $2,810 | Your region (generic) | city page average | 5.5s |
| LowestRates.ca | SUCCESS | $3,113 | Your age band | closest published quote: 39-year-old driver, 2022 HONDA ACCORD SPORT 2.0 4DR | 14.8s |
| InsuranceHotline.com | SUCCESS | $3,555 | Your age band | age band 30-39 | 10.0s |
| FSRA Regulator Rate Ranger | SUCCESS | $3,965 | Your full profile | age 30-39, FSA M5V, 10,001-20,000 km | 11.9s |

## Comparisons

- **Recommended (cheapest personalised):** HelloSafe.ca at $1,953/yr — basis: Your city
- **Cheapest overall (any basis):** Surex.com at $1,296/yr
- **Average across priced sources:** $2,575/yr
- **Spread (cheapest to priciest):** $2,669
- **Priciest:** $3,965/yr

The recommendation deliberately ignores cheaper *generic* figures: a population
average is not a quote for this applicant, and the report labels every figure's basis.

## Gaps

Sources that priced but could not match the applicant more closely than a broad average:

- **Surex.com** (Province-wide average): Surex publishes only a handful of recent Ontario quotes, so the closest one by age can still be far from you.
- **InsurEye.com** (Province-wide average): InsurEye publishes averages by city and age band, not per-driver rates.
- **isure.ca** (Province-wide average): isure publishes only a provincial average, with no breakdown to match against.
- **RateSupermarket.ca** (Province-wide average): RateSupermarket publishes averages rather than per-driver rates.
- **Ratehub.ca** (Your region): Ratehub publishes regional averages rather than per-driver rates; their own quote tool needs contact details.

Candidates probed and excluded (16; full list in `market-registry.json`):

- **Forbes Advisor Canada** — HTTP 403 -- automation blocked
- **RateLab.ca** — HTTP 403 -- automation blocked
- **NerdWallet Canada** — HTTP 404 -- page gone
- **WOWA** — HTTP 404 -- page gone
- **Finder Canada** — HTTP 404 -- page gone
- **MoneySense** — HTTP 404 -- page gone
- **Insurdinary** — HTTP 404 -- page gone
- **BrokerLink** — HTTP 404 -- page gone
- **Youngs Insurance** — HTTP 404 -- page gone
- **Sonnet** — no published rate figures; quote funnel requires contact details (lead generation)
- **Onlia** — no published rate figures; quote funnel requires contact details
- **CAA Insurance** — no published rate figures; member pricing behind membership
- **Zensurance** — commercial lines only; no personal auto rate data
- **ThinkInsure** — no published rate figures on probed pages
- **Kanetix** — serves identical data to RateSupermarket -- duplicate, not a distinct source
- **Rates.ca live quote funnel** — HTTP 403 behind Cloudflare human-verification challenge; the registry entry for rates_ca reads their public postal-area rate page instead

## Errors

- None in this run. Known transient modes: per-channel 120s timeout,
  site HTML drift breaking a parser, and third-party outages. A failed
  channel returns a null figure with its reason; it is never substituted
  with a placeholder value.

## Notes

- Figures are benchmarks and published averages, **not binding quotes**.
- Screenshot evidence (result page framed on the figure, plus form-entry shots)
  exists for every attempt but stays on the machine that ran it; it contains the
  entered values by design and is therefore excluded from this redacted report.
