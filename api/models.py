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
