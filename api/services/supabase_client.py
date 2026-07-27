import os
from api.config import settings

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        if "your-project" in settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
            # Fallback mock wrapper for setup phase
            _supabase_client = MockSupabaseClient()
        else:
            try:
                from supabase import create_client
                client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY)
                # Verify Supabase connectivity
                client.table("tenants").select("id").limit(1).execute()
                _supabase_client = client
            except Exception as e:
                print(f"[Supabase Init Warning]: {e}. Using mock state client.")
                _supabase_client = MockSupabaseClient()
    return _supabase_client

class MockSupabaseClient:
    """In-memory data store for initial testing prior to full Supabase deployment."""
    def __init__(self):
        self.buildings = [
            {"id": "bldg-001", "landlord_id": "landlord-1", "name": "Kileleshwa Park Heights", "location": "Kileleshwa, Nairobi", "total_floors": 6, "created_at": "2026-01-10T10:00:00Z"},
            {"id": "bldg-002", "landlord_id": "landlord-1", "name": "Westlands Executive Suites", "location": "Westlands, Nairobi", "total_floors": 4, "created_at": "2026-02-15T10:00:00Z"}
        ]
        self.units = [
            {"id": "u-101", "building_id": "bldg-001", "unit_number": "A1", "floor": 1, "rent_amount": 45000, "deposit_amount": 45000, "deposit_paid": True, "status": "occupied", "is_active": True},
            {"id": "u-102", "building_id": "bldg-001", "unit_number": "A2", "floor": 1, "rent_amount": 48000, "deposit_amount": 48000, "deposit_paid": True, "status": "occupied", "is_active": True},
            {"id": "u-103", "building_id": "bldg-001", "unit_number": "B1", "floor": 2, "rent_amount": 40000, "deposit_amount": 40000, "deposit_paid": False, "status": "vacant", "is_active": True},
            {"id": "u-104", "building_id": "bldg-001", "unit_number": "B2", "floor": 2, "rent_amount": 42000, "deposit_amount": 42000, "deposit_paid": True, "status": "maintenance", "is_active": True},
            {"id": "u-201", "building_id": "bldg-002", "unit_number": "101", "floor": 1, "rent_amount": 65000, "deposit_amount": 65000, "deposit_paid": True, "status": "occupied", "is_active": True}
        ]
        self.tenants = [
            {"id": "t-001", "unit_id": "u-101", "full_name": "Samuel Ochieng", "phone_number": "+254712345678", "email": "samuel@example.com", "password": "samuel01", "account_number": "LND-001-KPH-A1", "lease_start_date": "2026-01-01", "monthly_rent": 45000, "is_active": True, "is_approved": True},
            {"id": "t-002", "unit_id": "u-102", "full_name": "Amina Mohamed", "phone_number": "+254722987654", "email": "amina@example.com", "password": "amina011", "account_number": "LND-001-KPH-A2", "lease_start_date": "2026-02-01", "monthly_rent": 48000, "is_active": True, "is_approved": True},
            {"id": "t-003", "unit_id": "u-201", "full_name": "David Mutua", "phone_number": "+254733112233", "email": "david@example.com", "password": "david011", "account_number": "LND-001-WES-101", "lease_start_date": "2026-03-01", "monthly_rent": 65000, "is_active": True, "is_approved": True}
        ]
        self.payments = [
            {"id": "pay-001", "tenant_id": "t-001", "unit_id": "u-101", "amount_paid": 45000, "payment_date": "2026-07-03T14:30:00Z", "mpesa_code": "QHX889123A", "tenant_message": "Rent July", "status": "approved", "rejection_reason": None},
            {"id": "pay-002", "tenant_id": "t-002", "unit_id": "u-102", "amount_paid": 30000, "payment_date": "2026-07-05T09:15:00Z", "mpesa_code": "QHY991122B", "tenant_message": "Partial July rent", "status": "approved", "rejection_reason": None},
            {"id": "pay-003", "tenant_id": "t-003", "unit_id": "u-201", "amount_paid": 65000, "payment_date": "2026-07-20T16:00:00Z", "mpesa_code": "QHZ445566C", "tenant_message": "July payment", "status": "pending", "rejection_reason": None}
        ]
        self.expenses = [
            {"id": "exp-001", "building_id": "bldg-001", "category": "security", "amount": 25000, "date": "2026-07-01", "description": "Guards salary July", "receipt_url": ""},
            {"id": "exp-002", "building_id": "bldg-001", "category": "water", "amount": 14500, "date": "2026-07-10", "description": "Nairobi Water bill", "receipt_url": ""}
        ]
        self.occupancy_logs = []
        self.audit_logs = []
        self.system_settings = [
            {"key": "copyright_text", "value": "© 2026 Nairobi Rentals . All rights reserved."},
            {"key": "philosophy_title", "value": "Redefining Nairobi property management with quiet elegance."},
            {"key": "philosophy_description", "value": "We combine digital automated M-Pesa ledger reconciliation with refined tenant services. Designed specifically for Nairobi landlords overseeing portfolios up to 1,000 units with zero friction and 100% email clarity."},
            {"key": "stat1_value", "value": "1,000+"},
            {"key": "stat1_label", "value": "Units Managed"},
            {"key": "stat2_value", "value": "98.4%"},
            {"key": "stat2_label", "value": "Occupancy Rate"},
            {"key": "stat3_value", "value": "KES 45M+"},
            {"key": "stat3_label", "value": "Annual Revenue"},
            {"key": "phil_quote", "value": "“Nairobi Rentals made managing 40 units feel effortless — receipts go out automatically.”"},
            {"key": "phil_quote_author", "value": "SANAA LANDLORDS GROUP • KILELESHWA"},
            {"key": "why_headline", "value": "Every unit. Every payment. Every tenant — in one elegant, email-driven portal."},
            {"key": "why_stat1_val", "value": "100%"},
            {"key": "why_stat1_lbl", "value": "Email-First"},
            {"key": "why_stat2_val", "value": "M-Pesa"},
            {"key": "why_stat2_lbl", "value": "Auto-Ledger"},
            {"key": "price_std_title", "value": "Standard Portfolio"},
            {"key": "price_std_val", "value": "KES 2,500"},
            {"key": "price_std_sub", "value": "/ month"},
            {"key": "price_std_features", "value": "Up to 30 units\nM-Pesa approval queue\nAutomatic email receipts\nCaretaker access"},
            {"key": "price_ent_title", "value": "Multi-Building Estate"},
            {"key": "price_ent_val", "value": "Custom Quote"},
            {"key": "price_ent_features", "value": "Unlimited units & buildings\nCustom Paybill / Till integration\nDedicated onboarding support\nCustom report exports"}
        ]
