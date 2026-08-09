# backend/app/scrapers/base_scraper.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import json
import os
import uuid
from datetime import datetime, timezone

class BaseScraper(ABC):
    channel_id: str
    channel_name: str
    channel_category: str  # Direct, Aggregator, Broker, Regulatory, Affinity

    def __init__(self, screenshot_dir: str = "app/scrapers/screenshots"):
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)

    @abstractmethod
    async def execute(self, applicant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Must be implemented by child classes.
        Returns a dictionary containing execution results and evidence.
        """
        pass

    def save_screenshot_artifact(self, page_bytes: bytes, prefix: str = "evidence") -> str:
        """Saves screenshot bytes to disk for visual evidence audits."""
        filename = f"{prefix}_{self.channel_id}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        with open(filepath, "wb") as f:
            f.write(page_bytes)
        return filepath

    def save_json_artifact(self, payload: Dict[str, Any], prefix: str = "evidence") -> str:
        """Saves structured JSON payloads to disk next to screenshots."""
        filename = f"{prefix}_{self.channel_id}_{uuid.uuid4().hex[:8]}.json"
        filepath = os.path.join(self.screenshot_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return filepath

    def build_result(
        self,
        status: str,  # SUCCESS, BLOCKED_CAPTCHA, PHONE_REQUIRED, REJECTED, SYSTEM_ERROR
        annual_premium: Optional[float] = None,
        monthly_premium: Optional[float] = None,
        evidence_summary: Optional[str] = None,
        evidence_payload: Optional[Dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ensures every route returns standardized evidence fields."""
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_category": self.channel_category,
            "status": status,
            "annual_premium": annual_premium,
            "monthly_premium": monthly_premium or (round(annual_premium / 12, 2) if annual_premium else None),
            "evidence_summary": evidence_summary,
            "evidence_payload": evidence_payload or {},
            "screenshot_path": screenshot_path,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }