from pydantic import BaseModel, Field, ConfigDict
from datetime import date
from typing import Optional, List, Dict, Any

class DrivingRecordSchema(BaseModel):
    tickets_last_3_years: int = 0
    convictions_last_3_years: int = 0
    at_fault_accidents_last_6_years: int = 0
    license_suspensions: bool = False
    prior_insurance_cancelled: bool = False

class ApplicantCreate(BaseModel):
    first_name: str = Field(..., example="Aren")
    last_name: str = Field(..., example="Mirzaian")
    date_of_birth: date = Field(..., example="1995-01-01")
    gender: str = Field(..., example="Male")
    marital_status: str = Field(..., example="Single")
    
    # Address details (Ontario focus)
    street_address: str = Field(..., example="123 Main St")
    city: str = Field(..., example="Toronto")
    province: str = Field(..., example="Ontario")
    postal_code: str = Field(..., example="M1A 2B3")
    
    # Vehicle details
    vehicle_vin: Optional[str] = Field(None, example="1HGCM82633A123456")
    vehicle_year: int = Field(..., example=2020)
    vehicle_make: str = Field(..., example="Honda")
    vehicle_model: str = Field(..., example="Civic")
    vehicle_purchase_date: date = Field(..., example="2020-05-15")
    vehicle_parking_location: str = Field(..., example="Garage")
    financed_or_leased: bool = Field(..., example=True)
    
    # Usage details
    primary_use_personal_business: bool = Field(..., example=True)
    annual_mileage_km: int = Field(..., example=15000)
    anti_theft_device: bool = Field(..., example=True)
    est_kilometres_driven_one_way_per_day: int = Field(..., example=20)
    est_kilometres_driven_per_year: int = Field(..., example=15000)
    
    # Coverage
    comprehensive_coverage: bool = Field(..., example=True)
    collision_coverage: bool = Field(..., example=True)
    
    # Driving record
    license_class: str = Field(..., example="G")
    years_licensed: int = Field(..., example=5)
    driving_record: DrivingRecordSchema = Field(default_factory=DrivingRecordSchema)
    
class ApplicantResponse(ApplicantCreate):
    id: str
    
    model_config = ConfigDict(from_attributes=True)  # This allows Pydantic to read from ORM models directly