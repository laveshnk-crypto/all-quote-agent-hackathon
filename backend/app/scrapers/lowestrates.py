# backend/app/scrapers/lowestrates.py
import re
from typing import Any, Dict, List, Optional

from app.scrapers.rate_page import RatePageScraper


class LowestRatesScraper(RatePageScraper):
    """LowestRates publishes a table of recent real quotes per city.

    Each row carries the driver's age, city, vehicle and both the lowest and
    average annual rate, so unlike the other editorial channels we can pick the
    row closest to this applicant rather than quoting a city-wide average.
    """

    channel_id = "lowestrates"
    channel_name = "LowestRates.ca"
    channel_category = "Aggregator"

    city_url_template = "https://www.lowestrates.ca/insurance/auto/{city}"
    fallback_url = "https://www.lowestrates.ca/insurance/auto"

    required_fields = ["city", "age"]

    @staticmethod
    def _row_quotes(row_text: str) -> List[float]:
        """Annual figures in a row, in order: lowest/yr then average/yr."""
        return [
            float(value.replace(",", ""))
            for value in re.findall(r"\$\s*(\d[\d,]*)\s*/\s*yr", row_text)
        ]

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            target_age = int(applicant_data.get("age") or 0)
        except (TypeError, ValueError):
            target_age = 0

        target_make = str(applicant_data.get("vehicle_make") or "").strip().upper()

        quotes: List[Dict[str, Any]] = []
        for row in tables:
            joined = " ".join(row)
            annuals = self._row_quotes(joined)
            if len(annuals) < 2:
                continue

            age_match = re.search(r"(\d{2})\s*years?\s*old", joined, re.I)
            vehicle_match = re.search(r"((?:19|20)\d{2}\s+[A-Z][A-Z0-9 .\-]{2,40})", joined)
            quotes.append(
                {
                    "age": int(age_match.group(1)) if age_match else None,
                    "vehicle": vehicle_match.group(1).strip() if vehicle_match else None,
                    "lowest_annual": annuals[0],
                    "average_annual": annuals[1],
                }
            )

        if not quotes:
            return {"annual_premium": None, "headline": None, "comparisons": []}

        def distance(quote: Dict[str, Any]) -> tuple:
            age_gap = abs((quote["age"] or 999) - target_age) if target_age else 999
            make_hit = 0 if target_make and target_make in (quote["vehicle"] or "") else 1
            return (make_hit, age_gap)

        best = min(quotes, key=distance)
        matched: Optional[str] = None
        if best["age"] is not None and target_age:
            matched = f"closest published quote: {best['age']}-year-old driver"
            if best["vehicle"]:
                matched += f", {best['vehicle']}"

        comparisons = [
            {
                "label": f"{q['age']}yo · {q['vehicle'] or 'vehicle n/a'}",
                "annual": q["lowest_annual"],
                "note": f"market average {q['average_annual']:,.0f}",
            }
            for q in quotes[:5]
        ]

        headline = (
            f"LowestRates.ca's closest published quote for this profile is "
            f"${best['lowest_annual']:,.0f}/yr, against a market average of "
            f"${best['average_annual']:,.0f}/yr."
        )

        return {
            # The lowest rate is what this channel actually offers a shopper.
            "annual_premium": best["lowest_annual"],
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": matched,
            "market_average_annual": best["average_annual"],
        }
