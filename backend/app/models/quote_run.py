import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Numeric, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class QuoteRun(Base):
    __tablename__ = "quote_runs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False
    )
    
    # Channel Identifiers
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_category: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Outcome Status: "SUCCESS", "BLOCKED_CAPTCHA", "PHONE_REQUIRED", "REJECTED", "SYSTEM_ERROR"
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Financial results (only if quote is obtained)
    annual_premium: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    monthly_premium: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    
    # Evidence details
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=True)
    evidence_payload: Mapped[dict] = mapped_column(JSON, nullable=True)
    screenshot_path: Mapped[str] = mapped_column(String(255), nullable=True)
    
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    applicant = relationship("Applicant", back_populates="quote_runs")