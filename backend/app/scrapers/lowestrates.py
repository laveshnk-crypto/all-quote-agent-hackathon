# backend/app/scrapers/lowestrates.py
import re
from typing import Any, Dict, List, Optional

from app.scrapers.rate_page import RatePageScraper


class LowestRatesScraper(RatePageScraper):
    """LowestRates publishes a table of recent real quotes per city.

    Each row carries the driver's age, city, vehicle and both the lowest and
    average annual rate, so unlike the other editorial channels we can pick the
    row closest to this applicant rather than quoting a city-wide average.
    """

    channel_id = "lowestrates"
    channel_name = "LowestRates.ca"
    channel_category = "Aggregator"

    city_url_template = "https://www.lowestrates.ca/insurance/auto/{city}"
    fallback_url = "https://www.lowestrates.ca/insurance/auto"

    required_fields = ["city", "age"]

    #: LowestRates' own wording for each canonical answer.
    VALUE_MAP = {
        "parking": {
            "garage": "Private Garage",
            "driveway": "Private Driveway",
            "underground": "Underground Parking",
            "lot": "Parking Lot",
            "street": "Street",
            "carport": "Carport",
        },
        "use": {"personal": "Personal", "business": "Business"},
        "ownership": {
            "owned": "Owned - Paid in Cash / Completed Financing",
            "financed": "Financed",
            "leased": "Leased",
        },
        "yesno": {True: "Yes", False: "No"},
    }

    async def enter_profile(self, page, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Drive LowestRates' real quote funnel.

        Unlike the other editorial channels this one has a genuine multi-step
        intake that takes the whole vehicle profile before asking for anything
        personal, so we fill it properly rather than just dropping in a postal
        code. We stop at the end of the vehicle step: everything past it collects
        a name, email and phone number, and submitting those would put a real
        person into a broker's lead queue.
        """
        entered: Dict[str, Any] = {}
        postal = str(applicant_data.get("postal_code") or "").strip().upper()

        try:
            await page.locator("#postal-code").first.fill(postal, timeout=4000)
            entered["postal_code"] = postal
            await self.capture_entry(page, "1_postal")
            await page.get_by_role(
                "button", name=re.compile(r"Get Started", re.I)
            ).first.click(timeout=6000)
            await page.wait_for_selector("select[name='vehicle-year[]']", timeout=20000)
        except Exception as exc:
            return {"entered": entered, "note": f"funnel did not open: {str(exc)[:90]}"}

        async def choose(field: str, value: Optional[str], key: str) -> None:
            if value and await self.set_select(page, f"select[name='{field}']", str(value)):
                entered[key] = value

        async def options_for(field: str) -> List[str]:
            try:
                raw = await page.locator(f"select[name='{field}'] option").all_text_contents()
                return [o.strip() for o in raw if o.strip() and not o.strip().startswith("Select")]
            except Exception:
                return []

        await choose("vehicle-year[]", str(applicant_data.get("vehicle_year") or ""), "vehicle_year")

        # Make only populates once a year is chosen, and model once a make is.
        make = str(applicant_data.get("vehicle_make") or "").strip().upper()
        if make:
            try:
                await page.wait_for_function(
                    "() => document.querySelector(\"select[name='vehicle-make[]']\")"
                    "?.options.length > 1",
                    timeout=8000,
                )
            except Exception:
                pass
            match = next((o for o in await options_for("vehicle-make[]") if o.upper() == make), None)
            await choose("vehicle-make[]", match, "vehicle_make")

        model = str(applicant_data.get("vehicle_model") or "").strip()
        if model and entered.get("vehicle_make"):
            try:
                await page.wait_for_function(
                    "() => document.querySelector(\"select[name='vehicle-model[]']\")"
                    "?.options.length > 1",
                    timeout=8000,
                )
            except Exception:
                pass
            options = await options_for("vehicle-model[]")
            match = next((o for o in options if model.lower() in o.lower()), None)
            await choose("vehicle-model[]", match, "vehicle_model")

        # The site asks these in its own words; we already collected both.
        if applicant_data.get("winter_tires") is not None:
            await choose(
                "winter-tires[]",
                self.site_value("yesno", bool(applicant_data["winter_tires"])),
                "winter_tires",
            )

        if applicant_data.get("anti_theft_device") is not None:
            answer = self.site_value("yesno", bool(applicant_data["anti_theft_device"]))
            # Rendered conditionally with no stable name attribute, so locate it
            # by the question the site prints above it.
            try:
                await page.locator(
                    "xpath=//*[contains(., 'anti-theft devices')]"
                    "/following::select[1]"
                ).last.select_option(label=answer, timeout=5000)
                entered["anti_theft_device"] = answer
            except Exception as exc:
                entered.setdefault("_skipped", []).append(f"anti_theft: {str(exc)[:50]}")

        await choose(
            "is-leased[]",
            self.site_value("ownership", applicant_data.get("financed_or_leased")),
            "ownership",
        )
        await choose(
            "overnight-parking[]",
            self.site_value("parking", applicant_data.get("overnight_parking")),
            "overnight_parking",
        )
        await choose(
            "primary-use[]",
            self.site_value("use", applicant_data.get("primary_use")),
            "primary_use",
        )

        # Distance dropdowns use fixed buckets, so snap to the nearest offered value.
        for field, source, key in (
            ("daily-distance[]", "daily_commute_km", "daily_distance"),
            ("annual-distance[]", "annual_mileage", "annual_distance"),
        ):
            try:
                target = float(applicant_data.get(source) or 0)
                if not target:
                    continue
                options = await page.locator(f"select[name='{field}'] option").all_text_contents()
                pick = self.nearest_option([o for o in options if o.strip()], target)
                await choose(field, pick, key)
            except Exception:
                continue

        for field, source, key in (
            ("comprehensive-coverage[]", "comprehensive_coverage", "comprehensive"),
            ("collision-coverage[]", "collision_coverage", "collision"),
        ):
            value = applicant_data.get(source)
            if value is not None:
                await choose(field, self.site_value("yesno", bool(value)), key)

        await self.capture_entry(page, "2_vehicle")

        # Deliberately not clicking Continue: the next steps collect personal
        # contact details and submitting them would generate a real broker lead.
        return {
            "entered": entered,
            "note": "vehicle step completed; stopped before personal-details step",
        }

    @staticmethod
    def _row_quotes(row_text: str) -> List[float]:
        """Annual figures in a row, in order: lowest/yr then average/yr."""
        return [
            float(value.replace(",", ""))
            for value in re.findall(r"\$\s*(\d[\d,]*)\s*/\s*yr", row_text)
        ]

    def parse(
        self, text: str, tables: List[List[str]], applicant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            target_age = int(applicant_data.get("age") or 0)
        except (TypeError, ValueError):
            target_age = 0

        target_make = str(applicant_data.get("vehicle_make") or "").strip().upper()

        quotes: List[Dict[str, Any]] = []
        for row in tables:
            joined = " ".join(row)
            annuals = self._row_quotes(joined)
            if len(annuals) < 2:
                continue

            age_match = re.search(r"(\d{2})\s*years?\s*old", joined, re.I)
            vehicle_match = re.search(r"((?:19|20)\d{2}\s+[A-Z][A-Z0-9 .\-]{2,40})", joined)
            quotes.append(
                {
                    "age": int(age_match.group(1)) if age_match else None,
                    "vehicle": vehicle_match.group(1).strip() if vehicle_match else None,
                    "lowest_annual": annuals[0],
                    "average_annual": annuals[1],
                }
            )

        if not quotes:
            return {"annual_premium": None, "headline": None, "comparisons": []}

        def distance(quote: Dict[str, Any]) -> tuple:
            age_gap = abs((quote["age"] or 999) - target_age) if target_age else 999
            make_hit = 0 if target_make and target_make in (quote["vehicle"] or "") else 1
            return (make_hit, age_gap)

        best = min(quotes, key=distance)
        matched: Optional[str] = None
        if best["age"] is not None and target_age:
            matched = f"closest published quote: {best['age']}-year-old driver"
            if best["vehicle"]:
                matched += f", {best['vehicle']}"

        comparisons = [
            {
                "label": f"{q['age']}yo · {q['vehicle'] or 'vehicle n/a'}",
                "annual": q["lowest_annual"],
                "note": f"market average {q['average_annual']:,.0f}",
            }
            for q in quotes[:5]
        ]

        headline = (
            f"LowestRates.ca's closest published quote for this profile is "
            f"${best['lowest_annual']:,.0f}/yr, against a market average of "
            f"${best['average_annual']:,.0f}/yr."
        )

        return {
            # The lowest rate is what this channel actually offers a shopper.
            "annual_premium": best["lowest_annual"],
            "headline": headline,
            "comparisons": comparisons,
            "matched_on": matched,
            "market_average_annual": best["average_annual"],
        }
