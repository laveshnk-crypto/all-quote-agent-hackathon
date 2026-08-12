# backend/app/scrapers/surex.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper


class SurexScraper(RatePageScraper):
    """Surex is a brokerage; their auto page carries sample monthly premiums.

    There is no per-profile matching available here, so this channel reports the
    cheapest published sample as its figure and shows the rest as context.
    """

    channel_id = "surex"
    channel_name = "Surex.com"
    channel_category = "Broker"

    city_url_template = None
    fallback_url = "https://www.surex.com/insurance/auto"

    required_fields = []

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        monthly = {
            float(value.replace(",", ""))
            for value in re.findall(r"\$\s*([\d,]+(?:\.\d+)?)\s*/\s*month", text, re.I)
        }
        # Guard against picking up coverage limits or unrelated figures.
        plausible = sorted(m for m in monthly if 40 <= m <= 1200)

        if not plausible:
            return {"annual_premium": None, "headline": None, "comparisons": []}

        cheapest = plausible[0]
        annual = round(cheapest * 12, 2)

        return {
            "annual_premium": annual,
            "headline": (
                f"Surex publishes sample Ontario premiums from ${cheapest:,.0f}/month "
                f"(${annual:,.0f}/yr)."
            ),
            "comparisons": [
                {
                    "label": f"${m:,.0f}/month sample",
                    "annual": round(m * 12, 2),
                    "note": "published sample",
                }
                for m in plausible[1:5]
            ],
            "matched_on": "cheapest published sample (not profile-matched)",
        }
