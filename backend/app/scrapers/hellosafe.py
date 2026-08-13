# backend/app/scrapers/hellosafe.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper, lines_with_money, plausible_annual


class HelloSafeScraper(RatePageScraper):
    """HelloSafe publishes worked sample quotes alongside city averages.

    Their Ontario page carries a two-column comparison of fully specified
    driver profiles (age, vehicle, city, mileage) with annual costs, plus a set
    of per-city averages we can match the applicant's city against.
    """

    channel_id = "hellosafe"
    channel_name = "HelloSafe.ca"
    channel_category = "Aggregator"

    city_url_template = None
    fallback_url = "https://hellosafe.ca/en/car-insurance/ontario"

    required_fields = []

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        flat = re.sub(r"\s+", " ", text)
        city = str(applicant_data.get("city") or "").strip()

        annual = None
        headline = None
        matched_on = None

        # Prefer a figure for the applicant's own city: HelloSafe lists them as
        # "Toronto, Mississauga and Brampton came in ... at $1,953, $1,971 and $1,976".
        if city:
            for sentence in re.split(r"(?<=[.!?])\s+", flat):
                if city.lower() not in sentence.lower():
                    continue
                cities = re.findall(r"\b([A-Z][a-zA-Z.\- ]{2,24})\b(?=,| and | came)", sentence)
                amounts = [
                    float(a.replace(",", "")) for a in re.findall(r"\$\s*(\d[\d,]{2,})", sentence)
                ]
                names = [c.strip() for c in cities]
                if names and amounts and len(names) == len(amounts):
                    for name, amount in zip(names, amounts):
                        if name.lower() == city.lower():
                            annual, headline = amount, sentence[:220]
                            matched_on = f"HelloSafe city average for {name}"
                            break
                if annual:
                    break

        # Otherwise the province-wide average.
        if annual is None:
            for line in lines_with_money(text, keywords=r"average car insurance|average cost"):
                match = re.search(r"\$\s*(\d[\d,]{2,})\s*(?:per year|annually|a year)", line, re.I)
                if match:
                    annual = float(match.group(1).replace(",", ""))
                    headline = line[:220]
                    matched_on = "HelloSafe Ontario average"
                    break

        # The sample-profile table gives concrete worked examples to compare to.
        comparisons: List[Dict[str, Any]] = []
        profiles = next((r for r in tables if r and re.match(r"driver", r[0] or "", re.I)), None)
        costs = next((r for r in tables if r and re.match(r"cost per year", r[0] or "", re.I)), None)
        if profiles and costs:
            for label, cost in zip(profiles[1:], costs[1:]):
                amount = self.parse_money(cost)
                if amount:
                    comparisons.append(
                        {"label": label[:60], "annual": amount, "note": "sample profile"}
                    )

        # A figure outside the credible annual band is a monthly rate or a
        # coverage limit that happened to sit near the words we matched on.
        if not plausible_annual(annual):
            annual = None

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": matched_on,
        }
