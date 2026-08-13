# backend/app/scrapers/registry.py
"""All quote channels, and the fan-out that runs them together.

Channels are independent and every one of them drives a browser, so running
them sequentially would take minutes. They run concurrently with a per-channel
timeout, and a channel that fails never takes the others down with it.

A channel that cannot produce a real figure returns a null premium. Nothing in
this pipeline substitutes a nominal or example value for a missing answer.
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.browser import BrowserPool
from app.scrapers.fsra_benchmark import FSRABenchmarkScraper
from app.scrapers.hellosafe import HelloSafeScraper
from app.scrapers.insurancehotline import InsuranceHotlineScraper
from app.scrapers.isure import IsureScraper
from app.scrapers.lowestrates import LowestRatesScraper
from app.scrapers.mychoice import MyChoiceScraper
from app.scrapers.mychoice_index import MyChoiceIndexScraper
from app.scrapers.ratehub import RatehubScraper
from app.scrapers.rates_ca import RatesCaScraper
from app.scrapers.surex import SurexScraper

logger = logging.getLogger(__name__)

SCRAPERS: List[Type[BaseScraper]] = [
    FSRABenchmarkScraper,
    LowestRatesScraper,
    RatesCaScraper,
    RatehubScraper,
    InsuranceHotlineScraper,
    MyChoiceScraper,
    MyChoiceIndexScraper,
    HelloSafeScraper,
    SurexScraper,
    IsureScraper,
]

# How long a channel gets *once it starts working*. This deliberately excludes
# time spent queued for a browser slot: measuring from task creation meant the
# channels behind the queue spent their whole budget waiting and every one of
# them timed out together, which is the opposite of a per-channel timeout.
CHANNEL_TIMEOUT_S = 120.0

# Channels actively driving a browser at once. The rest queue for a slot, and
# their clock does not start until they get one.
#
# Four rather than six: this runs on the same machine as the voice session, and
# six pages laying out simultaneously starved the audio pipeline enough to make
# the agent's speech stutter. The full run is only a couple of seconds slower.
CHANNEL_CONCURRENCY = 4


def channel_directory() -> List[Dict[str, Any]]:
    """Static description of every channel, for docs and the intake prompt."""
    return [
        {
            "channel_id": cls.channel_id,
            "channel_name": cls.channel_name,
            "channel_category": cls.channel_category,
            "required_fields": list(cls.required_fields),
        }
        for cls in SCRAPERS
    ]


async def _run_one(
    cls: Type[BaseScraper],
    applicant_data: Dict[str, Any],
    screenshot_dir: Optional[str],
    pool: Optional[BrowserPool] = None,
    gate: Optional[asyncio.Semaphore] = None,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"pool": pool}
    if screenshot_dir:
        kwargs["screenshot_dir"] = screenshot_dir
    scraper = cls(**kwargs)
    try:
        # Queue for a slot *outside* the timeout, so the clock measures this
        # channel's own work rather than how busy the others were.
        if gate is not None:
            await gate.acquire()
        try:
            return await asyncio.wait_for(
                scraper.execute(applicant_data), timeout=CHANNEL_TIMEOUT_S
            )
        finally:
            if gate is not None:
                gate.release()
    except asyncio.TimeoutError:
        logger.warning("%s timed out after %ss", cls.channel_id, CHANNEL_TIMEOUT_S)
        return scraper.build_result(
            status="SYSTEM_ERROR",
            evidence_summary=f"{cls.channel_name} timed out after {CHANNEL_TIMEOUT_S:.0f}s.",
            evidence_payload={"error": "timeout"},
        )
    except Exception as exc:  # a channel must never sink the whole run
        logger.exception("%s raised", cls.channel_id)
        return scraper.build_result(
            status="SYSTEM_ERROR",
            evidence_summary=f"{cls.channel_name} failed: {exc}",
            evidence_payload={"error": str(exc)},
        )


async def run_all_channels(
    applicant_data: Dict[str, Any],
    *,
    screenshot_dir: Optional[str] = None,
    only: Optional[List[str]] = None,
    on_result: Optional[Callable[[Dict[str, Any], int, int], Awaitable[None]]] = None,
) -> List[Dict[str, Any]]:
    """Run every channel concurrently and return all results, successes first.

    ``on_result`` is awaited as each channel lands, so the UI can fill in
    progressively instead of staring at a spinner until the slowest one
    finishes. All channels share a single browser process.
    """
    selected = [c for c in SCRAPERS if not only or c.channel_id in only]
    total = len(selected)
    # The pool no longer gates concurrency; the registry does, so that queueing
    # happens before a channel's timeout starts.
    pool = BrowserPool(concurrency=len(selected) or 1)
    gate = asyncio.Semaphore(CHANNEL_CONCURRENCY)
    results: List[Dict[str, Any]] = []

    try:
        pending = [
            asyncio.create_task(_run_one(cls, applicant_data, screenshot_dir, pool, gate))
            for cls in selected
        ]
        for done in asyncio.as_completed(pending):
            result = await done
            results.append(result)
            if on_result is not None:
                try:
                    await on_result(result, len(results), total)
                except Exception:
                    logger.exception("on_result callback failed for %s", result.get("channel_id"))
    finally:
        # Never let teardown throw away results the channels already produced.
        try:
            await pool.aclose()
        except Exception:
            logger.exception("browser pool did not close cleanly")

    # Successes first, cheapest first within that; everything else keeps registry order.
    def sort_key(result: Dict[str, Any]) -> tuple:
        ok = result.get("status") == "SUCCESS"
        premium = result.get("annual_premium")
        return (0 if ok else 1, premium if ok and premium is not None else float("inf"))

    ordered = sorted(results, key=sort_key)

    # Flag the recommendation so the UI and the agent agree on one winner.
    cheapest_id = next(
        (r["channel_id"] for r in ordered if r.get("status") == "SUCCESS" and r.get("annual_premium")),
        None,
    )
    for result in ordered:
        result["is_recommended"] = result.get("channel_id") == cheapest_id

    return ordered


def summarise(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll the per-channel results into the headline numbers the agent speaks."""
    priced = [
        r for r in results if r.get("status") == "SUCCESS" and r.get("annual_premium")
    ]
    amounts = [r["annual_premium"] for r in priced]
    unavailable = [r["channel_name"] for r in results if r not in priced]

    return {
        "channels_run": len(results),
        "channels_with_a_price": len(priced),
        "channels_unavailable": unavailable,
        "cheapest_annual": min(amounts) if amounts else None,
        "cheapest_channel": (
            min(priced, key=lambda r: r["annual_premium"])["channel_name"] if priced else None
        ),
        "dearest_annual": max(amounts) if amounts else None,
        "average_annual": round(sum(amounts) / len(amounts), 2) if amounts else None,
        "spread_annual": round(max(amounts) - min(amounts), 2) if len(amounts) > 1 else None,
    }
