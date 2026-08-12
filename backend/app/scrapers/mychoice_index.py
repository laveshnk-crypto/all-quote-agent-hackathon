# backend/app/scrapers/mychoice_index.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper


class MyChoiceIndexScraper(RatePageScraper):
    """MyChoice's Ontario rate index -- a different dataset to their calculator.

    Where the calculator benchmarks one driver, this page publishes the rolling
    provincial average, a year-over-year change, and per-city averages, plus a
    live feed of recently issued quotes with age and vehicle attached.
    """

    channel_id = "mychoice_index"
    channel_name = "MyChoice.ca Rate Index"
    channel_category = "Aggregator"

    city_url_template = None
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

        # City averages read as "Brampton is the most expensive ... at $3,471".
        if city:
            pattern = rf"{re.escape(city)}[^.$]{{0,80}}\$\s*(\d[\d,]{{2,}})"
            match = re.search(pattern, flat, re.I)
            if match:
                annual = float(match.group(1).replace(",", ""))
                matched_on = f"MyChoice city average for {city}"
                headline = match.group(0)[:220]

        # Otherwise the headline provincial average.
        if annual is None:
            match = re.search(r"Average annual premium:?\s*\$\s*(\d[\d,]{2,})", flat, re.I)
            if match:
                annual = float(match.group(1).replace(",", ""))
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
        }
