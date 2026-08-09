# backend/app/scrapers/test_fsra.py
import asyncio
import sys
import os

# Add the backend root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.scrapers.fsra_benchmark import FSRABenchmarkScraper

async def test():
    scraper = FSRABenchmarkScraper()
    test_profile = {
        "postal_code": "K2S1E7",
        "vehicle_year": 2021,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic"
    }
    print("Running FSRA Benchmark scraper test...")
    result = await scraper.execute(test_profile)
    print("\n--- Scraper Output Result ---")
    print(result)

if __name__ == "__main__":
    asyncio.run(test())