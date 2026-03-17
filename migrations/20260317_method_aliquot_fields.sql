-- Replace weighing_basis + n_aliquots with v_solution_ml + v_aliquot_ml
-- for proper aliquot handling (e.g. KI: 1.5g dissolved to 100ml, 20ml aliquot)

ALTER TABLE method ADD COLUMN v_solution_ml REAL;
ALTER TABLE method ADD COLUMN v_aliquot_ml REAL;

-- Old columns (weighing_basis, n_aliquots) cannot be auto-migrated
-- because no volume information was stored. They are left in place
-- for SQLite compatibility but are no longer used by the application.
