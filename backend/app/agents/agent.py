import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    ToolError,
    TurnHandlingOptions,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.plugins import ai_coustics

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.routers.token import build_livekit_token
from app.scrapers.registry import channel_directory, run_all_channels, summarise

logger = logging.getLogger("insurance-quote-agent")

load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
load_dotenv(dotenv_path=BACKEND_ROOT / ".env.local", override=False)

SYSTEM_PROMPT = """
You are Omni-Quote, an insurance agent helping a user compare Ontario auto insurance rates
across ten different sources at once: the FSRA Regulator Rate Ranger, LowestRates.ca,
Rates.ca, Ratehub.ca, InsuranceHotline.com, MyChoice.ca (both their calculator and their
rate index), HelloSafe.ca, Surex.com and isure.ca.

You are on a voice call. Everything you say is spoken aloud.

Workflow:
1. Introduce yourself as an insurance agent and you are here to help the user compare insurance rates in order to get the best possible auto quotes..
2. Collect these details. Group related ones into a single question so this doesn't drag --
   aim for about ten questions, not twenty-four:
   - date of birth, gender, marital status
   - postal code and city (several sources publish rates per city)
   - vehicle year, make and model
   - whether it's owned outright, financed or leased
   - where it's parked overnight (garage, driveway, underground, parking lot, street, carport)
   - whether it has, or they plan to install, an anti-theft device
   - primary use: personal or business driving
   - kilometres per year, and the one-way daily commute
   - years licensed, years claim-free, at-fault accidents in 6 years, tickets in 3 years
   - whether they put winter tires on each season
   - whether they want comprehensive and collision cover, or liability only
   - what they pay per month today
   - multi-vehicle and multi-policy discounts
   - For what they pay today, make clear it's optional and that "not insured yet" or "not
     sure" is fine. One source is skipped without it; the other nine still run.
   - Parking, anti-theft, ownership and commute are typed straight into the sources' own
     quote forms, so they change the numbers -- they aren't box-ticking.
3. As soon as you have all of the above, call the get_insurance_quote tool. Do not read the
   details back verbally first. The tool puts an editable form on the user's screen and waits
   for them to review it, which is how confirmation happens.
4. The user may edit any value on that form. The tool returns confirmed_details showing what
   they actually submitted. Narrate those values, not the ones you passed in.
5. If the tool comes back CANCELLED, ask what they would like to change, then call it again.

Style rules:
- Keep responses friendly, clear, and short.
- Speak like a professional insurance agent, in plain language.
- Never ask for anything outside the list above. Do not ask for last name, street address,
  licence number, email, or phone; none of the sources use them.
- Say numbers the way a person would: "twenty one hundred dollars a year", not "$2,167.00".
- Never invent or estimate pricing. Pricing only ever comes from the get_insurance_quote tool.

Tooling:
- get_insurance_quote handles the on-screen confirmation form, the loading state, and the
  results carousel. You do not need to describe any of that; the user can see it.
- Results appear on screen one source at a time as each finishes, so the user is not
  staring at a blank screen. Do not narrate them arriving.
- The tool blocks while the user reviews the form and then for a minute or two while all ten
  sources run in parallel. Stay quiet during that time.
- If the tool reports an error, explain it plainly and offer to correct a detail and retry.

Final response after the quotes come back. Talk the user through it properly -- this is
the part they waited for, so give it four or five sentences, not one:
- Start with the best option in the `best` field: name the source, the annual figure and
  roughly what that is per month, and what coverage level it reflects.
- Say what that quote was matched on, from `best.matched_on`, so they know how close a fit
  it is to them. If it was matched on someone materially different -- a much older driver,
  a city-wide average rather than their own profile -- say so plainly. Do not oversell it.
- Put it in context: how much below the average of all the sources it is, and what the
  spread between cheapest and priciest was. A wide spread is the useful finding, because it
  means shopping around is worth real money to them.
- Mention one or two of the other notable results, especially any regulator or benchmark
  figure, so the best one has something to sit against.
- Say how many of the ten returned a price, and briefly name any that didn't and why.
- Never invent a figure for a source that returned nothing; call it unavailable and move on.
- Tell them they can swipe the cards, or open the table to compare all ten side by side,
  where the best rate is highlighted in gold and every row links to a screenshot of the
  page its number came from.
- Be clear these are benchmarks and published averages, not binding quotes from an insurer,
  and that an actual policy needs a real application.
- Offer to re-run with different details, such as lower mileage, a garage, or added
  discounts, and say the mic is open again.
"""


