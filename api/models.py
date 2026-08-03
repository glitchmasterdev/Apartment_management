from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import date, datetime

# Auth Schemas
class UserRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone_number: Optional[str] = ""
    role: str = "landlord"  # landlord, caretaker, or tenant
    paybill_number: Optional[str] = "247247"

class UserLoginRequest(BaseModel):
    email: str
    password: str
    expected_role: Optional[str] = None  # 'staff', 'landlord', 'caretaker', or 'tenant'

# Waitlist / Early Access Schema
class WaitlistEntry(BaseModel):
    full_name: str
    email: str
    phone_number: Optional[str] = ""
    num_units: Optional[str] = ""
    locations: Optional[str] = ""
    current_method: Optional[str] = ""

# Landlord Management Schemas
class LandlordSignupRequest(BaseModel):
    name: str
    email: str
    password: str
    contact: Optional[str] = ""

class LandlordChangeRequest(BaseModel):
    new_name: Optional[str] = None
    new_email: Optional[str] = None
    new_password: Optional[str] = None
    new_contact: Optional[str] = None

class LandlordDirectUpdateRequest(BaseModel):
    """Direct update — authenticated landlord provides current password then applies changes immediately."""
    current_password: str
    new_name: Optional[str] = None
    new_email: Optional[str] = None
    new_password: Optional[str] = None
    new_contact: Optional[str] = None

class CaretakerUpdateRequest(BaseModel):
    """Landlord-only: update caretaker login credentials."""
    caretaker_id: str
    new_name: Optional[str] = None
    new_email: Optional[str] = None
    new_password: Optional[str] = None

class LandlordForgotPasswordRequest(BaseModel):
    email: str

class LandlordResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# Building Schemas
class BuildingCreate(BaseModel):
    name: str
    location: Optional[str] = "Nairobi, Kenya"
    total_floors: Optional[int] = 4

# Unit Schemas
class UnitCreate(BaseModel):
    building_id: str
    unit_number: str
    floor: Optional[int] = 1
    rent_amount: float
    deposit_amount: Optional[float] = 0.0

class UnitUpdate(BaseModel):
    unit_number: Optional[str] = None
    floor: Optional[int] = None
    rent_amount: Optional[float] = None
    status: Optional[str] = None
    building_id: Optional[str] = None

class BuildingUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None

class BulkUnitsImport(BaseModel):
    building_id: str
    csv_data: List[dict]  # Unit Number, Floor, Rent, Deposit

# Tenant Schemas
class TenantAssignRequest(BaseModel):
    unit_id: str
    full_name: str
    phone_number: str
    email: Optional[str] = None
    lease_start_date: str
    monthly_rent: float

# Payment Schemas
class PublicPaymentSubmit(BaseModel):
    unit_number: str
    phone_number: str
    amount_paid: float
    mpesa_code: str
    tenant_message: Optional[str] = ""
    receipt_photo: Optional[str] = ""  # Base64 string

class TenantPaymentSubmit(BaseModel):
    tenant_id: Optional[str] = None
    unit_id: Optional[str] = None
    amount: float
    mpesa_code: str
    payment_date: Optional[str] = None
    notes: Optional[str] = ""

class PaymentApproveRequest(BaseModel):
    payment_ids: List[str]

class PaymentRejectRequest(BaseModel):
    payment_ids: List[str]
    reason: str

# Occupancy Schemas
class OccupancyMoveIn(BaseModel):
    unit_id: str
    tenant_id: str
    notes: Optional[str] = ""

class OccupancyMoveOut(BaseModel):
    unit_id: str
    tenant_id: str
    notes: str  # Move-out inspection / deposit withholding notes

class BulkDailyPresence(BaseModel):
    building_id: str
    action: str  # 'present' or 'absent'

# Expense Schemas
class ExpenseCreate(BaseModel):
    building_id: str
    category: str  # security, water, electricity, garbage, repairs, salaries, other
    amount: float
    date: str
    description: Optional[str] = ""
    receipt_url: Optional[str] = ""
