-- Migration: move Arzneibuch-Einwaage for primary standard from Reagent to Method.
-- The same primary standard may serve different titration solutions with different
-- weighing amounts, so e_ab_g belongs on the Method (per-method), not the Reagent.

-- 1) Add the new column on method.
ALTER TABLE method ADD COLUMN e_ab_ps_g FLOAT;

-- 2) Backfill from reagent.e_ab_g via the primary_standard_id FK.
UPDATE method SET e_ab_ps_g = (
    SELECT r.e_ab_g FROM reagent r WHERE r.id = method.primary_standard_id
) WHERE primary_standard_id IS NOT NULL AND e_ab_ps_g IS NULL;

-- Note: reagent.e_ab_g column is kept for backward compatibility
-- but is no longer the source of truth. Method.e_ab_ps_g is canonical.
