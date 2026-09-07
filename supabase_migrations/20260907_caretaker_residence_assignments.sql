-- Caretaker residence assignments. Run this once in Supabase SQL Editor.
-- The API uses the service-role key and enforces the selected building set.

CREATE TABLE IF NOT EXISTS public.caretaker_properties (
  caretaker_id UUID NOT NULL REFERENCES public.caretakers(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES public.buildings(id) ON DELETE CASCADE,
  PRIMARY KEY (caretaker_id, building_id)
);

CREATE INDEX IF NOT EXISTS caretaker_properties_caretaker_id_idx
  ON public.caretaker_properties (caretaker_id);

ALTER TABLE public.caretaker_properties ENABLE ROW LEVEL SECURITY;
-- No browser-facing policies: all reads/writes go through the authenticated API.
