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

    #: Where this channel takes the applicant's location. Every one of these
    #: sites has a quote box; typing into it is the entry step we screenshot.
    postal_selectors: List[str] = [
        "#postal-code",
        "#postal_code",
        "#postal-code-input",
        "input[name='postal_code']",
        "input[placeholder*='postal' i]",
    ]

    @abstractmethod
    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return ``{annual_premium, headline, comparisons}`` for this channel.

        ``annual_premium`` must be ``None`` when the page carries no figure for
        this profile; never fall back to a nominal value.
        """

    async def enter_profile(self, page, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Type the applicant's details into this site's own quote form.

        The base implementation fills the postal code, which is the one input
        every one of these sites exposes without demanding a name and phone
        number. Channels with a real multi-step funnel override this.
        """
        postal = str(applicant_data.get("postal_code") or "").strip().upper()
        if not postal:
            return {"entered": {}, "note": "no postal code to enter"}

        for selector in self.postal_selectors:
            try:
                # `:visible` skips the duplicate inputs these sites hide in
                # collapsed mobile headers, which is what fill() was hitting.
                field = page.locator(f"{selector}:visible")
                # Cheap existence check first. A site with no postal box at all
                # (HelloSafe, isure) used to burn 6s per selector here -- 30s of
                # dead waiting on a page that was never going to have one.
                if await field.count() == 0:
                    continue
                target = field.first
                # Frame the box before shooting it. Without this the "entry
                # proof" was a screenshot of whatever part of the page happened
                # to be scrolled into view, which proves nothing was entered.
                await target.scroll_into_view_if_needed(timeout=2000)
                await target.fill(postal, timeout=2500)
                # fill() sets the value without firing the events these sites
                # validate on -- Rates.ca leaves its submit button disabled after
                # a fill but enables it after real keystrokes. Nudging the same
                # events keeps the field in the state the site expects.
                await target.evaluate(
                    "el => { el.dispatchEvent(new Event('input', {bubbles:true}));"
                    " el.dispatchEvent(new Event('change', {bubbles:true})); }"
                )
                await page.wait_for_timeout(250)
                await self.capture_entry(page, "postal")
                return {"entered": {"postal_code": postal}, "selector": selector}
            except Exception:
                continue

        return {"entered": {}, "note": "no postal input found on this page"}

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
                        await page.wait_for_timeout(2200)
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

                    # Entry runs last because a real funnel navigates away from the
                    # rate page, and the result screenshot has to be taken while
                    # we are still standing on the figure it proves.
                    entry = await self.enter_profile(page, applicant_data)

                    payload = {
                        "source_url": url,
                        "attempts": attempts,
                        "headline": parsed.get("headline"),
                        "comparisons": parsed.get("comparisons", []),
                        "matched_on": parsed.get("matched_on"),
                        "entered": entry.get("entered", {}),
                        "entry_note": entry.get("note"),
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


# Ontario annual auto premiums live in this band. Anything below is a monthly
# figure, a deductible or a discount; anything above is a coverage limit. These
# pages print all of those next to each other, and picking the first dollar sign
# after a city name once reported a $239 monthly rate as an annual premium --
# which made that source look like the cheapest by a factor of ten.
ANNUAL_MIN = 700.0
ANNUAL_MAX = 15000.0


def plausible_annual(value: Optional[float]) -> bool:
    """Is this figure credible as an annual Ontario premium?"""
    return value is not None and ANNUAL_MIN <= value <= ANNUAL_MAX


def first_plausible_annual(pattern: str, text: str, flags: int = re.I) -> Optional[tuple]:
    """First match whose captured amount is a credible annual premium.

    Returns ``(amount, matched_text)`` or ``None``. Scanning past implausible
    matches is what separates "the number near the city name" from "the city's
    annual premium".
    """
    for match in re.finditer(pattern, text, flags):
        try:
            amount = float(match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            continue
        if plausible_annual(amount):
            return amount, match.group(0)
    return None


def lines_with_money(text: str, *, keywords: str) -> List[str]:
    """Lines carrying both a 3+ digit dollar figure and one of `keywords`."""
    hits = []
    for line in text.splitlines():
        line = line.strip()
        if re.search(r"\$\s*\d[\d,]{2,}", line) and re.search(keywords, line, re.I):
            hits.append(line)
    return hits
