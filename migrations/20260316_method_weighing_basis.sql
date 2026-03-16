-- Migration: add method-level weighing basis configuration for calculation scaling.

ALTER TABLE method ADD COLUMN weighing_basis VARCHAR(30) DEFAULT 'per_preparation';
ALTER TABLE method ADD COLUMN n_aliquots INTEGER;

UPDATE method
SET weighing_basis = COALESCE(weighing_basis, 'per_preparation');

UPDATE method
SET weighing_basis = 'per_preparation'
WHERE weighing_basis NOT IN ('per_preparation', 'per_determination');

UPDATE method
SET n_aliquots = NULL
WHERE weighing_basis = 'per_preparation';

UPDATE method
SET n_aliquots = 1
WHERE weighing_basis = 'per_determination'
  AND COALESCE(n_aliquots, 0) < 1;
