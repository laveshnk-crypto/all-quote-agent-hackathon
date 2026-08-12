# backend/app/scrapers/mychoice.py
"""MyChoice.ca publishes a client-side Ontario rate calculator.

Unlike the editorial channels this one is a real form: vehicle, driver age band,
claims and ticket history, plus what the driver pays today. It benchmarks the
current premium against MyChoice's aggregated Ontario quote data, so it only
runs when the applicant told us their current premium -- there is no sensible
stand-in for "what you pay now".
"""
import re
from typing import Any, Dict, List, Optional

from app.scrapers.base_scraper import BaseScraper

# The age <select> is index-valued: 0="16–20", 1="21–24", … 6="65+".
AGE_BANDS = [
    (20, "0"),
    (24, "1"),
    (34, "2"),
    (44, "3"),
    (54, "4"),
    (64, "5"),
    (200, "6"),
]


class MyChoiceScraper(BaseScraper):
    channel_id = "mychoice"
    channel_name = "MyChoice.ca Calculator"
    channel_category = "Aggregator"

    required_fields = [
        "age", "vehicle_year", "vehicle_make", "postal_code", "current_monthly_premium",
    ]

    url = "https://www.mychoice.ca/ontario-car-insurance-calculator/"

    @staticmethod
    def _age_band_label(age: int) -> str:
        for ceiling, value in AGE_BANDS:
            if age <= ceiling:
                return value
        return "6"

    @staticmethod
    def _labelled_amount(text: str, label: str) -> Optional[float]:
        """The calculator renders each figure on the line after its label."""
        lines = [line.strip() for line in text.splitlines()]
        for index, line in enumerate(lines):
            if re.fullmatch(label, line, re.I):
                for candidate in lines[index + 1 : index + 3]:
                    match = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", candidate)
                    if match:
                        return float(match.group(1).replace(",", ""))
        return None

    async def execute(self, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        missing = self.missing_fields(applicant_data)
        if missing:
            return self.build_result(
                status="REJECTED",
                evidence_summary=(
                    f"MyChoice.ca benchmarks against what you pay today; missing "
                    f"{', '.join(missing)}."
                ),
                evidence_payload={"missing_fields": missing},
            )

        age = int(applicant_data["age"])
        band = self._age_band_label(age)
        make = str(applicant_data["vehicle_make"]).strip().upper()
        year = str(applicant_data["vehicle_year"]).strip()
        premium = str(applicant_data["current_monthly_premium"]).strip()
        postal = str(applicant_data["postal_code"]).strip().upper()
        claim_free = int(applicant_data.get("at_fault_accidents") or 0) == 0
        no_tickets = int(applicant_data.get("tickets_convictions") or 0) == 0

        steps: List[str] = []
        screenshot_path = None

        try:
            async with self.browser_page() as page:
                response = await page.goto(self.url, wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(3000)
                steps.append(f"loaded ({response.status if response else '?'})")

                selects = page.locator("select")

                async def choose(index: int, value: str, what: str) -> bool:
                    try:
                        await selects.nth(index).select_option(value=value, timeout=8000)
                        steps.append(f"{what}={value}")
                        return True
                    except Exception as exc:
                        steps.append(f"{what} FAILED: {str(exc)[:70]}")
                        return False

                await choose(0, year, "vehicle_year")
                await choose(1, make, "vehicle_make")
                await page.wait_for_timeout(1800)  # model list is populated by make
                # Model barely moves the estimate; take the first real option.
                try:
                    await selects.nth(2).select_option(index=1, timeout=8000)
                    steps.append("vehicle_model=first available")
                except Exception:
                    steps.append("vehicle_model skipped")

                await choose(3, band, "age_band")

                for label in (
                    "Claim-free" if claim_free else "1+ at-fault accident",
                    "No tickets" if no_tickets else "1+ ticket",
                ):
                    try:
                        await page.get_by_role("button", name=re.compile(label, re.I)).first.click(
                            timeout=5000
                        )
                        steps.append(f"clicked {label!r}")
                    except Exception as exc:
                        steps.append(f"{label!r} FAILED: {str(exc)[:60]}")

                try:
                    await page.locator("input[type=number]").first.fill(premium, timeout=8000)
                    steps.append(f"current_premium={premium}")
                except Exception as exc:
                    steps.append(f"premium FAILED: {str(exc)[:60]}")

                # The calculator's own postal field is the unnamed one; the named
                # `postal_code` inputs belong to the site-wide lead capture header.
                try:
                    await page.locator(
                        "input[type=text]:not([name]), input[placeholder*='e.g.']"
                    ).first.fill(postal, timeout=8000)
                    steps.append(f"postal_code={postal}")
                except Exception as exc:
                    steps.append(f"postal FAILED: {str(exc)[:60]}")

                try:
                    await page.get_by_role(
                        "button", name=re.compile(r"See How Much", re.I)
                    ).first.click(timeout=5000)
                    steps.append("submitted")
                except Exception as exc:
                    steps.append(f"submit FAILED: {str(exc)[:60]}")

                await page.wait_for_timeout(4500)
                text = await page.inner_text("body")

                # Results block renders as label/value pairs: "Fair benchmark" then
                # "$2,258". Keying off those exact labels avoids matching the
                # explanatory copy elsewhere on the page.
                estimate = self._labelled_amount(text, r"Fair benchmark")
                city_average = self._labelled_amount(text, r".*avg")
                pays_now = self._labelled_amount(text, r"You pay now")

                screenshot_path = await self.capture(page, amount=estimate)

                if estimate is None:
                    return self.build_result(
                        status="REJECTED",
                        evidence_summary=(
                            "MyChoice.ca's calculator did not return a benchmark for this "
                            "profile."
                        ),
                        evidence_payload={"steps": steps},
                        screenshot_path=screenshot_path,
                    )

                verdict = next(
                    (
                        line.strip()
                        for line in text.splitlines()
                        if re.search(r"You pay \$\d+/mo", line)
                    ),
                    None,
                )
                headline = verdict or (
                    f"MyChoice.ca benchmarks a driver like you at ${estimate:,.0f}/yr."
                )

                payload = {
                    "source_url": self.url,
                    "steps": steps,
                    "headline": headline,
                    "current_annual": pays_now,
                    "city_average_annual": city_average,
                    "matched_on": f"age band {band}, {make} {year}, {postal[:3]}",
                    "comparisons": [
                        c
                        for c in (
                            {"label": "What you pay now", "annual": pays_now, "note": ""}
                            if pays_now
                            else None,
                            {"label": "City average", "annual": city_average, "note": ""}
                            if city_average
                            else None,
                        )
                        if c
                    ],
                    "applicant_profile": applicant_data,
                }
                payload["results_file_path"] = self.save_json_artifact(
                    payload, prefix=f"{self.channel_id}_results"
                )

                return self.build_result(
                    status="SUCCESS",
                    annual_premium=estimate,
                    evidence_summary=headline,
                    evidence_payload=payload,
                    screenshot_path=screenshot_path,
                )

        except Exception as exc:
            return self.build_result(
                status="SYSTEM_ERROR",
                evidence_summary=f"MyChoice.ca automation error: {exc}",
                evidence_payload={"error": str(exc), "steps": steps},
                screenshot_path=screenshot_path,
            )
