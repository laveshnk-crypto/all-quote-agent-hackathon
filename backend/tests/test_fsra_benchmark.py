import unittest

from app.scrapers.fsra_benchmark import FSRABenchmarkScraper


class FSRABenchmarkScraperTests(unittest.TestCase):
    def test_extract_result_payload_groups_table_cells_by_coverage(self):
        cells = [
            "Mandatory coverage",
            "Mandatory coverage is comprised of the following coverages.",
            "Insurance was not recently provided for someone with your profile.",
            "Insurance was not recently provided for someone with your profile.",
            "Insurance was not recently provided for someone with your profile.",
            "Full coverage",
            "Full coverage is comprised of the following coverages.",
            "Insurance was not recently provided for someone with your profile.",
            "Insurance was not recently provided for someone with your profile.",
            "Insurance was not recently provided for someone with your profile.",
        ]

        parsed = FSRABenchmarkScraper._extract_result_payload(cells)

        self.assertEqual(parsed["mandatory_coverage"]["name"], "Mandatory coverage")
        self.assertEqual(parsed["full_coverage"]["name"], "Full coverage")
        self.assertEqual(parsed["mandatory_coverage"]["values"][0], "Insurance was not recently provided for someone with your profile.")
        self.assertEqual(parsed["full_coverage"]["values"][0], "Insurance was not recently provided for someone with your profile.")
        self.assertEqual(parsed["raw_cells"], cells)


if __name__ == "__main__":
    unittest.main()
