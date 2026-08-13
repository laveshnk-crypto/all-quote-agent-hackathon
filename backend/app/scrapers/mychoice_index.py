# backend/app/scrapers/mychoice_index.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import (
    RatePageScraper, age_band_premium, first_plausible_annual, plausible_annual,
)


class MyChoiceIndexScraper(RatePageScraper):
    """MyChoice's Ontario rate index -- a different dataset to their calculator.

    Where the calculator benchmarks one driver, this page publishes the rolling
    provincial average, a year-over-year change, and per-city averages, plus a
    live feed of recently issued quotes with age and vehicle attached.
    """

    channel_id = "mychoice_index"
    channel_name = "MyChoice.ca Rate Index"
    channel_category = "Aggregator"

    # The city page carries 31 city figures and an age table; the province page
    # only has the provincial average.
    limit_note = "MyChoice's index publishes averages by age band and city, not per-driver rates."

    city_url_template = "https://www.mychoice.ca/insurance/car/{city}/"
    fallback_url = "https://www.mychoice.ca/insurance/car/ontario/"

    required_fields = []

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        flat = re.sub(r"\s+", " ", text)
        city = str(applicant_data.get("city") or "").strip()

        annual = None
        headline = None
        matched_on = None

        # Age band first: closest match this page offers.
        try:
            age = int(applicant_data.get("age") or 0)
        except (TypeError, ValueError):
            age = 0
        if age:
            hit = age_band_premium(text, age)
            if hit:
                amount, band, _ = hit
                return {
                    "annual_premium": amount,
                    "headline": (
                        f"MyChoice's index puts drivers aged {band} at ${amount:,.0f}/yr."
                    ),
                    "comparisons": [],
                    "matched_on": f"age band {band}",
                    "personalisation": "age",
                }

        # City averages read as "Brampton is the most expensive ... at $3,471".
        if city:
            # The page prints "Toronto $239" (monthly) before "Toronto, ON $2,348"
            # (annual), so scan for the first figure that is credible as annual.
            hit = first_plausible_annual(
                rf"{re.escape(city)}[^.$]{{0,80}}\$\s*(\d[\d,]{{2,}})", flat
            )
            if hit:
                annual, headline = hit[0], hit[1][:220]
                matched_on = f"MyChoice city average for {city}"

        # Otherwise the headline provincial average.
        if annual is None:
            hit = first_plausible_annual(
                r"Average annual premium:?\s*\$\s*(\d[\d,]{2,})", flat
            )
            if hit:
                annual = hit[0]
                matched_on = "MyChoice Ontario average"
                yoy = re.search(r"YoY rate change:?\s*([+\-]?[\d.]+%)", flat, re.I)
                headline = (
                    f"MyChoice's Ontario rate index sits at ${annual:,.0f}/yr"
                    + (f", {yoy.group(1)} year over year." if yoy else ".")
                )

        # Recently issued quotes: "$171.25 Aug 11 2026 Auto 30 Hyundai Elantra Ottawa".
        comparisons: List[Dict[str, Any]] = []
        for row in tables:
            joined = " ".join(row)
            monthly = re.match(r"\s*\$\s*([\d,]+(?:\.\d+)?)", joined)
            age = re.search(r"\bAuto\b\s+(\d{2})\s+(.{3,40}?)\s+([A-Z][a-z]+)\s*$", joined)
            if monthly and age:
                comparisons.append(
                    {
                        "label": f"{age.group(1)}yo · {age.group(2).strip()} · {age.group(3)}",
                        "annual": round(float(monthly.group(1).replace(",", "")) * 12, 2),
                        "note": "recent quote",
                    }
                )
            if len(comparisons) >= 5:
                break

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": matched_on,
            "personalisation": "city" if matched_on and "city" in matched_on else "province",
        }
