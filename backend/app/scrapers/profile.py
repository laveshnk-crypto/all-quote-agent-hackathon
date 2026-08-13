# backend/app/scrapers/profile.py
"""One canonical answer format, translated per site at the point of entry.

Every site asks the same questions in different words. Overnight parking is
"Private Garage" on LowestRates, "Garage" on the intake form, and a bucket index
on other calculators; marital status is "Not Married" here and "Single" there.
Scattering those spellings through the scrapers meant each one silently
interpreted the applicant slightly differently.

So the answer is normalised exactly once, into the tokens below, and each
scraper declares a ``VALUE_MAP`` from those tokens to the wording its own site
uses. A scraper never sees a raw form value, and adding a site is a table of
strings rather than another dialect of if-statements.

Binary answers are booleans. Multi-valued answers are lowercase tokens rather
than booleans, so a site offering a sixth parking option or a third marital
status is a new row in a map, not a schema change.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

# --- canonical vocabularies -------------------------------------------------

GENDERS = ("male", "female")
PARKING = ("garage", "driveway", "underground", "lot", "street", "carport")
USE = ("personal", "business")
OWNERSHIP = ("owned", "financed", "leased")

#: How the intake form's labels map onto the canonical tokens. The form is the
#: only place these human-facing strings are allowed to exist.
FORM_TO_CANONICAL: Dict[str, Dict[str, Any]] = {
    "gender": {"Male": "male", "Female": "female"},
    "marital_status": {"Married": True, "Not Married": False},
    "overnight_parking": {
        "Garage": "garage",
        "Driveway": "driveway",
        "Underground": "underground",
        "Parking Lot": "lot",
        "Street": "street",
        "Carport": "carport",
    },
    "primary_use": {"Personal": "personal", "Business": "business"},
    "financed_or_leased": {"Owned": "owned", "Financed": "financed", "Leased": "leased"},
}


@dataclass
class Profile:
    """The applicant, in canonical form. Built once, read by every scraper."""

    age: int
    gender: str                 # "male" | "female"
    is_married: bool
    postal_code: str
    city: str

    vehicle_year: int
    vehicle_make: str
    vehicle_model: Optional[str]
    ownership: str              # "owned" | "financed" | "leased"

    annual_km: int
    daily_commute_km: Optional[int]
    parking: str                # one of PARKING
    use: str                    # "personal" | "business"

    years_licensed: int
    years_claim_free: int
    at_fault_accidents: int
    tickets_convictions: int

    anti_theft: bool
    winter_tires: bool
    wants_comprehensive: bool
    wants_collision: bool
    multi_vehicle_discount: bool
    multi_policy_discount: bool

    current_monthly_premium: Optional[int] = None

    #: Kept so evidence payloads can still show exactly what the user confirmed.
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def fsa(self) -> str:
        """First three characters of the postal code, which is what rate tables key on."""
        return self.postal_code.upper().replace(" ", "")[:3]

    @property
    def is_claim_free(self) -> bool:
        return self.at_fault_accidents == 0

    @property
    def has_tickets(self) -> bool:
        return self.tickets_convictions > 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _canonical(field_name: str, value: Any, default: Any = None) -> Any:
    """Translate one confirmed form value into its canonical token."""
    table = FORM_TO_CANONICAL.get(field_name, {})
    if value in table:
        return table[value]
    # Already canonical (a re-run, or a caller building a Profile directly).
    if value in table.values():
        return value
    return default


def _int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError, AttributeError):
        return default


def build_profile(confirmed: Dict[str, Any], *, age: int) -> Profile:
    """Turn the confirmed intake form into the canonical profile.

    ``age`` is passed in because it is derived from the date of birth against
    today's date, which is the agent's job rather than this module's.
    """
    return Profile(
        age=age,
        gender=_canonical("gender", confirmed.get("gender"), "male"),
        is_married=bool(_canonical("marital_status", confirmed.get("marital_status"), False)),
        postal_code=str(confirmed.get("postal_code") or "").strip().upper(),
        city=str(confirmed.get("city") or "").strip(),
        vehicle_year=_int(confirmed.get("vehicle_year")) or 0,
        vehicle_make=str(confirmed.get("vehicle_make") or "").strip().upper(),
        vehicle_model=(str(confirmed.get("vehicle_model")).strip() or None)
        if confirmed.get("vehicle_model")
        else None,
        ownership=_canonical("financed_or_leased", confirmed.get("financed_or_leased"), "owned"),
        annual_km=_int(confirmed.get("annual_mileage_km")) or 0,
        daily_commute_km=_int(confirmed.get("daily_commute_km")),
        parking=_canonical("overnight_parking", confirmed.get("overnight_parking"), "driveway"),
        use=_canonical("primary_use", confirmed.get("primary_use"), "personal"),
        years_licensed=_int(confirmed.get("years_licensed")) or 0,
        years_claim_free=_int(confirmed.get("years_claim_free")) or 0,
        at_fault_accidents=_int(confirmed.get("at_fault_accidents"), 0) or 0,
        tickets_convictions=_int(confirmed.get("tickets_convictions"), 0) or 0,
        anti_theft=bool(confirmed.get("anti_theft_device")),
        winter_tires=bool(confirmed.get("winter_tires")),
        wants_comprehensive=bool(confirmed.get("comprehensive_coverage")),
        wants_collision=bool(confirmed.get("collision_coverage")),
        multi_vehicle_discount=bool(confirmed.get("multi_vehicle_discount")),
        multi_policy_discount=bool(confirmed.get("multi_policy_discount")),
        current_monthly_premium=_int(confirmed.get("current_monthly_premium")),
        raw=dict(confirmed),
    )


def legacy_applicant_dict(profile: Profile) -> Dict[str, Any]:
    """The flat dict shape the scrapers already read.

    Canonical tokens are expanded back into the keys each scraper expects, so
    the mapping lives here rather than being re-derived in ten places.
    """
    return {
        "age": profile.age,
        "gender": "Male" if profile.gender == "male" else "Female",
        "marital_status": "Married" if profile.is_married else "Not Married",
        "postal_code": profile.postal_code,
        "city": profile.city,
        "annual_mileage": profile.annual_km,
        "vehicle_model_year": profile.vehicle_year,
        "vehicle_year": profile.vehicle_year,
        "vehicle_make": profile.vehicle_make,
        "vehicle_model": profile.vehicle_model,
        "years_licensed": profile.years_licensed,
        "years_claim_free": profile.years_claim_free,
        "at_fault_accidents": profile.at_fault_accidents,
        "tickets_convictions": profile.tickets_convictions,
        "current_monthly_premium": profile.current_monthly_premium,
        "overnight_parking": profile.parking,
        "primary_use": profile.use,
        "financed_or_leased": profile.ownership,
        "daily_commute_km": profile.daily_commute_km,
        "anti_theft_device": profile.anti_theft,
        "winter_tires": profile.winter_tires,
        "comprehensive_coverage": profile.wants_comprehensive,
        "collision_coverage": profile.wants_collision,
        "multi_vehicle_discount": profile.multi_vehicle_discount,
        "multi_policy_discount": profile.multi_policy_discount,
        # Deliberately no Profile object in here: scrapers write this dict
        # straight into their JSON evidence artifacts, and a dataclass makes
        # json.dump raise, failing the channel after it had already succeeded.
    }
