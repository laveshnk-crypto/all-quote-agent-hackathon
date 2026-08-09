# OmniQuote ON

OmniQuote ON is a backend-first Ontario auto insurance quote automation project. It uses Playwright to drive the FSRA Regulator Rate Ranger benchmark flow and capture the resulting coverage information for a supplied applicant profile.

The current implementation focuses on the FSRA benchmark workflow, including input mapping, browser automation, evidence capture, and result export.

---

## What the project does

- Accepts a structured applicant profile with fields such as age, gender, marital status, postal code, annual mileage, vehicle make/model year, and discount flags.
- Maps those values into the FSRA form fields.
- Runs the Playwright automation flow against the FSRA benchmark site.
- Saves a screenshot and a JSON result file in the scraper artifacts folder.
- Returns the parsed results from the page in a structured payload.

---

## Current structure

- backend/app/main.py: FastAPI entrypoint and FSRA quote endpoint.
- backend/app/scrapers/fsra_benchmark.py: Playwright scraper for the FSRA benchmark flow.
- backend/app/scrapers/base_scraper.py: shared scraper helpers for screenshots and JSON artifacts.
- backend/test_fsra.py: simple local test harness for running the FSRA scraper.
- backend/app/scrapers/screenshots: output folder for screenshots and JSON result files.

---

## Tech stack

- Backend: FastAPI, Pydantic, Playwright, Python
- Database: SQLAlchemy + PostgreSQL support is scaffolded, but the current flow is centered on the scraper and evidence export.

---

## Run the FSRA benchmark locally

1. Create and activate a Python environment.
2. Install backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

3. Run the test harness:

```bash
python test_fsra.py
```

4. Or run the FastAPI app and call the endpoint:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then send a POST request to:

```text
http://localhost:8000/fsra/quote
```

with a JSON body shaped like:

```json
{
  "age": 24,
  "gender": "Female",
  "marital_status": "Not Married",
  "postal_code": "L6X 4Y3",
  "annual_mileage": 10100,
  "vehicle_model_year": 2021,
  "vehicle_make": "HYUNDAI",
  "years_licensed": 2,
  "years_claim_free": 2,
  "multi_vehicle_discount": "Not Applied",
  "multi_policy_discount": "Not Applied"
}
```

---

## Output artifacts

Each run saves:

- a screenshot PNG in backend/app/scrapers/screenshots
- a JSON results file in backend/app/scrapers/screenshots

These files are returned in the scraper response as part of the evidence payload.