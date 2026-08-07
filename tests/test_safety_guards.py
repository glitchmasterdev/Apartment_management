"""Local, no-network tests for destructive-operation and caretaker safeguards."""
import os
import unittest
from types import SimpleNamespace
from datetime import date

from fastapi import HTTPException

# Route imports intentionally fail closed without this production secret. The
# local tests only need a non-sensitive placeholder to exercise route logic.
os.environ.setdefault("SECRET_KEY", "local-test-secret-not-for-production")

from api.models import BuildingCreate, CaretakerUpdateRequest
from api.routes import buildings, landlord_auth, payments, reports


class SafetyGuardTests(unittest.TestCase):
    def setUp(self):
        self.original_building_db = buildings.get_supabase_client
        self.original_landlord_profile = buildings._get_landlord_id
        self.original_caretaker_db = landlord_auth.get_supabase_client
        self.original_payment_db = payments.db_for
        self.original_approver_profile = payments._approval_profile_id
        self.original_unit_for_staff = payments.unit_for_staff
        self.original_report_db = reports.db_for
        self.original_allowed_buildings = reports.allowed_building_ids

    def tearDown(self):
        buildings.get_supabase_client = self.original_building_db
        buildings._get_landlord_id = self.original_landlord_profile
        landlord_auth.get_supabase_client = self.original_caretaker_db
        payments.db_for = self.original_payment_db
        payments._approval_profile_id = self.original_approver_profile
        payments.unit_for_staff = self.original_unit_for_staff
        reports.db_for = self.original_report_db
        reports.allowed_building_ids = self.original_allowed_buildings

    def test_occupied_inventory_cannot_be_deleted(self):
        db = SimpleNamespace(
            buildings=[{"id": "building-1"}],
            units=[{"id": "unit-1", "building_id": "building-1", "status": "occupied"}],
        )
        buildings.get_supabase_client = lambda: db

        with self.assertRaises(HTTPException) as building_error:
            buildings.delete_building("building-1", {"role": "landlord"})
        with self.assertRaises(HTTPException) as unit_error:
            buildings.delete_unit("unit-1", {"role": "landlord"})

        self.assertEqual(building_error.exception.status_code, 409)
        self.assertEqual(unit_error.exception.status_code, 409)
        self.assertEqual(len(db.buildings), 1)
        self.assertEqual(len(db.units), 1)

    def test_vacant_unit_can_be_deleted_in_isolated_store(self):
        db = SimpleNamespace(
            buildings=[{"id": "building-1"}],
            units=[{"id": "unit-1", "building_id": "building-1", "status": "vacant"}],
        )
        buildings.get_supabase_client = lambda: db

        result = buildings.delete_unit("unit-1", {"role": "landlord"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(db.units, [])

    def test_building_uses_valid_profile_not_legacy_login_id(self):
        class Table:
            def __init__(self):
                self.inserted = None
            def insert(self, data):
                self.inserted = data
                return self
            def execute(self):
                return SimpleNamespace(data=[self.inserted])

        class Database:
            def __init__(self):
                self.buildings_table = Table()
            def table(self, name):
                if name != "buildings":
                    raise AssertionError(f"Unexpected table: {name}")
                return self.buildings_table

        db = Database()
        buildings.get_supabase_client = lambda: db
        buildings._get_landlord_id = lambda _: "profile-landlord-id"

        result = buildings.create_building(
            BuildingCreate(name="Test Property", location="Nairobi", total_floors=2),
            {"id": "00000000-0000-0000-0000-000000000001", "role": "landlord"},
        )

        self.assertEqual(result["building"]["landlord_id"], "profile-landlord-id")

    def test_building_rejects_zero_floors(self):
        with self.assertRaises(HTTPException) as error:
            buildings.create_building(
                BuildingCreate(name="Test Property", total_floors=0), {"role": "landlord"}
            )
        self.assertEqual(error.exception.status_code, 422)

    def test_missing_landlord_profile_is_provisioned(self):
        class ProfilesTable:
            def __init__(self):
                self.record = None
            def insert(self, record):
                self.record = record
                return self
            def execute(self):
                return SimpleNamespace(data=[self.record])

        class Admin:
            def list_users(self):
                return SimpleNamespace(users=[])
            def create_user(self, _payload):
                return SimpleNamespace(user=SimpleNamespace(id="auth-landlord-id"))

        db = SimpleNamespace(
            auth=SimpleNamespace(admin=Admin()),
            profiles_table=ProfilesTable(),
        )
        db.table = lambda name: db.profiles_table if name == "profiles" else None
        buildings._get_landlord_id = lambda _: None

        profile_id = buildings._ensure_landlord_profile(
            db, {"email": "landlord@example.test", "full_name": "Landlord"}
        )

        self.assertEqual(profile_id, "auth-landlord-id")
        self.assertEqual(db.profiles_table.record["id"], "auth-landlord-id")
        self.assertEqual(db.profiles_table.record["role"], "landlord")

    def test_payment_approval_uses_profile_foreign_key(self):
        class PaymentQuery:
            def __init__(self, table, mode):
                self.table, self.mode = table, mode
            def eq(self, _field, _value):
                return self
            def limit(self, _count):
                return self
            def execute(self):
                if self.mode == "select":
                    return SimpleNamespace(data=[{"unit_id": "unit-1"}])
                return SimpleNamespace(data=[self.table.updated])

        class PaymentsTable:
            def __init__(self):
                self.updated = None
            def select(self, _fields):
                return PaymentQuery(self, "select")
            def update(self, values):
                self.updated = values
                return PaymentQuery(self, "update")

        table = PaymentsTable()
        db = SimpleNamespace(table=lambda name: table if name == "payments" else None)
        payments.db_for = lambda _user: db
        payments._approval_profile_id = lambda _db, _user: "profile-landlord-id"
        payments.unit_for_staff = lambda *_args: {"id": "unit-1"}

        result = payments._change(["payment-1"], "approved", {"id": "legacy-login-id", "role": "landlord"})

        self.assertEqual(result["approved_count"], 1)
        self.assertEqual(table.updated["approved_by"], "profile-landlord-id")

    def test_rent_received_counts_only_current_month_approved_payments(self):
        current_month = date.today().strftime("%Y-%m")

        class Query:
            def __init__(self, rows):
                self.rows = rows
            def select(self, _fields): return self
            def in_(self, _field, _values): return self
            def eq(self, _field, _value): return self
            def execute(self): return SimpleNamespace(data=self.rows)

        class Database:
            def table(self, name):
                rows = {
                    "units": [{"id": "unit-1", "status": "occupied", "building_id": "building-1", "rent_amount": 9000}],
                    "tenants": [{"unit_id": "unit-1"}],
                    "payments": [
                        {"amount_paid": 5000, "payment_date": f"{current_month}-06T12:00:00Z"},
                        {"amount_paid": 7000, "payment_date": "2020-01-01T12:00:00Z"},
                    ],
                }[name]
                return Query(rows)

        reports.db_for = lambda _user: Database()
        reports.allowed_building_ids = lambda _db, _user: {"building-1"}

        result = reports.dashboard(None, {"role": "landlord"})

        self.assertEqual(result["kpis"]["monthly_revenue"], 9000)
        self.assertEqual(result["kpis"]["rent_received"], 5000)

    def test_month_close_retains_payments_and_records_cycle(self):
        class SettingsQuery:
            def __init__(self): self.record = None
            def upsert(self, record): self.record = record; return self
            def execute(self): return SimpleNamespace(data=[self.record])

        query = SettingsQuery()
        reports.db_for = lambda _user: SimpleNamespace(table=lambda name: query if name == "system_settings" else None)

        result = reports.close_monthly_cycle({"role": "landlord"})

        self.assertEqual(result["status"], "success")
        self.assertTrue(query.record["key"].startswith("payment_cycle_closed:"))

    def test_caretaker_update_targets_selected_account_only(self):
        db = SimpleNamespace(caretakers=[
            {"id": "care-1", "name": "First", "email": "first@example.test", "password_hash": "old"},
            {"id": "care-2", "name": "Second", "email": "second@example.test", "password_hash": "old"},
        ])
        landlord_auth.get_supabase_client = lambda: db

        result = landlord_auth.update_caretaker(
            CaretakerUpdateRequest(caretaker_id="care-2", new_name="Updated"),
            {"role": "landlord"},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(db.caretakers[0]["name"], "First")
        self.assertEqual(db.caretakers[1]["name"], "Updated")

    def test_caretaker_email_must_be_unique(self):
        db = SimpleNamespace(caretakers=[
            {"id": "care-1", "name": "First", "email": "first@example.test"},
            {"id": "care-2", "name": "Second", "email": "second@example.test"},
        ])
        landlord_auth.get_supabase_client = lambda: db

        with self.assertRaises(HTTPException) as error:
            landlord_auth.update_caretaker(
                CaretakerUpdateRequest(caretaker_id="care-2", new_email="first@example.test"),
                {"role": "landlord"},
            )

        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
