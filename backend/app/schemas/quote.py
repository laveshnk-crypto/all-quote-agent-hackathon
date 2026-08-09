from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Dict, Any

class QuoteRunCreate(BaseModel):
    applicant_id: str
    channel_id: str
    channel_name: str
    channel_category: str
    status: str  # "SUCCESS", "BLOCKED_CAPTCHA", "PHONE_REQUIRED", "REJECTED", "SYSTEM_ERROR"
    annual_premium: Optional[float] = None
    monthly_premium: Optional[float] = None
    evidence_summary: Optional[str] = None
    evidence_payload: Optional[Dict[str, Any]] = None
    screenshot_path: Optional[str] = None
    executed_at: datetime
    
    model_config = ConfigDict(from_attributes=True)  # This allows Pydantic to read from ORM models directly