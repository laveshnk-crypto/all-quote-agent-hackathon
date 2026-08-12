# backend/app/scrapers/fsra_benchmark.py
import re
from typing import Dict, Any, List

from app.scrapers.base_scraper import BaseScraper, MissingProfileField


class FSRABenchmarkScraper(BaseScraper):
    channel_id = "fsra_regulatory_benchmark"
    channel_name = "FSRA Regulator Rate Ranger"
    channel_category = "Regulatory"

    required_fields = [
        "age", "gender", "marital_status", "postal_code", "annual_mileage",
        "vehicle_model_year", "vehicle_make", "years_licensed", "years_claim_free",
    ]

    @staticmethod
    def _parse_band(values: List[str]) -> Dict[str, Any]:
        """FSRA reports three annual premiums per coverage tier: low, average, high."""
        amounts = []
        for value in values:
            match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
            if match:
                amounts.append(float(match.group().replace(",", "")))

        if len(amounts) < 3:
            return {"low": None, "average": None, "high": None}

        return {"low": amounts[0], "average": amounts[1], "high": amounts[2]}

    @staticmethod
    def _extract_result_payload(table_cells: List[str]) -> Dict[str, Any]:
        cleaned_cells = [cell.strip() for cell in table_cells if cell and cell.strip() and cell.strip() != "---"]
        normalized = [re.sub(r"\s+", " ", cell) for cell in cleaned_cells]

        sections = {
            "mandatory_coverage": {
                "name": "Mandatory coverage",
                "description": "",
                "values": [],
            },
            "full_coverage": {
                "name": "Full coverage",
                "description": "",
                "values": [],
            },
        }

        current_section = None
        for cell in normalized:
            lowered = cell.lower()
            if re.match(r"^mandatory coverage", lowered):
                current_section = "mandatory_coverage"
                description = re.sub(r"^mandatory coverage", "", cell, flags=re.IGNORECASE).strip()
                sections[current_section]["description"] = description or "Mandatory coverage"
                continue
            if re.match(r"^full coverage", lowered):
                current_section = "full_coverage"
                description = re.sub(r"^full coverage", "", cell, flags=re.IGNORECASE).strip()
                sections[current_section]["description"] = description or "Full coverage"
                continue
            if current_section and cell:
                sections[current_section]["values"].append(cell)

        for key in ("mandatory_coverage", "full_coverage"):
            sections[key]["premiums"] = FSRABenchmarkScraper._parse_band(sections[key]["values"])

        return {
            "raw_cells": normalized,
            "mandatory_coverage": sections["mandatory_coverage"],
            "full_coverage": sections["full_coverage"],
        }

    @staticmethod
    def _age_bucket(age: int) -> str:
        for ceiling, label in (
            (19, "16-19"), (29, "20-29"), (39, "30-39"), (49, "40-49"),
            (59, "50-59"), (69, "60-69"),
        ):
            if age <= ceiling:
                return label
        return "70+"

    @staticmethod
    def _vehicle_year_bucket(year: int) -> str:
        for ceiling, label in (
            (1998, "Prior-to-1999"), (2003, "1999-2003"), (2008, "2004-2008"),
            (2013, "2009-2013"), (2018, "2014-2018"), (2023, "2019-2023"),
        ):
            if year <= ceiling:
                return label
        return "2024+"

    @staticmethod
    def _mileage_bucket(km: int) -> str:
        if km <= 10000:
            return "0-10,000"
        if km <= 20000:
            return "10,001-20,000"
        if km <= 30000:
            return "20,001-30,000"
        return "30,001+"

    async def execute(self, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        url = "https://regulatorrateranger.fsrao.ca/"

        missing = self.missing_fields(applicant_data)
        if missing:
            return self.build_result(
                status="REJECTED",
                evidence_summary=(
                    f"FSRA needs {', '.join(missing)}; refusing to run with placeholder values."
                ),
                evidence_payload={"missing_fields": missing},
            )

        # Every value below comes from the applicant. There are no fallbacks:
        # a bad or absent answer fails the channel rather than producing a
        # confident-looking quote for somebody else's profile.
        try:
            postal_code = str(self.require(applicant_data, "postal_code")).upper().replace(" ", "")
            fsa = postal_code[:3]
            if not re.fullmatch(r"[A-Z]\d[A-Z]", fsa):
                return self.build_result(
                    status="REJECTED",
                    evidence_summary=f"'{postal_code}' is not a valid Ontario postal code.",
                    evidence_payload={"postal_code": postal_code},
                )

            age_value = int(self.require(applicant_data, "age"))
            gender = str(self.require(applicant_data, "gender"))
            marital_status = str(self.require(applicant_data, "marital_status"))
            vehicle_year_value = int(self.require(applicant_data, "vehicle_model_year"))
            vehicle_make = str(self.require(applicant_data, "vehicle_make")).strip()
            annual_mileage_value = int(self.require(applicant_data, "annual_mileage"))
            years_licensed = self.require(applicant_data, "years_licensed")
            years_claim_free = self.require(applicant_data, "years_claim_free")
        except MissingProfileField as exc:
            return self.build_result(
                status="REJECTED",
                evidence_summary=f"FSRA needs {exc.field}; refusing to substitute a default.",
                evidence_payload={"missing_fields": [exc.field]},
            )
        except (TypeError, ValueError) as exc:
            return self.build_result(
                status="REJECTED",
                evidence_summary=f"FSRA could not read the profile: {exc}",
                evidence_payload={"error": str(exc)},
            )

        age_bucket = self._age_bucket(age_value)
        vehicle_year_bucket = self._vehicle_year_bucket(vehicle_year_value)
        mileage_bucket = self._mileage_bucket(annual_mileage_value)

        # Discount toggles are genuinely optional on the FSRA form; absent means
        # "not applied", which is the site's own default, not an invented answer.
        def discount_display(key: str) -> str:
            value = applicant_data.get(key, False)
            if isinstance(value, bool):
                return "Applied" if value else "Not Applied"
            return str(value)

        multi_vehicle_discount_display = discount_display("multi_vehicle_discount")
        multi_policy_discount_display = discount_display("multi_policy_discount")

        screenshot_path = None
        try:
            async with self.browser_page() as page:
                await page.goto(url, wait_until="networkidle", timeout=40000)

                async def fill_react_select(selector_id: str, search_text: str):
                    locator = page.locator(selector_id)
                    await locator.focus()
                    await locator.fill(search_text)
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(200)

                await fill_react_select("#react-select-2-input", age_bucket)
                await fill_react_select("#react-select-3-input", gender)
                await fill_react_select("#react-select-4-input", marital_status)
                await fill_react_select("#react-select-5-input", fsa)
                await fill_react_select("#react-select-6-input", mileage_bucket)
                await fill_react_select("#react-select-7-input", vehicle_year_bucket)
                await fill_react_select("#react-select-8-input", vehicle_make)
                await fill_react_select("#react-select-9-input", str(years_licensed))
                await fill_react_select("#react-select-10-input", str(years_claim_free))
                await fill_react_select("#react-select-11-input", multi_vehicle_discount_display)
                await fill_react_select("#react-select-12-input", multi_policy_discount_display)

                await page.locator("button:has-text('Calculate')").click()
                await page.wait_for_timeout(2500)

                screenshot_path = await self.capture(page)

                table_cells = await page.locator("table tbody tr td").all_text_contents()
                result_payload = self._extract_result_payload(table_cells)

                mandatory = result_payload["mandatory_coverage"]["premiums"]
                full = result_payload["full_coverage"]["premiums"]
                annual_premium = full["average"]

                if annual_premium is None:
                    return self.build_result(
                        status="REJECTED",
                        evidence_summary=(
                            f"FSRA returned no rate for FSA {fsa} with this profile."
                        ),
                        evidence_payload={"results": result_payload, "fsa_queried": fsa},
                        screenshot_path=screenshot_path,
                    )

                result_file_path = self.save_json_artifact(result_payload, prefix="fsra_results")

                return self.build_result(
                    status="SUCCESS",
                    annual_premium=annual_premium,
                    evidence_summary=(
                        f"FSRA's regulatory benchmark for FSA {fsa} puts full coverage at "
                        f"${annual_premium:,.0f}/yr on average."
                    ),
                    evidence_payload={
                        "source_url": url,
                        "matched_on": f"age {age_bucket}, FSA {fsa}, {mileage_bucket} km",
                        "comparisons": [
                            c
                            for c in (
                                {"label": "Full coverage low", "annual": full.get("low"), "note": ""},
                                {"label": "Full coverage high", "annual": full.get("high"), "note": ""},
                                {
                                    "label": "Mandatory only",
                                    "annual": mandatory.get("average"),
                                    "note": "average",
                                },
                            )
                            if c["annual"] is not None
                        ],
                        "fsa_queried": fsa,
                        "applicant_profile": applicant_data,
                        "age_bucket": age_bucket,
                        "mileage_bucket": mileage_bucket,
                        "vehicle_year_bucket": vehicle_year_bucket,
                        "results": result_payload,
                        "results_file_path": result_file_path,
                    },
                    screenshot_path=screenshot_path,
                )

        except Exception as e:
            return self.build_result(
                status="SYSTEM_ERROR",
                evidence_summary=f"FSRA Rate Ranger automation error: {str(e)}",
                evidence_payload={"error": str(e)},
                screenshot_path=screenshot_path,
            )
