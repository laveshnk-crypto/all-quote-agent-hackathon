# backend/app/scrapers/ratesupermarket.py
from typing import Any, Dict, List

from app.scrapers.rate_page import (
    RatePageScraper, age_band_premium, city_premium, lines_with_money, plausible_annual,
)


class RateSupermarketScraper(RatePageScraper):
    """RateSupermarket, a Canadian comparison site publishing Ontario averages."""

    channel_id = "ratesupermarket"
    channel_name = "RateSupermarket.ca"
    channel_category = "Aggregator"

    limit_note = "RateSupermarket publishes averages rather than per-driver rates."

    city_url_template = None
    fallback_url = "https://www.ratesupermarket.ca/car_insurance"

    required_fields = []

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
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
                    "headline": f"RateSupermarket puts drivers aged {band} at ${amount:,.0f}/yr.",
                    "comparisons": [],
                    "matched_on": f"age band {band}",
                    "personalisation": "age",
                }

        hit = city_premium(text, str(applicant_data.get("city") or "").strip())
        if hit:
            return {
                "annual_premium": hit[0],
                "headline": hit[1],
                "comparisons": [],
                "matched_on": "city average",
                "personalisation": "city",
            }

        annual = None
        headline = None
        for line in lines_with_money(text, keywords=r"averag|per year|annually"):
            amount = self.parse_money(line)
            if plausible_annual(amount):
                annual, headline = amount, line[:200]
                break

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": [],
            "matched_on": "Ontario average" if annual else None,
            "personalisation": "province",
        }
