import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Date, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Applicant(Base):
    __tablename__ = "applicants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    marital_status: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Address details (Ontario focus)
    street_address: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str] = mapped_column(String(100), nullable=False, default="Ontario")
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # Vehicle details
    vehicle_vin: Mapped[str] = mapped_column(String(17), nullable=False)
    vehicle_make: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_model: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_year: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    vehicle_parking_location: Mapped[str] = mapped_column(String(100), nullable=False)
    financed_or_leased: Mapped[bool] = mapped_column(nullable=False)

    # Usage details
    primary_use_personal_business: Mapped[bool] = mapped_column(nullable=False)
    annual_mileage_km: Mapped[int] = mapped_column(Integer, nullable=False)
    anti_theft_device: Mapped[bool] = mapped_column(nullable=False)
    est_kilometres_driven_one_way_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    est_kilometres_driven_per_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Coverage
    comprehensive_coverage: Mapped[bool] = mapped_column(nullable=False)
    collision_coverage: Mapped[bool] = mapped_column(nullable=False)
    
    # Driving record (e.g, license date, tickets, claims)
    license_class: Mapped[str] = mapped_column(String(10), nullable=False)
    years_licensed: Mapped[int] = mapped_column(Integer, nullable=False)
    driving_history: Mapped[dict] = mapped_column(JSON, nullable=True)  # e.g., {"tickets": 2, "claims": 1}
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(datetime.timezone.utc), nullable=False)
    
    quote_runs = relationship("QuoteRun", back_populates="applicant", cascade="all, delete-orphan")
    
    