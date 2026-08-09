# backend/app/scrapers/test_fsra.py
import asyncio
import sys
import os
import json

# Ensure the backend directory is on the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.scrapers.fsra_benchmark import FSRABenchmarkScraper

async def test():
    scraper = FSRABenchmarkScraper()
    
    # Minimal applicant test profile matching the FSRA scraper contract
    test_profile = {
        "age": 24,
        "gender": "Male",
        "marital_status": "Not Married",
        "postal_code": "L6X 4Y3",
        "annual_mileage": 10100,
        "vehicle_model_year": 2021,
        "vehicle_make": "HYUNDAI",
        "years_licensed": 2,
        "years_claim_free": 2,
        "multi_vehicle_discount": False,
        "multi_policy_discount": False,
    }
    
    print("🚀 Launching FSRA Regulator Rate Ranger automation...")
    result = await scraper.execute(test_profile)
    
    print("\n--- Execution Result ---")
    print(json.dumps(result, indent=2))
    
    if result.get("screenshot_path"):
        abs_path = os.path.abspath(result["screenshot_path"])
        print(f"\n📸 Visual Evidence Screenshot Saved at:\n{abs_path}")

if __name__ == "__main__":
    asyncio.run(test())