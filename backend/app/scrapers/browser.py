# backend/app/scrapers/browser.py
"""One browser for the whole run.

Launching a Chromium per channel meant ten process spawns for a single quote,
which is where the run spent most of its CPU and all of its memory. A browser
process is expensive; a browser *context* is nearly free and gives the same
isolation -- separate cookies, storage and cache per channel.

The semaphore caps how many pages render at once. The channels are mostly
waiting on the network, but page layout is CPU-bound, and letting all ten paint
simultaneously is what made the rest of the machine stutter.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

#: Pages rendering at once. Measured: 6 beats 10 on this workload -- past six the
#: pages contend for CPU and every one of them gets slower, which pushes the
#: first result out even though the last one lands at about the same time.
DEFAULT_CONCURRENCY = 6

# Ad, analytics and session-replay hosts. These are pure latency: they load slowly,
# never affect the rate figures, and several of them alone add seconds per page.
# Images and fonts are deliberately NOT blocked -- the screenshots are evidence and
# have to look like the page a person would see.
NOISE_HOSTS = (
    "doubleclick.net", "googletagmanager.com", "google-analytics.com",
    "googlesyndication.com", "facebook.net", "hotjar.com", "clarity.ms",
    "segment.com", "sentry.io", "teads.tv", "adsrvr.org", "bing.com",
    "taboola.com", "outbrain.com", "quantserve.com", "scorecardresearch.com",
)


async def _block_noise(route) -> None:
    url = route.request.url
    if any(host in url for host in NOISE_HOSTS) or route.request.resource_type == "media":
        try:
            await route.abort()
        except Exception:
            pass
        return
    try:
        await route.continue_()
    except Exception:
        pass


class BrowserPool:
    def __init__(self, *, headless: bool = True, concurrency: int = DEFAULT_CONCURRENCY):
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(concurrency)

    async def _ensure_browser(self):
        # Double-checked: the fast path avoids taking the lock once we're warm.
        if self._browser is not None:
            return self._browser
        async with self._lock:
            if self._browser is None:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self._headless,
                    args=["--disable-dev-shm-usage", "--no-sandbox"],
                )
                logger.info("browser pool: launched shared chromium")
        return self._browser

    @asynccontextmanager
    async def page(self, *, block_noise: bool = True):
        """A page in its own context. Closed on exit whatever happens."""
        browser = await self._ensure_browser()
        async with self._sem:
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="en-CA",
                viewport={"width": 1280, "height": 900},
            )
            try:
                page = await context.new_page()
                if block_noise:
                    await page.route("**/*", _block_noise)
                yield page
            finally:
                await context.close()

    async def aclose(self):
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
