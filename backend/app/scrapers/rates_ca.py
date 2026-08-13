# backend/app/scrapers/rates_ca.py
import re
from typing import Any, Dict, List

from app.scrapers.rate_page import RatePageScraper, lines_with_money, plausible_annual


class RatesCaScraper(RatePageScraper):
    """Rates.ca, read from their published city rate pages.

    Their live quote funnel is not usable, and this is worth writing down so it
    is not re-attempted. Entering a postal code on rates.ca and pressing "Get My
    Quote" hands off to ``quotes.rates.ca/autoquote``, which answers **HTTP 403**
    behind a Cloudflare "Verify you are human" challenge. It does not clear on
    its own -- checked repeatedly over 36 seconds -- and getting past it would
    mean defeating a bot-protection control, which this project does not do.

    Note the postal box also needs real key events: ``fill()`` sets the value but
    leaves the submit button ``disabled``, because the site enables it from
    keystrokes. Typing works. That only matters if someone revisits this.

    So this channel reads the city page, which is public, un-gated, and carries
    the figure we actually want: the city's average annual premium plus a ranked
    table of neighbouring cities.
    """

    channel_id = "rates_ca"
    channel_name = "Rates.ca"
    channel_category = "Aggregator"

    limit_note = (
        "Their live quote funnel is behind a Cloudflare bot check (HTTP 403), so this "
        "is their published rate for your postal area rather than a personal quote."
    )

    city_url_template = "https://rates.ca/insurance-quotes/auto/{city}"
    fallback_url = "https://rates.ca/insurance-quotes/auto"

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        annual = None
        headline = None
        matched_on = "city average"

        # Best available: this page lists an annual premium per forward sortation
        # area, so quote the applicant's own postal area rather than the whole
        # city. Across Toronto these run $2,510-$4,026 against a $2,888 city
        # average, so the difference is worth having.
        fsa = str(applicant_data.get("postal_code") or "").upper().replace(" ", "")[:3]
        if re.fullmatch(r"[A-Z]\d[A-Z]", fsa):
            by_fsa = {
                area: float(amount.replace(",", ""))
                for area, amount in re.findall(
                    r"\b([A-Z]\d[A-Z])\b[^\n]{0,60}?\$\s*([\d,]{3,})", text
                )
            }
            found = by_fsa.get(fsa)
            if plausible_annual(found):
                annual = found
                matched_on = f"postal area {fsa}"
                ranked = sorted(by_fsa.values())
                position = ranked.index(found) + 1
                headline = (
                    f"Rates.ca puts {fsa} at ${found:,.0f}/yr -- {position} of "
                    f"{len(ranked)} postal areas they list for this city, which "
                    f"span ${ranked[0]:,.0f} to ${ranked[-1]:,.0f}."
                )

        # Otherwise the city-wide figure: "The average cost of car insurance in
        # Toronto-proper is $2,888 per year".
        if annual is None:
            for line in lines_with_money(
                text, keywords=r"average cost|average annual|average premium"
            ):
                match = re.search(
                    r"\$\s*(\d[\d,]{2,})\s*(?:per year|annually|a year)?", line, re.I
                )
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

        # A figure outside the credible annual band is a monthly rate or a
        # coverage limit that happened to sit near the words we matched on.
        if not plausible_annual(annual):
            annual = None

        return {
            "annual_premium": annual,
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": matched_on if annual else None,
            "personalisation": (
                ("postal" if matched_on.startswith("postal") else "city")
                if annual else None
            ),
        }
