# backend/app/scrapers/ratehub.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper, lines_with_money


class RatehubScraper(RatePageScraper):
    channel_id = "ratehub"
    channel_name = "Ratehub.ca"
    channel_category = "Aggregator"

    city_url_template = "https://www.ratehub.ca/insurance/car/{city}"
    fallback_url = "https://www.ratehub.ca/insurance/car/ontario"

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        annual = None
        headline = None
        comparisons: List[Dict[str, Any]] = []

        # Ratehub writes averages two ways: "$2,810 per year" and "$2,164 annually".
        for line in lines_with_money(text, keywords=r"averag|per year|annually"):
            match = re.search(
                r"\$\s*(\d[\d,]{2,})\s*(?:per year|annually|a year)", line, re.I
            )
            if match and annual is None:
                annual = float(match.group(1).replace(",", ""))
                headline = line[:200]

        # Monthly city averages ("average monthly rate of $428") -> annualise.
        if annual is None:
            for line in lines_with_money(text, keywords=r"averag.*month|month.*averag"):
                match = re.search(r"\$\s*(\d[\d,]{2,})", line)
                if match:
                    annual = round(float(match.group(1).replace(",", "")) * 12, 2)
                    headline = line[:200]
                    break

        # Example quotes Ratehub prints as "$97/month for a 52-year-old ...".
        for line in text.splitlines():
            match = re.search(r"\$\s*(\d[\d,]{1,})\s*/?\s*month", line, re.I)
            if match and re.search(r"\d{2}[- ]year[- ]old", line, re.I):
                comparisons.append(
                    {
                        "label": line.strip()[:90],
                        "annual": round(float(match.group(1).replace(",", "")) * 12, 2),
                        "note": "sample quote published by Ratehub",
                    }
                )
            if len(comparisons) >= 4:
                break

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": "city page average" if annual else None,
        }
