# backend/app/scrapers/rates_ca.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper, lines_with_money


class RatesCaScraper(RatePageScraper):
    channel_id = "rates_ca"
    channel_name = "Rates.ca"
    channel_category = "Aggregator"

    city_url_template = "https://rates.ca/insurance-quotes/auto/{city}"
    fallback_url = "https://rates.ca/insurance-quotes/auto"

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        annual = None
        headline = None

        # "The average cost of car insurance in Toronto-proper is $2,888 per year"
        for line in lines_with_money(text, keywords=r"average cost|average annual|average premium"):
            match = re.search(r"\$\s*(\d[\d,]{2,})\s*(?:per year|annually|a year)?", line, re.I)
            if match:
                annual = float(match.group(1).replace(",", ""))
                headline = line[:200]
                break

        # Rates.ca ranks neighbouring cities: "1 Burlington $2,109 26.97% lower".
        comparisons: List[Dict[str, Any]] = []
        for row in tables:
            if len(row) < 3:
                continue
            joined = " ".join(row)
            if not re.search(r"\$\s*\d[\d,]{2,}", joined):
                continue
            city = next((c for c in row if c and not re.search(r"[\d$%]", c)), None)
            amount = self.parse_money(joined)
            if city and amount:
                note = next((c for c in row if "%" in c), "")
                comparisons.append({"label": city, "annual": amount, "note": note})
            if len(comparisons) >= 6:
                break

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": "city average" if annual else None,
        }
