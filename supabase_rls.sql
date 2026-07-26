-- ====================================================================
-- NAIROBI RENTALS — ROW LEVEL SECURITY (RLS) POLICIES
-- ====================================================================
-- Run these SQL statements in your Supabase SQL Editor to enforce 
-- server-side data isolation directly in PostgreSQL.

-- 1. Enable RLS on all tables
ALTER TABLE IF EXISTS profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS buildings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS units ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS system_settings ENABLE ROW LEVEL SECURITY;

-- 2. Drop existing policies to ensure clean state
DROP POLICY IF EXISTS "Profiles self access" ON profiles;
DROP POLICY IF EXISTS "Landlords read own buildings" ON buildings;
DROP POLICY IF EXISTS "Landlords modify own buildings" ON buildings;
DROP POLICY IF EXISTS "Units building access" ON units;
DROP POLICY IF EXISTS "Tenants own data or landlord" ON tenants;
DROP POLICY IF EXISTS "Payments tenant or landlord" ON payments;
DROP POLICY IF EXISTS "Expenses landlord access" ON expenses;

-- 3. PROFILES POLICIES
CREATE POLICY "Profiles self access" ON profiles
    FOR ALL USING (auth.uid() = id);

-- 4. BUILDINGS POLICIES (Landlords manage their own buildings)
CREATE POLICY "Landlords read own buildings" ON buildings
    FOR SELECT USING (auth.uid() = landlord_id OR auth.jwt() ->> 'role' = 'caretaker');

CREATE POLICY "Landlords modify own buildings" ON buildings
    FOR ALL USING (auth.uid() = landlord_id);

-- 5. UNITS POLICIES
CREATE POLICY "Units access policy" ON units
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM buildings 
            WHERE buildings.id = units.building_id 
            AND (buildings.landlord_id = auth.uid() OR auth.jwt() ->> 'role' IN ('caretaker', 'tenant'))
        )
    );

CREATE POLICY "Units modify policy" ON units
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM buildings 
            WHERE buildings.id = units.building_id 
            AND buildings.landlord_id = auth.uid()
        )
    );

-- 6. TENANTS POLICIES (Tenants see own record; Landlord/Caretaker see all in building)
CREATE POLICY "Tenants own data or landlord" ON tenants
    FOR ALL USING (
        id = auth.uid() 
        OR auth.jwt() ->> 'role' IN ('landlord', 'caretaker')
    );

-- 7. PAYMENTS POLICIES
CREATE POLICY "Payments tenant or landlord" ON payments
    FOR ALL USING (
        tenant_id = auth.uid() 
        OR auth.jwt() ->> 'role' IN ('landlord', 'caretaker')
    );

-- 8. EXPENSES POLICIES (Landlord & Caretaker access)
CREATE POLICY "Expenses staff access" ON expenses
    FOR ALL USING (auth.jwt() ->> 'role' IN ('landlord', 'caretaker'));

-- 9. SYSTEM SETTINGS POLICIES (Public read, Landlord write)
CREATE POLICY "Settings public read" ON system_settings
    FOR SELECT USING (true);

CREATE POLICY "Settings landlord write" ON system_settings
    FOR ALL USING (auth.jwt() ->> 'role' = 'landlord');
