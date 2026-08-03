"""Local, no-network tests for destructive-operation and caretaker safeguards."""
import os
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

# Route imports intentionally fail closed without this production secret. The
# local tests only need a non-sensitive placeholder to exercise route logic.
os.environ.setdefault("SECRET_KEY", "local-test-secret-not-for-production")

from api.models import CaretakerUpdateRequest
from api.routes import buildings, landlord_auth


class SafetyGuardTests(unittest.TestCase):
    def setUp(self):
        self.original_building_db = buildings.get_supabase_client
        self.original_caretaker_db = landlord_auth.get_supabase_client

    def tearDown(self):
        buildings.get_supabase_client = self.original_building_db
        landlord_auth.get_supabase_client = self.original_caretaker_db

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
