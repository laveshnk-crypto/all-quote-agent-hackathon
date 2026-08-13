#!/usr/bin/env python3
"""Generate the machine-readable market registry and the redacted run report.

Both artifacts are produced from a live verification run against every
registered channel, so the statuses and timestamps in them are measured, not
asserted. Regenerate from the repo root with:

    .venv/bin/python submission/generate.py

The profile used is the project's synthetic test fixture. No real person's
data is involved, and the outputs are additionally redacted to the level the
project's safety note commits to: age band rather than date of birth, forward
sortation area (first three postal characters) rather than a full postal code,
and no name, contact detail or street address anywhere (none are collected).
"""
import asyncio
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT / "submission"

sys.path.insert(0, str(BACKEND))
import os

os.chdir(BACKEND)  # scrapers write artifacts relative to the backend root

from app.scrapers.profile import build_profile, legacy_applicant_dict  # noqa: E402
from app.scrapers.registry import SCRAPERS, run_all_channels, summarise  # noqa: E402
from tests.test_scrapers_live import CONFIRMED  # noqa: E402  (synthetic fixture)

AGE = 31  # derived from the synthetic fixture's date of birth


def age_band(age: int) -> str:
    low = (age // 10) * 10
    return f"{low}-{low + 9}"


REDACTED_PROFILE = {
    "profile_type": "synthetic test fixture -- not a real person",
    "age_band": age_band(AGE),
    "postal_area": str(CONFIRMED["postal_code"]).replace(" ", "")[:3],
    "city": CONFIRMED["city"],
    "vehicle": f"{CONFIRMED['vehicle_year']} {CONFIRMED['vehicle_make'].upper()}",
    "redactions_applied": [
        "date_of_birth -> age band",
        "postal_code -> forward sortation area (3 chars)",
        "no name / email / phone / street address (never collected)",
    ],
}

# Candidates probed live on 2026-08-12 and not admitted to the registry.
# Every rejection reason was observed, not assumed.
REJECTED_CANDIDATES = [
    {"name": "Forbes Advisor Canada", "url": "https://www.forbes.com/advisor/ca/car-insurance/car-insurance-ontario/", "reason": "HTTP 403 -- automation blocked"},
    {"name": "RateLab.ca", "url": "https://ratelab.ca/car-insurance-ontario/", "reason": "HTTP 403 -- automation blocked"},
    {"name": "NerdWallet Canada", "url": "https://www.nerdwallet.com/ca/insurance/car-insurance-ontario", "reason": "HTTP 404 -- page gone"},
    {"name": "WOWA", "url": "https://wowa.ca/insurance/car-insurance-ontario", "reason": "HTTP 404 -- page gone"},
    {"name": "Finder Canada", "url": "https://www.finder.com/ca/car-insurance-ontario", "reason": "HTTP 404 -- page gone"},
    {"name": "MoneySense", "url": "https://www.moneysense.ca/save/insurance/car-insurance-ontario/", "reason": "HTTP 404 -- page gone"},
    {"name": "Insurdinary", "url": "https://insurdinary.ca/car-insurance-ontario/", "reason": "HTTP 404 -- page gone"},
    {"name": "BrokerLink", "url": "https://www.brokerlink.ca/insurance/car-insurance/ontario", "reason": "HTTP 404 -- page gone"},
    {"name": "Youngs Insurance", "url": "https://www.youngsinsurance.ca/personal-insurance/auto-insurance", "reason": "HTTP 404 -- page gone"},
    {"name": "Sonnet", "url": "https://www.sonnet.ca/auto-insurance/ontario", "reason": "no published rate figures; quote funnel requires contact details (lead generation)"},
    {"name": "Onlia", "url": "https://www.onlia.ca/car-insurance", "reason": "no published rate figures; quote funnel requires contact details"},
    {"name": "CAA Insurance", "url": "https://www.caainsurancecompany.com/auto-insurance", "reason": "no published rate figures; member pricing behind membership"},
    {"name": "Zensurance", "url": "https://www.zensurance.com/", "reason": "commercial lines only; no personal auto rate data"},
    {"name": "ThinkInsure", "url": "https://www.thinkinsure.ca/insurance-quotes/car-insurance-toronto.html", "reason": "no published rate figures on probed pages"},
    {"name": "Kanetix", "url": "https://www.kanetix.ca/car-insurance", "reason": "serves identical data to RateSupermarket -- duplicate, not a distinct source"},
    {"name": "Rates.ca live quote funnel", "url": "https://quotes.rates.ca/autoquote", "reason": "HTTP 403 behind Cloudflare human-verification challenge; the registry entry for rates_ca reads their public postal-area rate page instead"},
]

STATUS_MAP = {
    "SUCCESS": "verified",
    "REJECTED": "no_match_for_profile",
    "SYSTEM_ERROR": "error",
    "BLOCKED_CAPTCHA": "blocked_captcha",
    "PHONE_REQUIRED": "phone_required",
}


async def main() -> None:
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    arrivals: dict[str, float] = {}

    async def on_result(result, done, total):
        arrivals[result["channel_id"]] = round(time.perf_counter() - t0, 1)

    profile = build_profile(CONFIRMED, age=AGE)
    applicant = legacy_applicant_dict(profile)
    results = await run_all_channels(
        applicant, screenshot_dir="app/scrapers/screenshots", on_result=on_result
    )
    wall = round(time.perf_counter() - t0, 1)
    finished = datetime.now(timezone.utc)
    totals = summarise(results)
    verified_at = finished.isoformat(timespec="seconds")

    ids = [r["channel_id"] for r in results]
    assert len(ids) == len(set(ids)), "rate-source IDs must be distinct"

    by_id = {r["channel_id"]: r for r in results}

    # ---------------- market registry ----------------
    registry_rows = []
    for cls in SCRAPERS:
        r = by_id[cls.channel_id]
        payload = r.get("evidence_payload") or {}
        urls = [
            u
            for u in (
                getattr(cls, "city_url_template", None),
                getattr(cls, "fallback_url", None),
                getattr(cls, "url", None),
            )
            if u
        ] or [payload.get("source_url") or payload.get("target_url")]
        registry_rows.append(
            {
                "source_id": cls.channel_id,
                "name": cls.channel_name,
                "channel_category": cls.channel_category,
                "urls": [u for u in urls if u],
                "status": STATUS_MAP.get(r["status"], r["status"].lower()),
                "last_run_status": r["status"],
                "verified_at": verified_at,
                "personalisation": r.get("personalisation"),
                "personalisation_label": r.get("personalisation_label"),
                "is_generic": r.get("is_generic"),
                "required_fields": list(cls.required_fields),
                "limit_note": cls.limit_note,
                "evidence": {
                    "result_screenshot": bool(r.get("screenshot_url")),
                    "entry_screenshots": len(r.get("entry_screenshot_urls") or []),
                },
            }
        )

    registry = {
        "generated_at": verified_at,
        "generator": "submission/generate.py (live verification run)",
        "province": "Ontario, Canada",
        "verification_profile": REDACTED_PROFILE,
        "active_sources": registry_rows,
        "rejected_candidates": [
            {**c, "probed_at": "2026-08-12"} for c in REJECTED_CANDIDATES
        ],
    }
    (OUT / "market-registry.json").write_text(json.dumps(registry, indent=2) + "\n")

    with (OUT / "market-registry.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["source_id", "name", "channel_category", "status", "personalisation",
             "is_generic", "verified_at", "primary_url", "limit_note"]
        )
        for row in registry_rows:
            w.writerow(
                [row["source_id"], row["name"], row["channel_category"], row["status"],
                 row["personalisation"] or "", row["is_generic"], row["verified_at"],
                 (row["urls"] or [""])[0], row["limit_note"] or ""]
            )

    # ---------------- redacted run report ----------------
    priced = [r for r in results if r["status"] == "SUCCESS" and r["annual_premium"]]
    personalised = [r for r in priced if not r["is_generic"]]
    generic = [r for r in priced if r["is_generic"]]
    failures = [r for r in results if r["status"] != "SUCCESS"]
    best = next((r for r in results if r.get("is_recommended")), None)
    shots = sum(
        (1 if r.get("screenshot_url") else 0) + len(r.get("entry_screenshot_urls") or [])
        for r in results
    )

    def money(v):
        return f"${v:,.0f}" if v else "-"

    lines = []
    lines.append("# Redacted run report — OmniQuote")
    lines.append("")
    lines.append(f"- **Run started:** {started.isoformat(timespec='seconds')}")
    lines.append(f"- **Run finished:** {finished.isoformat(timespec='seconds')} ({wall}s wall clock)")
    lines.append(f"- **Sources attempted:** {len(results)}  ·  **priced:** {len(priced)}  ·  "
                 f"**personalised:** {len(personalised)}  ·  **generic averages:** {len(generic)}  ·  "
                 f"**failed:** {len(failures)}")
    lines.append(f"- **Evidence captured:** {shots} screenshots (stored locally, gitignored; not in this repo)")
    lines.append("")
    lines.append("## Profile used (redacted)")
    lines.append("")
    lines.append("This run used the project's **synthetic test fixture** — no real person's data.")
    lines.append("")
    for k in ("age_band", "postal_area", "city", "vehicle"):
        lines.append(f"- **{k}:** {REDACTED_PROFILE[k]}")
    lines.append(f"- **redactions:** {'; '.join(REDACTED_PROFILE['redactions_applied'])}")
    lines.append("")
    lines.append("## Coverage ledger")
    lines.append("")
    lines.append("| Source | Status | Annual figure | Basis | Matched on | Landed at |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for r in results:
        payload = r.get("evidence_payload") or {}
        basis = r.get("personalisation_label") or "—"
        matched = payload.get("matched_on") or r.get("evidence_summary") or "—"
        lines.append(
            f"| {r['channel_name']} | {r['status']} | {money(r['annual_premium'])} | "
            f"{basis}{' (generic)' if r.get('is_generic') else ''} | {str(matched)[:80]} | "
            f"{arrivals.get(r['channel_id'], '—')}s |"
        )
    lines.append("")
    lines.append("## Comparisons")
    lines.append("")
    if best:
        lines.append(f"- **Recommended (cheapest personalised):** {best['channel_name']} at "
                     f"{money(best['annual_premium'])}/yr — basis: {best['personalisation_label']}")
    lines.append(f"- **Cheapest overall (any basis):** {totals['cheapest_channel']} at {money(totals['cheapest_annual'])}/yr")
    lines.append(f"- **Average across priced sources:** {money(totals['average_annual'])}/yr")
    lines.append(f"- **Spread (cheapest to priciest):** {money(totals['spread_annual'])}")
    lines.append(f"- **Priciest:** {money(totals['dearest_annual'])}/yr")
    lines.append("")
    lines.append("The recommendation deliberately ignores cheaper *generic* figures: a population")
    lines.append("average is not a quote for this applicant, and the report labels every figure's basis.")
    lines.append("")
    lines.append("## Gaps")
    lines.append("")
    lines.append("Sources that priced but could not match the applicant more closely than a broad average:")
    lines.append("")
    for r in generic:
        lines.append(f"- **{r['channel_name']}** ({r.get('personalisation_label')}): {r.get('limit_note') or 'no reason declared'}")
    lines.append("")
    lines.append(f"Candidates probed and excluded ({len(REJECTED_CANDIDATES)}; full list in `market-registry.json`):")
    lines.append("")
    for c in REJECTED_CANDIDATES:
        lines.append(f"- **{c['name']}** — {c['reason']}")
    lines.append("")
    lines.append("## Errors")
    lines.append("")
    if failures:
        for r in failures:
            lines.append(f"- **{r['channel_name']}**: {r['status']} — {(r.get('evidence_summary') or '')[:140]}")
    else:
        lines.append("- None in this run. Known transient modes: per-channel 120s timeout,")
        lines.append("  site HTML drift breaking a parser, and third-party outages. A failed")
        lines.append("  channel returns a null figure with its reason; it is never substituted")
        lines.append("  with a placeholder value.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Figures are benchmarks and published averages, **not binding quotes**.")
    lines.append("- Screenshot evidence (result page framed on the figure, plus form-entry shots)")
    lines.append("  exists for every attempt but stays on the machine that ran it; it contains the")
    lines.append("  entered values by design and is therefore excluded from this redacted report.")
    lines.append("")
    (OUT / "run-report.md").write_text("\n".join(lines))

    report_json = {
        "generated_at": verified_at,
        "run": {"started": started.isoformat(timespec="seconds"),
                "finished": finished.isoformat(timespec="seconds"),
                "wall_clock_seconds": wall},
        "profile": REDACTED_PROFILE,
        "summary": totals,
        "recommended": best["channel_id"] if best else None,
        "ledger": [
            {
                "source_id": r["channel_id"],
                "status": r["status"],
                "annual_premium": r["annual_premium"],
                "personalisation": r.get("personalisation"),
                "is_generic": r.get("is_generic"),
                "matched_on": (r.get("evidence_payload") or {}).get("matched_on"),
                "landed_at_seconds": arrivals.get(r["channel_id"]),
            }
            for r in results
        ],
    }
    (OUT / "run-report.json").write_text(json.dumps(report_json, indent=2) + "\n")

    print(f"wrote market-registry.json/.csv, run-report.md/.json  ({wall}s run, "
          f"{len(priced)}/{len(results)} priced, {len(personalised)} personalised)")


if __name__ == "__main__":
    asyncio.run(main())
