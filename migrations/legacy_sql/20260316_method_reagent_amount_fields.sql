-- Migration: replace volume-specific fields with generic amount fields on method_reagent.
-- 1) Add generic columns.
ALTER TABLE method_reagent ADD COLUMN amount_per_determination FLOAT;
ALTER TABLE method_reagent ADD COLUMN amount_per_blind FLOAT DEFAULT 0;
ALTER TABLE method_reagent ADD COLUMN amount_unit VARCHAR(20) DEFAULT 'mL';

-- 2) Migrate legacy mL values into generic amount fields.
UPDATE method_reagent
SET amount_per_determination = COALESCE(amount_per_determination, volume_per_determination_ml)
WHERE volume_per_determination_ml IS NOT NULL;

UPDATE method_reagent
SET amount_per_blind = COALESCE(amount_per_blind, volume_per_blind_ml, 0);

UPDATE method_reagent
SET amount_unit = COALESCE(amount_unit, 'mL');

-- Optional cleanup (only if your SQLite version supports DROP COLUMN and all app code is migrated):
-- ALTER TABLE method_reagent DROP COLUMN volume_per_determination_ml;
-- ALTER TABLE method_reagent DROP COLUMN volume_per_blind_ml;