SCREENSHOT_DIR = BACKEND_ROOT / "app" / "scrapers" / "screenshots"

# Agent -> browser UI state updates, and the browser -> agent reply when the user
# confirms the on-screen form.
QUOTE_UI_TOPIC = "quote.ui"
QUOTE_SUBMIT_RPC = "quote.submit"
QUOTE_VOICE_RPC = "quote.voice"
FORM_TIMEOUT_S = 300.0

# What we tell the user the lookup will take. Measured runs land between about
# 35s and 80s depending on how the sites are responding, so quote the pessimistic
# end -- a lookup that beats its estimate reads as fast, one that overruns reads
# as broken.
ESTIMATED_RUN_S = 90

# Drives both the on-screen form and the coercion of whatever comes back from it.
# `optional` fields may come back blank; they gate individual channels rather
# than blocking the whole run.
FORM_FIELDS = [
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    {"key": "gender", "label": "Gender", "type": "select", "options": ["Male", "Female"]},
    {
        "key": "marital_status",
        "label": "Marital status",
        "type": "select",
        "options": ["Married", "Not Married"],
    },
    {"key": "postal_code", "label": "Postal code", "type": "text"},
    {"key": "city", "label": "City or town", "type": "text"},
    {"key": "vehicle_year", "label": "Vehicle year", "type": "number"},
    {"key": "vehicle_make", "label": "Vehicle make", "type": "text"},
    {"key": "vehicle_model", "label": "Vehicle model", "type": "text", "optional": True},
    {"key": "annual_mileage_km", "label": "Kilometres per year", "type": "number"},
    {"key": "years_licensed", "label": "Years licensed", "type": "number"},
    {"key": "years_claim_free", "label": "Years claim-free", "type": "number"},
    {
        "key": "at_fault_accidents",
        "label": "At-fault accidents (last 6 years)",
        "type": "number",
    },
    {
        "key": "tickets_convictions",
        "label": "Tickets or convictions (last 3 years)",
        "type": "number",
    },
    {
        "key": "current_monthly_premium",
        "label": "What you pay now ($/month)",
        "type": "number",
        "optional": True,
        "hint": "Leave blank if you're not insured yet",
    },
    {
        "key": "overnight_parking",
        "label": "Where it parks overnight",
        "type": "select",
        "options": ["Garage", "Driveway", "Underground", "Parking Lot", "Street", "Carport"],
    },
    {
        "key": "primary_use",
        "label": "Primary use",
        "type": "select",
        "options": ["Personal", "Business"],
    },
    {
        "key": "financed_or_leased",
        "label": "Ownership",
        "type": "select",
        "options": ["Owned", "Financed", "Leased"],
    },
    {
        "key": "daily_commute_km",
        "label": "One-way commute (km/day)",
        "type": "number",
        "optional": True,
        "hint": "0 if you don't commute",
    },
    {
        "key": "anti_theft_device",
        "label": "Anti-theft device installed",
        "type": "boolean",
    },
    {
        "key": "winter_tires",
        "label": "Winter tires each season",
        "type": "boolean",
    },
    {
        "key": "comprehensive_coverage",
        "label": "Wants comprehensive coverage",
        "type": "boolean",
    },
    {
        "key": "collision_coverage",
        "label": "Wants collision coverage",
        "type": "boolean",
    },
    {
        "key": "multi_vehicle_discount",
        "label": "Insures more than one vehicle here",
        "type": "boolean",
    },
    {
        "key": "multi_policy_discount",
        "label": "Has another policy here (home or tenant)",
        "type": "boolean",
    },
]

