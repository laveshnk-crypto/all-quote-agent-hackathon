# backend/app/scrapers/base_scraper.py
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
import json
import os
import re
import uuid
from datetime import datetime, timezone

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

#: Screenshots are served to the browser from here (see app/main.py).
ARTIFACT_URL_PREFIX = "/artifacts"

# How closely a figure was matched to *this* applicant, best first. A quote is
# only as good as what it was matched on, and a province-wide average dressed up
# as "your quote" is the most misleading thing this pipeline could produce -- so
# every result has to declare which of these it is, and the UI shows it.
PERSONALISATION = {
    "profile":  "Your full profile",
    "postal":   "Your postal area",
    "age":      "Your age band",
    "vehicle":  "Your vehicle",
    "city":     "Your city",
    "region":   "Your region",
    "province": "Province-wide average",
}
PERSONALISATION_RANK = {key: i for i, key in enumerate(PERSONALISATION)}

#: Anything at or below this rank is a generic figure, not a quote for this person.
GENERIC_FROM = PERSONALISATION_RANK["region"]


class BaseScraper(ABC):
    channel_id: str
    channel_name: str
    channel_category: str  # Direct, Aggregator, Broker, Regulatory, Affinity

    # Keys from the intake profile this channel actually reads. A channel is
    # never run with a value it wasn't given -- it reports REJECTED instead of
    # quietly substituting a placeholder, which would produce a fake quote.
    required_fields: List[str] = []

    # Why this channel cannot match more closely than it does -- a blocked
    # funnel, a page that only publishes averages. Surfaced in the results table
    # so a generic figure always arrives with its reason attached.
    limit_note: Optional[str] = None

    # This site's dialect: canonical token -> the exact string this site's form
    # uses. Declared per scraper so one applicant answer reaches every site in
    # that site's own words. See app/scrapers/profile.py.
    VALUE_MAP: Dict[str, Dict[Any, str]] = {}

    def __init__(self, screenshot_dir: str = "app/scrapers/screenshots", pool=None):
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)
        #: Shared BrowserPool. Without one the channel launches its own browser,
        #: which is correct but ten times more expensive across a full run.
        self.pool = pool
        #: Screenshots taken while filling this channel's form, in order.
        self.entry_shots: List[str] = []

    @abstractmethod
    async def execute(self, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Must be implemented by child classes.
        Returns a dictionary containing execution results and evidence.
        """
        pass

    def missing_fields(self, applicant_data: Dict[str, Any]) -> List[str]:
        """Required keys the profile does not supply a usable value for."""
        return [
            key
            for key in self.required_fields
            if applicant_data.get(key) in (None, "", [])
        ]

    def require(self, applicant_data: Dict[str, Any], key: str) -> Any:
        """Read a required field, refusing to invent one.

        Every channel takes its inputs through here so that a missing answer can
        never silently become a stand-in value and a plausible-looking quote.
        """
        value = applicant_data.get(key)
        if value in (None, "", []):
            raise MissingProfileField(key)
        return value

    @asynccontextmanager
    async def browser_page(self, *, headless: bool = True):
        """Chromium page with a desktop UA. These sites 403 plain HTTP clients.

        Uses the shared pool when the registry supplied one; falls back to a
        private browser so a channel can still be run on its own in a test.
        """
        if self.pool is not None:
            async with self.pool.page() as page:
                yield page
            return

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-CA",
                    viewport={"width": 1280, "height": 900},
                )
                page = await context.new_page()
                yield page
            finally:
                await browser.close()

    async def capture_entry(self, page, label: str) -> Optional[str]:
        """Screenshot the form we just filled, as proof the data was entered.

        Distinct from the result screenshot: this shows *our* answers sitting in
        the site's own fields, before anything is calculated.
        """
        path = await self.capture(page, suffix=f"entry_{label}")
        if path:
            self.entry_shots.append(path)
        return path

    def site_value(self, field: str, token: Any, default: Optional[str] = None) -> Optional[str]:
        """Translate a canonical token into this site's wording.

        Returns ``None`` when this site has no equivalent, which is a real
        answer -- the field is left alone rather than guessed at.
        """
        return self.VALUE_MAP.get(field, {}).get(token, default)

    @staticmethod
    async def set_select(page, selector: str, value: str, *, by: str = "label") -> bool:
        """Best-effort <select> set. Returns whether it took."""
        try:
            locator = page.locator(selector).first
            if by == "label":
                await locator.select_option(label=value, timeout=6000)
            elif by == "value":
                await locator.select_option(value=value, timeout=6000)
            else:
                await locator.select_option(index=int(value), timeout=6000)
            return True
        except Exception:
            return False

    @staticmethod
    def nearest_option(options: List[str], target: float) -> Optional[str]:
        """Pick the option whose embedded number is closest to `target`.

        Sites express the same answer in incompatible buckets ("10,000 KM",
        "10-15k"); matching on the number rather than the string keeps one
        applicant answer usable across all of them.
        """
        best, best_gap = None, float("inf")
        for option in options:
            match = re.search(r"[\d,]+", option)
            if not match:
                continue
            try:
                value = float(match.group().replace(",", ""))
            except ValueError:
                continue
            gap = abs(value - target)
            if gap < best_gap:
                best, best_gap = option, gap
        return best

    async def focus_on_amount(self, page, amount: Optional[float]) -> bool:
        """Scroll the reported figure into view so the screenshot actually shows it.

        A screenshot of a page's hero banner proves nothing about the number we
        extracted from halfway down it.
        """
        if amount is None:
            return False

        # Try the ways sites render the same figure: "$2,348", "$2,348.00", "2,348".
        candidates = [
            f"${amount:,.0f}",
            f"${amount:,.2f}",
            f"{amount:,.0f}",
        ]
        for needle in candidates:
            try:
                locator = page.get_by_text(needle, exact=False)
                # count() resolves immediately. Going straight to scroll meant
                # three misses cost 10s of dead waiting per channel, which was a
                # large part of why channels ran out of time.
                if await locator.count() == 0:
                    continue
                await locator.first.scroll_into_view_if_needed(timeout=1500)
                await page.wait_for_timeout(300)
                return True
            except Exception:
                continue
        return False

    async def capture(self, page, *, suffix: str = "", amount: Optional[float] = None) -> Optional[str]:
        """Screenshot the current page. Never raises -- proof is best-effort.

        Pass ``amount`` to scroll the reported figure into frame first.
        """
        if amount is not None:
            await self.focus_on_amount(page, amount)
        try:
            shot = await page.screenshot(full_page=False)
        except Exception:
            return None
        prefix = f"{self.channel_id}_{suffix}" if suffix else self.channel_id
        return self.save_screenshot_artifact(shot, prefix=prefix)

    def save_screenshot_artifact(self, page_bytes: bytes, prefix: str = "evidence") -> str:
        """Saves screenshot bytes to disk for visual evidence audits."""
        filename = f"{prefix}_{self.channel_id}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        with open(filepath, "wb") as f:
            f.write(page_bytes)
        return filepath

    def save_json_artifact(self, payload: Dict[str, Any], prefix: str = "evidence") -> str:
        """Saves structured JSON payloads to disk next to screenshots."""
        filename = f"{prefix}_{self.channel_id}_{uuid.uuid4().hex[:8]}.json"
        filepath = os.path.join(self.screenshot_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return filepath

    @staticmethod
    def parse_money(text: Optional[str]) -> Optional[float]:
        """First dollar figure in a string -> float. '$2,167/yr' -> 2167.0"""
        if not text:
            return None
        match = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", text)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def slugify_city(city: Optional[str]) -> Optional[str]:
        """'St. Catharines' -> 'st-catharines', for city-scoped rate pages."""
        if not city:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", str(city).strip().lower()).strip("-")
        return slug or None

    def build_result(
        self,
        status: str,  # SUCCESS, BLOCKED_CAPTCHA, PHONE_REQUIRED, REJECTED, SYSTEM_ERROR
        annual_premium: Optional[float] = None,
        monthly_premium: Optional[float] = None,
        evidence_summary: Optional[str] = None,
        evidence_payload: Optional[Dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
        personalisation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ensures every route returns standardized evidence fields.

        A non-SUCCESS status always carries a null premium -- there is no
        fallback figure anywhere in this pipeline.
        """
        if status != "SUCCESS":
            annual_premium = None
            monthly_premium = None
            personalisation = None

        level = personalisation if personalisation in PERSONALISATION else None
        rank = PERSONALISATION_RANK.get(level) if level else None

        return {
            "personalisation": level,
            "personalisation_label": PERSONALISATION.get(level) if level else None,
            "limit_note": self.limit_note,
            # True when the figure describes a population rather than this person.
            "is_generic": (rank is not None and rank >= GENERIC_FROM),
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_category": self.channel_category,
            "status": status,
            "annual_premium": annual_premium,
            "monthly_premium": monthly_premium
            or (round(annual_premium / 12, 2) if annual_premium else None),
            "evidence_summary": evidence_summary,
            "evidence_payload": evidence_payload or {},
            "screenshot_path": screenshot_path,
            # Browser-facing URLs for the same files, so the UI can show proof.
            "screenshot_url": (
                f"{ARTIFACT_URL_PREFIX}/{os.path.basename(screenshot_path)}"
                if screenshot_path
                else None
            ),
            "entry_screenshot_urls": [
                f"{ARTIFACT_URL_PREFIX}/{os.path.basename(p)}" for p in self.entry_shots
            ],
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


class MissingProfileField(Exception):
    """Raised by `require` when a channel has no value for a field it needs."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"missing required profile field: {field}")
