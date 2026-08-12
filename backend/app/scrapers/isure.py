# backend/app/scrapers/isure.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper, lines_with_money


class IsureScraper(RatePageScraper):
    """isure is an Ontario brokerage publishing the provincial average premium."""

    channel_id = "isure"
    channel_name = "isure.ca"
    channel_category = "Broker"

    city_url_template = None
    fallback_url = "https://isure.ca/ontario-car-insurance/"

    required_fields = []

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        annual = None
        headline = None

        for line in lines_with_money(
            text, keywords=r"averag|premium|per year|annually"
        ):
            for raw in re.findall(r"\$\s*(\d[\d,]{2,}(?:\.\d+)?)", line):
                value = float(raw.replace(",", ""))
                # Ontario annual premiums live in this band; anything outside is
                # a coverage limit or a deductible, not a rate.
                if 800 <= value <= 12000:
                    annual = value
                    headline = line[:220]
                    break
            if annual:
                break

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": [],
            "matched_on": "isure Ontario average" if annual else None,
        }
