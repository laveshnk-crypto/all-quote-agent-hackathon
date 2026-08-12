import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime
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
1. Introduce yourself as an insurance agent and say you will check ten sources to show them
   what drivers with their profile actually pay.
2. Collect these details, one question at a time. Group the natural pairs into a single
   question so this doesn't drag: date of birth; gender; marital status; postal code and
   city; vehicle year, make and model; kilometres per year; years licensed; years
   claim-free; at-fault accidents in the last 6 years; tickets or convictions in the last 3
   years; what they pay per month today; multi-vehicle and multi-policy discounts.
   - Ask for city as well as postal code; several sources publish rates per city.
   - For what they pay today, make clear it's optional and that saying "not insured yet" or
     "not sure" is fine. One source is skipped without it; the other nine still run.
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
- The tool blocks while the user reviews the form and then for a minute or two while all ten
  sources run in parallel. Stay quiet during that time.
- If the tool reports an error, explain it plainly and offer to correct a detail and retry.

Final response after the quotes come back:
- Lead with the cheapest source and its annual figure, then the spread across all sources.
- Say how many of the ten returned a price, and name any that didn't and why, briefly.
- Never invent a figure for a source that returned nothing; call it unavailable and move on.
- Tell the user they can swipe through the cards, or open the table to compare all ten
  side by side, where the best rate is highlighted in gold.
- Be clear these are benchmarks and published averages, not binding quotes from an insurer.
- Offer to re-run with different details, such as lower mileage or added discounts.
"""


SCREENSHOT_DIR = BACKEND_ROOT / "app" / "scrapers" / "screenshots"

# Agent -> browser UI state updates, and the browser -> agent reply when the user
# confirms the on-screen form.
QUOTE_UI_TOPIC = "quote.ui"
QUOTE_SUBMIT_RPC = "quote.submit"
FORM_TIMEOUT_S = 300.0

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


def _coerce_form_values(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise values coming back from HTML inputs, which arrive as strings."""
    values: Dict[str, Any] = {}

    for field in FORM_FIELDS:
        key, label, kind = field["key"], field["label"], field["type"]
        optional = field.get("optional", False)
        value = raw.get(key)
        blank = value is None or str(value).strip() == ""

        if kind == "number":
            if blank:
                if optional:
                    values[key] = None
                    continue
                raise ToolError(f"'{label}' came back empty. Ask the user to fill it in.")
            try:
                values[key] = int(float(str(value).strip()))
            except (TypeError, ValueError):
                raise ToolError(f"'{label}' needs to be a whole number. Ask the user to fix it.")
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
                raise ToolError(f"'{label}' came back empty. Ask the user to fill it in.")
            if kind == "select" and text not in field["options"]:
                raise ToolError(
                    f"'{label}' must be one of {', '.join(field['options'])}. Ask the user to fix it."
                )
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
        # Full per-channel payloads from the most recent run, including artifact paths.
        self.last_quote_results: Optional[List[Dict[str, Any]]] = None

    def register_rpc(self) -> None:
        self._ctx.room.local_participant.register_rpc_method(
            QUOTE_SUBMIT_RPC, self._on_form_submit
        )

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

        future.set_result(payload)
        return json.dumps({"accepted": True})

    async def _publish_ui(self, payload: Dict[str, Any]) -> None:
        await self._ctx.room.local_participant.publish_data(
            json.dumps(payload), topic=QUOTE_UI_TOPIC, reliable=True
        )

    async def _await_form_confirmation(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Put the form on screen and block until the user confirms, edits, or cancels."""
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_form = future

        await self._publish_ui({"phase": "form", "fields": FORM_FIELDS, "values": values})

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

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="Greet the user as an insurance agent and ask for the first missing detail needed for an auto quote.",
            allow_interruptions=True,
        )

    @function_tool
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
        vehicle_model: str = "",
        current_monthly_premium: int = 0,
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
            multi_vehicle_discount: True if more than one vehicle is insured with the same company.
            multi_policy_discount: True if another policy (home, tenant) is with the same company.
        """
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
            "multi_vehicle_discount": multi_vehicle_discount,
            "multi_policy_discount": multi_policy_discount,
        }

        ctx.session.say(
            "I've put your details up on the screen. Have a quick look, "
            "change anything that's off, and hit confirm when it looks right."
        )

        submission = await self._await_form_confirmation(proposed)

        if submission.get("action") != "confirm":
            await self._publish_ui({"phase": "idle"})
            return {
                "status": "CANCELLED",
                "note": "The user dismissed the form without confirming. Ask what they "
                "would like to change, then call this tool again.",
            }

        confirmed = _coerce_form_values(submission.get("values", {}))
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
            "multi_vehicle_discount": confirmed["multi_vehicle_discount"],
            "multi_policy_discount": confirmed["multi_policy_discount"],
        }

        # Ten channels, each driving a browser, run concurrently.
        await self._publish_ui(
            {"phase": "loading", "channels": [c["channel_name"] for c in channel_directory()]}
        )
        ctx.session.say(
            "Perfect. I'm checking ten different sources for you now — "
            "this takes a minute or two."
        )

        logger.info("running all channels for profile: %s", applicant_data)
        results = await run_all_channels(applicant_data, screenshot_dir=str(SCREENSHOT_DIR))
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

        # Keep the spoken payload small: the cards are already on screen.
        return {
            "status": "SUCCESS",
            "currency": "CAD",
            "period": "annual",
            "summary": totals,
            "quotes": [
                {
                    "channel": c["channel_name"],
                    "status": c["status"],
                    "annual_premium": c["annual_premium"],
                    "headline": c["headline"],
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

    # Must come after start(): session.start() is what connects the room, and
    # ctx.room.local_participant raises until then.
    agent.register_rpc()


if __name__ == "__main__":
    cli.run_app(server)