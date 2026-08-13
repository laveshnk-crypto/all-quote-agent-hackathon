# backend/app/scrapers/insureye.py
import re
from typing import Any, Dict, List, Optional

from app.scrapers.rate_page import RatePageScraper


class InsureyeScraper(RatePageScraper):
    """InsurEye publishes Ontario auto premiums broken out by city and age."""

    channel_id = "insureye"
    channel_name = "InsurEye.com"
    channel_category = "Aggregator"

    limit_note = "InsurEye publishes averages by city and age band, not per-driver rates."

    city_url_template = None
    fallback_url = "https://www.insureye.com/car-insurance-ontario/"

    required_fields = []

    #: InsurEye publishes everything per month, so every figure here is x12
    #: before it can sit alongside the other channels.
    MONTHLY_MIN, MONTHLY_MAX = 40.0, 1200.0

    def _annualise(self, monthly: Optional[float]) -> Optional[float]:
        if monthly is None or not (self.MONTHLY_MIN <= monthly <= self.MONTHLY_MAX):
            return None
        return round(monthly * 12, 2)

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        city = str(applicant_data.get("city") or "").strip()

        # City first: their table is city -> monthly premium.
        if city:
            match = re.search(
                rf"\b{re.escape(city)}\b[^\n]{{0,50}}?\$\s*(\d[\d,]*(?:\.\d+)?)", text, re.I
            )
            if match:
                annual = self._annualise(float(match.group(1).replace(",", "")))
                if annual:
                    return {
                        "annual_premium": annual,
                        "headline": (
                            f"InsurEye puts {city} at ${annual / 12:,.0f}/month, "
                            f"about ${annual:,.0f}/yr."
                        ),
                        "comparisons": [],
                        "matched_on": f"city average for {city}",
                        "personalisation": "city",
                    }

        # Otherwise their headline monthly average.
        match = re.search(r"Average\s*\$\s*(\d[\d,]*(?:\.\d+)?)", text, re.I)
        annual = self._annualise(float(match.group(1).replace(",", ""))) if match else None

        return {
            "annual_premium": annual,
            "headline": (
                f"InsurEye's Ontario average is ${annual / 12:,.0f}/month, "
                f"about ${annual:,.0f}/yr."
                if annual
                else None
            ),
            "comparisons": [],
            "matched_on": "Ontario average" if annual else None,
            "personalisation": "province",
        }
