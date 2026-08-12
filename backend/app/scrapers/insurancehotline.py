# backend/app/scrapers/insurancehotline.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper, region_for


class InsuranceHotlineScraper(RatePageScraper):
    """InsuranceHotline reports Ontario averages split by region band.

    The province page breaks premiums into GTA / other urban / rural, so we pick
    the band the applicant's city falls into instead of the headline number.
    """

    channel_id = "insurancehotline"
    channel_name = "InsuranceHotline.com"
    channel_category = "Broker"

    city_url_template = None
    fallback_url = "https://www.insurancehotline.com/car-insurance-quotes-ontario"

    required_fields = []

    _BANDS = (
        ("gta", r"in the GTA[^.]*?\$\s*(\d[\d,]{2,})", "GTA average"),
        ("urban", r"other urban areas[^.]*?\$\s*(\d[\d,]{2,})", "urban Ontario average"),
        ("rural", r"rural Ontario[^.]*?\$\s*(\d[\d,]{2,})", "rural Ontario average"),
        ("province", r"province-wide[^.]*?\$\s*(\d[\d,]{2,})", "Ontario average"),
    )

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        flat = re.sub(r"\s+", " ", text)

        bands: Dict[str, float] = {}
        labels: Dict[str, str] = {}
        for key, pattern, label in self._BANDS:
            match = re.search(pattern, flat, re.I)
            if match:
                bands[key] = float(match.group(1).replace(",", ""))
                labels[key] = label

        if not bands:
            return {"annual_premium": None, "headline": None, "comparisons": []}

        region = region_for(self.slugify_city(applicant_data.get("city")))
        chosen = region if region in bands else ("province" if "province" in bands else next(iter(bands)))
        annual = bands[chosen]

        comparisons = [
            {"label": labels[key], "annual": value, "note": ""}
            for key, value in bands.items()
            if key != chosen
        ]

        city = applicant_data.get("city") or "Ontario"
        headline = (
            f"InsuranceHotline.com puts the {labels[chosen]} at ${annual:,.0f}/yr, "
            f"which is the band {city} falls into."
        )

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": f"{labels[chosen]} (region: {chosen})",
        }
