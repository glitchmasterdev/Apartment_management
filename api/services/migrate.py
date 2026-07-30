"""Database migrations are manual, never executed from the web application.

Run supabase_migrations/20260730_security_and_features.sql in Supabase SQL
Editor after reviewing it. This module intentionally has no live credentials
or service-role access.
"""
from pathlib import Path


def migration_path() -> Path:
    return Path(__file__).resolve().parents[2] / "supabase_migrations" / "20260730_security_and_features.sql"