_DOB_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%d %B %Y")


#: Why a channel produced no number, in words a person would use.
_STATUS_BLURB = {
    "REJECTED": "doesn't cover this profile",
    "BLOCKED_CAPTCHA": "blocked automated access",
    "PHONE_REQUIRED": "needs a phone call to quote",
    "SYSTEM_ERROR": "couldn't be reached",
}


def _quote_card(result: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one channel result into what the carousel renders."""
    payload = result.get("evidence_payload") or {}
    annual = result.get("annual_premium")

    return {
        "channel_id": result.get("channel_id"),
        "channel_name": result.get("channel_name"),
        "channel_category": result.get("channel_category"),
        "status": result.get("status"),
        "annual_premium": annual,
        "monthly_premium": result.get("monthly_premium"),
        "headline": result.get("evidence_summary"),
        "matched_on": payload.get("matched_on"),
        "comparisons": payload.get("comparisons", [])[:5],
        "source_url": payload.get("source_url"),
        # Screenshot proof of the page this figure was read from.
        "screenshot_url": result.get("screenshot_url"),
        "is_recommended": result.get("is_recommended", False),
        "unavailable_reason": (
            None
            if result.get("status") == "SUCCESS"
            else _STATUS_BLURB.get(result.get("status"), "returned no rate")
        ),
    }


class FormValidationError(Exception):
    """A field came back unusable. Carries which one, so the form can say so."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def _coerce_form_values(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise values coming back from HTML inputs, which arrive as strings."""
    values: Dict[str, Any] = {}

    for field in FORM_FIELDS:
        key, kind = field["key"], field["type"]
        optional = field.get("optional", False)
        value = raw.get(key)
        blank = value is None or str(value).strip() == ""

        if kind == "number":
            if blank:
                if optional:
                    values[key] = None
                    continue
                raise FormValidationError(key, "Needs a number")
            try:
                values[key] = int(float(str(value).strip()))
            except (TypeError, ValueError):
                raise FormValidationError(key, "Whole numbers only")
        elif kind == "boolean":
            values[key] = (
                value
                if isinstance(value, bool)
                else str(value).strip().lower() in ("true", "yes", "on", "1")
            )
        else:
            text = str(value).strip() if value is not None else ""
            if not text:
                if optional:
                    values[key] = None
                    continue
                raise FormValidationError(key, "This one is needed")
            if kind == "select" and text not in field["options"]:
                raise FormValidationError(key, f"Pick one of: {', '.join(field['options'])}")
            values[key] = text

    return values


def _parse_date_of_birth(value: str) -> date:
    cleaned = value.strip()
    for fmt in _DOB_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ToolError(
        "I could not read that date of birth. Ask the user to repeat it, "
        "then pass it as YYYY-MM-DD."
    )


def _age_on(dob: date, today: Optional[date] = None) -> int:
    today = today or date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 16 or age > 110:
        raise ToolError(
            f"That date of birth works out to {age} years old, which is outside the range "
            "the rate benchmark covers. Ask the user to confirm their birth year."
        )
    return age


class DefaultAgent(Agent):
    def __init__(self, ctx: JobContext) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=[
                EndCallTool(
                    extra_description="Let the user leave the call gracefully.",
                    end_instructions="Thank the user for their time and say goodbye.",
                    delete_room=False,
                )
            ],
        )
        self._ctx = ctx
        # Resolved by the browser's RPC reply while a form is on screen.
        self._pending_form: Optional[asyncio.Future] = None
        self._voice_enabled = True
        # Full per-channel payloads from the most recent run, including artifact paths.
        self.last_quote_results: Optional[List[Dict[str, Any]]] = None

    def register_rpc(self) -> None:
        local = self._ctx.room.local_participant
        local.register_rpc_method(QUOTE_SUBMIT_RPC, self._on_form_submit)
        local.register_rpc_method(QUOTE_VOICE_RPC, self._on_voice_toggle)

    async def _on_voice_toggle(self, data: rtc.RpcInvocationData) -> str:
        """User tapped the mic button to start or stop talking to us."""
        try:
            payload = json.loads(data.payload)
        except json.JSONDecodeError:
            return json.dumps({"ok": False, "reason": "malformed payload"})

        enable = payload.get("action") != "pause"
        await self.set_voice_input(enable, reason="user tapped the mic")
        if enable:
            # Acknowledge out loud so it's obvious the mic is live again.
            self.session.generate_reply(
                instructions=(
                    "The user just re-opened the microphone while their details "
                    "are on screen. Briefly say you're listening and ask what "
                    "they'd like to change. One short sentence."
                )
            )
        return json.dumps({"ok": True, "enabled": enable})

    async def set_voice_input(self, enabled: bool, *, reason: str = "") -> None:
        """Open or close the mic, and tell the UI which it is.

        While the form is up there is nothing useful to say to us -- the answers
        are being edited on screen -- and an open mic just feeds room noise into
        the transcriber. The UI shows a mic button so the user can re-open it.
        """
        try:
            self.session.input.set_audio_enabled(enabled)
        except Exception:
            logger.exception("could not set audio input enabled=%s", enabled)
        self._voice_enabled = enabled
        logger.info("voice input %s (%s)", "on" if enabled else "off", reason)
        await self._publish_ui({"phase": "voice", "enabled": enabled})

    async def _on_form_submit(self, data: rtc.RpcInvocationData) -> str:
        """Browser calls this when the user confirms or cancels the on-screen form."""
        future = self._pending_form
        if future is None or future.done():
            # Stale click after the form already resolved; ack so the UI doesn't hang.
            return json.dumps({"accepted": False, "reason": "no form awaiting submission"})

        try:
            payload = json.loads(data.payload)
        except json.JSONDecodeError:
            return json.dumps({"accepted": False, "reason": "malformed payload"})

        logger.info(
            "form submitted: action=%s fields=%d",
            payload.get("action"),
            len(payload.get("values") or {}),
        )
        future.set_result(payload)
        return json.dumps({"accepted": True})

    async def _publish_ui(self, payload: Dict[str, Any]) -> None:
        await self._ctx.room.local_participant.publish_data(
            json.dumps(payload), topic=QUOTE_UI_TOPIC, reliable=True
        )

    async def _collect_confirmed_details(self, proposed: Dict[str, Any]) -> Dict[str, Any]:
        """Show the form until we get values that actually validate, or a cancel.

        A bad field used to raise out to the model, which would call the tool
        again and paint a brand new empty-looking form -- the user saw the same
        form twice with no idea what was wrong. Now the same form comes back with
        the offending field marked, and the run continues from there.
        """
        values = dict(proposed)
        errors: Dict[str, str] = {}

        for _ in range(4):
            submission = await self._await_form_confirmation(values, errors)

            if submission.get("action") != "confirm":
                return {"cancelled": True}

            values = {**values, **(submission.get("values") or {})}
            try:
                return {"confirmed": _coerce_form_values(values)}
            except FormValidationError as exc:
                errors = {exc.field: exc.message}
                logger.info("form validation: %s", exc)

        return {"cancelled": True, "reason": "too many invalid submissions"}

    async def _await_form_confirmation(
        self, values: Dict[str, Any], errors: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Put the form on screen and block until the user confirms, edits, or cancels."""
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_form = future

        # Logged every time so a repeat "it asked me again" can be traced to the
        # cause: a second form with errors is validation, a second with none is a
        # duplicate tool call.
        logger.info(
            "publishing form (errors=%s)", list((errors or {}).keys()) or "none"
        )
        await self._publish_ui(
            {
                "phase": "form",
                "fields": FORM_FIELDS,
                "values": values,
                "errors": errors or {},
            }
        )
        # Nothing said out loud can help while the form is being edited, and an
        # open mic here just feeds room noise to the transcriber.
        await self.set_voice_input(False, reason="form on screen")

        try:
            return await asyncio.wait_for(future, timeout=FORM_TIMEOUT_S)
        except asyncio.TimeoutError:
            await self._publish_ui({"phase": "idle"})
            raise ToolError(
                "The user never confirmed the on-screen form. Ask them if they still "
                "want to run the rate lookup."
            )
        finally:
            self._pending_form = None
            # However the wait ended, the user gets their microphone back.
            await self.set_voice_input(True, reason="form closed")

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="Greet the user as an insurance agent and ask for the first missing detail needed for an auto quote.",
            allow_interruptions=True,
        )

    @function_tool(on_duplicate="reject", duplicate_scope="name")
    async def get_insurance_quote(
        self,
        ctx: RunContext,
        date_of_birth: str,
        gender: Literal["Male", "Female"],
        marital_status: Literal["Married", "Not Married"],
        postal_code: str,
        city: str,
        vehicle_year: int,
        vehicle_make: str,
        annual_mileage_km: int,
        years_licensed: int,
        years_claim_free: int,
        at_fault_accidents: int,
        tickets_convictions: int,
        overnight_parking: Literal[
            "Garage", "Driveway", "Underground", "Parking Lot", "Street", "Carport"
        ],
        primary_use: Literal["Personal", "Business"],
        financed_or_leased: Literal["Owned", "Financed", "Leased"],
        anti_theft_device: bool,
        vehicle_model: str = "",
        current_monthly_premium: int = 0,
        daily_commute_km: int = 0,
        winter_tires: bool = False,
        comprehensive_coverage: bool = True,
        collision_coverage: bool = True,
        multi_vehicle_discount: bool = False,
        multi_policy_discount: bool = False,
    ) -> Dict[str, Any]:
        """Put the collected details on screen for the user to review, then price them
        against every quote channel at once.

        Call this as soon as you have all the details. It shows the user an editable form,
        waits for them to confirm or correct it, then queries all ten channels in parallel
        (one to two minutes). The user may edit any value before confirming, so always read
        the returned confirmed_details back rather than assuming your arguments were used
        as-is. Returns one entry per channel plus a summary with the cheapest and the spread.

        Args:
            date_of_birth: The driver's date of birth as YYYY-MM-DD.
            gender: The driver's gender as listed on their licence.
            marital_status: Whether the driver is married.
            postal_code: Ontario postal code, e.g. "L6X 4Y3".
            city: City or town, e.g. "Toronto". Several channels publish rates per city.
            vehicle_year: Model year of the vehicle, e.g. 2021.
            vehicle_make: Manufacturer only, no model. E.g. "Hyundai", not "Hyundai Elantra".
            annual_mileage_km: Approximate kilometres driven per year, e.g. 15000.
            years_licensed: Full years the driver has held a licence.
            years_claim_free: Full years since the driver's last at-fault claim.
            at_fault_accidents: At-fault accidents in the last 6 years. 0 if none.
            tickets_convictions: Tickets or convictions in the last 3 years. 0 if none.
            vehicle_model: Model name, e.g. "Elantra". Optional but improves matching.
            current_monthly_premium: What the driver pays per month today, in dollars.
                0 if they are not insured yet or do not know; one channel needs this to
                benchmark them and is skipped without it.
            overnight_parking: Where the vehicle sits overnight. Sites price a garage
                very differently from street parking.
            primary_use: Whether the car is used for personal or business driving.
            financed_or_leased: Whether the vehicle is owned outright, financed, or leased.
            anti_theft_device: True if an anti-theft or tracking device is installed.
            daily_commute_km: One-way commute distance in km. 0 if they don't commute.
            winter_tires: True if winter tires go on each season; several insurers discount it.
            comprehensive_coverage: True if they want comprehensive cover.
            collision_coverage: True if they want collision cover.
            multi_vehicle_discount: True if more than one vehicle is insured with the same company.
            multi_policy_discount: True if another policy (home, tenant) is with the same company.
        """
        # A second call while a form is already on screen would paint a fresh
        # form over the one the user is filling in, and orphan the first tool
        # call's future -- which is what "it asked me again" looked like.
        if self._pending_form is not None and not self._pending_form.done():
            logger.warning("get_insurance_quote called while a form is already open")
            return {
                "status": "ALREADY_OPEN",
                "note": "Their details are already on screen waiting to be confirmed. "
                "Say nothing further and wait for them to press confirm.",
            }

        proposed = {
            "date_of_birth": _parse_date_of_birth(date_of_birth).isoformat(),
            "gender": gender,
            "marital_status": marital_status,
            "postal_code": postal_code,
            "city": city,
            "vehicle_year": vehicle_year,
            "vehicle_make": vehicle_make,
            "vehicle_model": vehicle_model,
            "annual_mileage_km": annual_mileage_km,
            "years_licensed": years_licensed,
            "years_claim_free": years_claim_free,
            "at_fault_accidents": at_fault_accidents,
            "tickets_convictions": tickets_convictions,
            "current_monthly_premium": current_monthly_premium or None,
            "overnight_parking": overnight_parking,
            "primary_use": primary_use,
            "financed_or_leased": financed_or_leased,
            "daily_commute_km": daily_commute_km,
            "anti_theft_device": anti_theft_device,
            "winter_tires": winter_tires,
            "comprehensive_coverage": comprehensive_coverage,
            "collision_coverage": collision_coverage,
            "multi_vehicle_discount": multi_vehicle_discount,
            "multi_policy_discount": multi_policy_discount,
        }

        ctx.session.say(
            "I've put your details up on the screen. Have a quick look, "
            "change anything that's off, and hit confirm when it looks right."
        )

        outcome = await self._collect_confirmed_details(proposed)

        if outcome.get("cancelled"):
            await self._publish_ui({"phase": "idle"})
            return {
                "status": "CANCELLED",
                "note": "The user dismissed the form without confirming. Ask what they "
                "would like to change, then call this tool again.",
            }

        confirmed = outcome["confirmed"]
        dob = _parse_date_of_birth(confirmed["date_of_birth"])

        applicant_data = {
            "age": _age_on(dob),
            "gender": confirmed["gender"],
            "marital_status": confirmed["marital_status"],
            "postal_code": confirmed["postal_code"],
            "city": confirmed["city"],
            "annual_mileage": confirmed["annual_mileage_km"],
            "vehicle_model_year": confirmed["vehicle_year"],
            "vehicle_year": confirmed["vehicle_year"],
            # The known-good scraper run used an uppercase make against the site's react-select.
            "vehicle_make": confirmed["vehicle_make"].strip().upper(),
            "vehicle_model": confirmed.get("vehicle_model"),
            "years_licensed": confirmed["years_licensed"],
            "years_claim_free": confirmed["years_claim_free"],
            "at_fault_accidents": confirmed["at_fault_accidents"],
            "tickets_convictions": confirmed["tickets_convictions"],
            "current_monthly_premium": confirmed.get("current_monthly_premium"),
            "overnight_parking": confirmed["overnight_parking"],
            "primary_use": confirmed["primary_use"],
            "financed_or_leased": confirmed["financed_or_leased"],
            "daily_commute_km": confirmed.get("daily_commute_km"),
            "anti_theft_device": confirmed["anti_theft_device"],
            "winter_tires": confirmed["winter_tires"],
            "comprehensive_coverage": confirmed["comprehensive_coverage"],
            "collision_coverage": confirmed["collision_coverage"],
            "multi_vehicle_discount": confirmed["multi_vehicle_discount"],
            "multi_policy_discount": confirmed["multi_policy_discount"],
        }

        # Ten channels, each driving a browser, run concurrently.
        await self._publish_ui(
            {
                "phase": "loading",
                "channels": [c["channel_name"] for c in channel_directory()],
                "eta_seconds": ESTIMATED_RUN_S,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        ctx.session.say(
            "Perfect. I'm entering your details on ten different sites now — "
            "it usually takes about a minute and a half. Results will appear on "
            "screen as each one comes back."
        )

        logger.info("running all channels for profile: %s", applicant_data)

        async def on_channel_done(result: Dict[str, Any], done: int, total: int) -> None:
            # Push each card the moment its channel lands, so the screen fills in
            # instead of holding a spinner until the slowest source returns.
            await self._publish_ui(
                {
                    "phase": "progress",
                    "done": done,
                    "total": total,
                    "quote": _quote_card(result),
                }
            )

        results = await run_all_channels(
            applicant_data,
            screenshot_dir=str(SCREENSHOT_DIR),
            on_result=on_channel_done,
        )
        self.last_quote_results = results

        totals = summarise(results)
        if not totals["channels_with_a_price"]:
            await self._publish_ui(
                {"phase": "error", "message": "No source returned a rate for this profile."}
            )
            raise ToolError(
                "All ten channels ran but none returned a price. Reasons: "
                + "; ".join(
                    f"{r['channel_name']}: {r.get('evidence_summary', '?')[:80]}"
                    for r in results
                )
                + ". Offer to double-check a detail and try again."
            )

        cards = [_quote_card(r) for r in results]
        await self._publish_ui({"phase": "result", "summary": totals, "quotes": cards})

        # The cards are already on screen, so the spoken payload stays small --
        # except for the winner, which gets the detail needed to talk about it.
        best = next((c for c in cards if c.get("is_recommended")), None)

        return {
            "status": "SUCCESS",
            "currency": "CAD",
            "period": "annual",
            "summary": totals,
            "best": (
                {
                    "channel": best["channel_name"],
                    "channel_type": best["channel_category"],
                    "annual_premium": best["annual_premium"],
                    "monthly_premium": best["monthly_premium"],
                    "headline": best["headline"],
                    "matched_on": best["matched_on"],
                    "coverage": (
                        "comprehensive and collision"
                        if confirmed.get("comprehensive_coverage")
                        and confirmed.get("collision_coverage")
                        else "mandatory coverage only"
                    ),
                    "versus_average": (
                        round(totals["average_annual"] - best["annual_premium"], 2)
                        if totals.get("average_annual") and best.get("annual_premium")
                        else None
                    ),
                }
                if best
                else None
            ),
            "quotes": [
                {
                    "channel": c["channel_name"],
                    "type": c["channel_category"],
                    "status": c["status"],
                    "annual_premium": c["annual_premium"],
                    "monthly_premium": c["monthly_premium"],
                    "matched_on": c["matched_on"],
                    "headline": c["headline"],
                    "unavailable_reason": c["unavailable_reason"],
                }
                for c in cards
            ],
            "confirmed_details": confirmed,
        }


async def get_token():
    return build_livekit_token()


server = AgentServer()


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "assistant-1-ge-1"))
async def entrypoint(ctx: JobContext):
    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3", language="en"),
        # gemma-4-31b-it has no native function calling; the quote tool would never fire.
        llm=inference.LLM(model="google/gemini-3-flash"),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
            language="en",
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            preemptive_generation={"enabled": True},
        ),
        vad=inference.VAD(),
    )

    agent = DefaultAgent(ctx)

    logger.info("entrypoint: starting session for room %s", ctx.room.name)
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S,
                ),
            ),
        ),
    )
    logger.info("entrypoint: session started, room connected=%s", ctx.room.isconnected())

    # Must come after start(): session.start() is what connects the room, and
    # ctx.room.local_participant raises until then.
    agent.register_rpc()
    logger.info("entrypoint: rpc registered, agent ready")


if __name__ == "__main__":
    cli.run_app(server)