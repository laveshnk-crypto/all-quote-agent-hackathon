# backend/app/scrapers/surex.py
import re
from typing import Any, Dict, List, Optional

from app.scrapers.rate_page import RatePageScraper

# Each published sample reads:
#   Male, 72 from Markham, ON
#   2014 TOYOTA SIENNA CE V6
#   Quote Date: Jul 21, 2026
#   $108 / month
#   $1,296 / year
SAMPLE_RE = re.compile(
    r"(Male|Female),\s*(\d{2})\s*from\s*([^,]{2,30}),\s*([A-Z]{2})\s+"
    r"(.{4,60}?)\s+Quote Date:[^$]{0,40}"
    r"\$\s*([\d,]+(?:\.\d+)?)\s*/\s*month\s+\$\s*([\d,]+(?:\.\d+)?)\s*/\s*year",
    re.I,
)


class SurexScraper(RatePageScraper):
    """Surex is a brokerage publishing a rolling feed of real issued quotes.

    Each sample carries the driver's gender, age, city, province and vehicle, so
    we match on province first and then age. Samples come from across Canada and
    premiums vary enormously by province, so a non-Ontario sample is worthless
    here -- if none exist we report no rate rather than quoting a stranger.
    """

    channel_id = "surex"
    channel_name = "Surex.com"
    channel_category = "Broker"

    city_url_template = None
    fallback_url = "https://www.surex.com/insurance/auto"

    required_fields = ["age"]

    #: Only samples from this province are comparable.
    province = "ON"

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        flat = re.sub(r"[ \t]+", " ", text)

        samples = []
        seen = set()
        for gender, age, city, prov, vehicle, monthly, annual in SAMPLE_RE.findall(flat):
            key = (age, city, vehicle, annual)
            if key in seen:
                continue
            seen.add(key)
            samples.append(
                {
                    "gender": gender.title(),
                    "age": int(age),
                    "city": city.strip(),
                    "province": prov.upper(),
                    "vehicle": vehicle.strip(),
                    "monthly": float(monthly.replace(",", "")),
                    "annual": float(annual.replace(",", "")),
                }
            )

        ontario = [s for s in samples if s["province"] == self.province]
        if not ontario:
            # Samples exist but none from Ontario: nothing comparable to quote.
            return {
                "annual_premium": None,
                "headline": (
                    f"Surex published {len(samples)} recent quotes, none of them from Ontario."
                    if samples
                    else None
                ),
                "comparisons": [],
            }

        try:
            target_age = int(applicant_data.get("age") or 0)
        except (TypeError, ValueError):
            target_age = 0

        best = min(ontario, key=lambda s: abs(s["age"] - target_age) if target_age else 0)

        matched: Optional[str] = (
            f"closest Ontario quote: {best['gender']}, {best['age']}, "
            f"{best['city']} · {best['vehicle']}"
        )

        return {
            "annual_premium": best["annual"],
            "headline": (
                f"Surex's closest published Ontario quote is ${best['annual']:,.0f}/yr "
                f"(${best['monthly']:,.0f}/month) for a {best['age']}-year-old in "
                f"{best['city']}."
            ),
            "comparisons": [
                {
                    "label": f"{s['age']}yo · {s['city']} · {s['vehicle'][:26]}",
                    "annual": s["annual"],
                    "note": f"${s['monthly']:,.0f}/mo",
                }
                for s in ontario
                if s is not best
            ][:4],
            "matched_on": matched,
        }
