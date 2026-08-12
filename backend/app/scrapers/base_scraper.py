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


class BaseScraper(ABC):
    channel_id: str
    channel_name: str
    channel_category: str  # Direct, Aggregator, Broker, Regulatory, Affinity

    # Keys from the intake profile this channel actually reads. A channel is
    # never run with a value it wasn't given -- it reports REJECTED instead of
    # quietly substituting a placeholder, which would produce a fake quote.
    required_fields: List[str] = []

    def __init__(self, screenshot_dir: str = "app/scrapers/screenshots"):
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)

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
        """Chromium page with a desktop UA. These sites 403 plain HTTP clients."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context(user_agent=USER_AGENT, locale="en-CA")
                page = await context.new_page()
                yield page
            finally:
                await browser.close()

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
                locator = page.get_by_text(needle, exact=False).first
                await locator.scroll_into_view_if_needed(timeout=3500)
                await page.wait_for_timeout(400)
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
    ) -> Dict[str, Any]:
        """Ensures every route returns standardized evidence fields.

        A non-SUCCESS status always carries a null premium -- there is no
        fallback figure anywhere in this pipeline.
        """
        if status != "SUCCESS":
            annual_premium = None
            monthly_premium = None

        return {
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
            # Browser-facing URL for the same file, so the UI can show proof.
            "screenshot_url": (
                f"{ARTIFACT_URL_PREFIX}/{os.path.basename(screenshot_path)}"
                if screenshot_path
                else None
            ),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


class MissingProfileField(Exception):
    """Raised by `require` when a channel has no value for a field it needs."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"missing required profile field: {field}")
