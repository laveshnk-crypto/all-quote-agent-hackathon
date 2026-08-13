# backend/tests/test_scrapers_live.py
"""Exercise every scraper on its own against the live site.

    python -m tests.test_scrapers_live            # all ten
    python -m tests.test_scrapers_live lowestrates fsra_regulatory_benchmark

Each channel runs in isolation with its own timing, so a slow or broken source
is named rather than hiding inside an aggregate. Network-dependent by design --
this is the check that the sites still behave, not a unit test.
"""
import asyncio
import sys
import time
from typing import Any, Dict, List

from app.scrapers.profile import build_profile, legacy_applicant_dict
from app.scrapers.registry import SCRAPERS

# A complete, realistic confirmed intake form.
CONFIRMED: Dict[str, Any] = {
    "date_of_birth": "1995-03-05",
    "gender": "Male",
    "marital_status": "Not Married",
    "postal_code": "M5V 2T6",
    "city": "Toronto",
    "vehicle_year": 2021,
    "vehicle_make": "Hyundai",
    "vehicle_model": "Elantra",
    "annual_mileage_km": 15000,
    "years_licensed": 5,
    "years_claim_free": 5,
    "at_fault_accidents": 0,
    "tickets_convictions": 0,
    "current_monthly_premium": 180,
    "overnight_parking": "Garage",
    "primary_use": "Personal",
    "financed_or_leased": "Financed",
    "daily_commute_km": 20,
    "anti_theft_device": True,
    "winter_tires": True,
    "comprehensive_coverage": True,
    "collision_coverage": True,
    "multi_vehicle_discount": False,
    "multi_policy_discount": True,
}

SHOTS = "app/scrapers/screenshots"


async def run_one(cls) -> Dict[str, Any]:
    profile = build_profile(CONFIRMED, age=31)
    applicant = legacy_applicant_dict(profile)

    scraper = cls(screenshot_dir=SHOTS)
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(scraper.execute(applicant), timeout=150)
    except asyncio.TimeoutError:
        return {"channel": cls.channel_name, "status": "TIMEOUT",
                "elapsed": time.perf_counter() - started}
    except Exception as exc:  # noqa: BLE001 - the report is the point
        return {"channel": cls.channel_name, "status": f"RAISED {type(exc).__name__}",
                "detail": str(exc)[:100], "elapsed": time.perf_counter() - started}

    payload = result.get("evidence_payload") or {}
    return {
        "channel": cls.channel_name,
        "status": result["status"],
        "premium": result.get("annual_premium"),
        "elapsed": time.perf_counter() - started,
        "entered": list((payload.get("entered") or {}).keys()),
        "entry_shots": len(result.get("entry_screenshot_urls") or []),
        "has_result_shot": bool(result.get("screenshot_url")),
        "detail": (result.get("evidence_summary") or "")[:90],
    }


async def main(only: List[str]) -> int:
    chosen = [c for c in SCRAPERS if not only or c.channel_id in only]
    print(f"testing {len(chosen)} scraper(s) individually\n")

    rows = []
    for cls in chosen:
        row = await run_one(cls)
        rows.append(row)
        mark = "ok  " if row["status"] == "SUCCESS" else "FAIL"
        premium = f"${row['premium']:,.0f}" if row.get("premium") else "-"
        print(f"[{mark}] {row['channel']:28} {row['status']:14} {premium:>9}  "
              f"{row['elapsed']:5.1f}s  entry={row.get('entry_shots', 0)} "
              f"result_shot={row.get('has_result_shot')}")
        if row.get("entered"):
            print(f"        entered: {', '.join(row['entered'])}")
        if row["status"] != "SUCCESS":
            print(f"        {row.get('detail', '')}")

    ok = sum(1 for r in rows if r["status"] == "SUCCESS")
    slow = [r for r in rows if r["elapsed"] > 60]
    print(f"\n{ok}/{len(rows)} scrapers returned a price")
    if slow:
        print("slow (>60s): " + ", ".join(f"{r['channel']} {r['elapsed']:.0f}s" for r in slow))
    no_shot = [r["channel"] for r in rows if r["status"] == "SUCCESS" and not r.get("has_result_shot")]
    if no_shot:
        print("missing result screenshot: " + ", ".join(no_shot))
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
