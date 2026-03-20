-- migrations/legacy_sql/20260320_mass_det_fields.sql
-- Mass determination fields on Analysis and configurable safety_factor on SampleBatch

ALTER TABLE analysis ADD COLUMN m_einwaage_min_mg REAL;
ALTER TABLE analysis ADD COLUMN m_einwaage_max_mg REAL;

ALTER TABLE sample_batch ADD COLUMN safety_factor REAL DEFAULT 1.2;
