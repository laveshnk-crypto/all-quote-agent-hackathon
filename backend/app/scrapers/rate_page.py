# backend/app/scrapers/rate_page.py
"""Shared machinery for channels that publish rate data on a public page.

Most of our channels work the same way: load a city- or province-scoped page,
read the averages the site publishes, and match the closest figure to the
applicant. Only the parsing differs, so subclasses implement `parse` and the
plumbing (browser, screenshot proof, error handling) lives here.

Every exit path captures a screenshot, including the failures -- a channel that
reports "no rate" should be able to show you the page it looked at.
"""
import re
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from app.scrapers.base_scraper import BaseScraper

# The GTA carries materially different rates than the rest of Ontario, so
# several channels report them as separate bands.
GTA_CITIES = {
    "toronto", "north-york", "scarborough", "etobicoke", "york", "east-york",
    "mississauga", "brampton", "caledon", "markham", "vaughan", "richmond-hill",
    "aurora", "newmarket", "king-city", "whitchurch-stouffville", "georgina",
    "pickering", "ajax", "whitby", "oshawa", "clarington", "uxbridge",
    "oakville", "burlington", "milton", "halton-hills",
}

OTHER_URBAN_CITIES = {
    "ottawa", "hamilton", "london", "kitchener", "waterloo", "cambridge",
    "windsor", "kingston", "guelph", "barrie", "sudbury", "thunder-bay",
    "st-catharines", "niagara-falls", "peterborough", "belleville", "sarnia",
    "brantford",
}


def region_for(city_slug: Optional[str]) -> str:
    """Classify a city into the bands these channels report against."""
    if not city_slug:
        return "province"
    if city_slug in GTA_CITIES:
        return "gta"
    if city_slug in OTHER_URBAN_CITIES:
        return "urban"
    return "rural"


class RatePageScraper(BaseScraper):
    #: ``str.format``-style template taking ``{city}``.
    city_url_template: Optional[str] = None
    #: Used when we have no city, or the city-scoped page 404s.
    fallback_url: str = ""

    required_fields = ["city"]

    def build_urls(self, applicant_data: Dict[str, Any]) -> List[str]:
        """City page first, province page as the backstop."""
        urls: List[str] = []
        city = self.slugify_city(applicant_data.get("city"))
        if city and self.city_url_template:
            urls.append(self.city_url_template.format(city=city))
        if self.fallback_url:
            urls.append(self.fallback_url)
        return urls

    @abstractmethod
    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return ``{annual_premium, headline, comparisons}`` for this channel.

        ``annual_premium`` must be ``None`` when the page carries no figure for
        this profile; never fall back to a nominal value.
        """

    async def execute(self, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        missing = self.missing_fields(applicant_data)
        if missing:
            return self.build_result(
                status="REJECTED",
                evidence_summary=(
                    f"{self.channel_name} needs {', '.join(missing)}, which the profile "
                    "does not include."
                ),
                evidence_payload={"missing_fields": missing},
            )

        urls = self.build_urls(applicant_data)
        if not urls:
            return self.build_result(
                status="REJECTED",
                evidence_summary=f"No {self.channel_name} page matches this profile.",
            )

        attempts: List[Dict[str, Any]] = []
        screenshot_path = None

        try:
            async with self.browser_page() as page:
                for url in urls:
                    try:
                        response = await page.goto(
                            url, wait_until="domcontentloaded", timeout=40000
                        )
                        status_code = response.status if response else None
                        await page.wait_for_timeout(3000)
                    except Exception as exc:  # navigation/timeout on this candidate
                        attempts.append({"url": url, "error": str(exc)[:160]})
                        continue

                    if status_code and status_code >= 400:
                        # Proof of what we looked at, even when it's a 404.
                        screenshot_path = await self.capture(page)
                        attempts.append({"url": url, "http_status": status_code})
                        continue

                    text = await page.inner_text("body")
                    tables = await page.eval_on_selector_all(
                        "table tr",
                        "els => els.map(e => [...e.querySelectorAll('th,td')]"
                        ".map(c => c.innerText.replace(/\\s+/g,' ').trim()))",
                    )

                    parsed = self.parse(text, tables, applicant_data)
                    attempts.append({"url": url, "http_status": status_code, "parsed": True})

                    if parsed.get("annual_premium") is None:
                        # Page loaded but the numbers we key off weren't there.
                        screenshot_path = await self.capture(page)
                        continue

                    # Frame the figure we're about to report, so the screenshot
                    # is evidence for this number rather than of the page's hero.
                    screenshot_path = await self.capture(
                        page, amount=parsed["annual_premium"]
                    )

                    payload = {
                        "source_url": url,
                        "attempts": attempts,
                        "headline": parsed.get("headline"),
                        "comparisons": parsed.get("comparisons", []),
                        "matched_on": parsed.get("matched_on"),
                        "applicant_profile": applicant_data,
                    }
                    payload["results_file_path"] = self.save_json_artifact(
                        payload, prefix=f"{self.channel_id}_results"
                    )

                    return self.build_result(
                        status="SUCCESS",
                        annual_premium=parsed["annual_premium"],
                        evidence_summary=parsed.get("headline")
                        or f"{self.channel_name} published rate data.",
                        evidence_payload=payload,
                        screenshot_path=screenshot_path,
                    )

            return self.build_result(
                status="REJECTED",
                evidence_summary=(
                    f"{self.channel_name} loaded but published no rate figure for this profile."
                ),
                evidence_payload={"attempts": attempts},
                screenshot_path=screenshot_path,
            )

        except Exception as exc:
            return self.build_result(
                status="SYSTEM_ERROR",
                evidence_summary=f"{self.channel_name} automation error: {exc}",
                evidence_payload={"error": str(exc), "attempts": attempts},
                screenshot_path=screenshot_path,
            )


def lines_with_money(text: str, *, keywords: str) -> List[str]:
    """Lines carrying both a 3+ digit dollar figure and one of `keywords`."""
    hits = []
    for line in text.splitlines():
        line = line.strip()
        if re.search(r"\$\s*\d[\d,]{2,}", line) and re.search(keywords, line, re.I):
            hits.append(line)
    return hits
