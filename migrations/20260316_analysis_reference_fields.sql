-- Migration: move AB reference fields from substance scope to analysis scope.

-- 1) Add new analysis-level reference columns.
ALTER TABLE analysis ADD COLUMN e_ab_g FLOAT;
ALTER TABLE analysis ADD COLUMN g_ab_min_pct FLOAT;
ALTER TABLE analysis ADD COLUMN g_ab_max_pct FLOAT;
ALTER TABLE analysis ADD COLUMN source_reference VARCHAR(255);

-- 2) Backfill from linked substance records (only when analysis fields are empty).
UPDATE analysis
SET e_ab_g = (
    SELECT s.e_ab_g
    FROM substance s
    WHERE s.id = analysis.substance_id
)
WHERE e_ab_g IS NULL;

UPDATE analysis
SET g_ab_min_pct = (
    SELECT s.g_ab_min_pct
    FROM substance s
    WHERE s.id = analysis.substance_id
)
WHERE g_ab_min_pct IS NULL;

UPDATE analysis
SET g_ab_max_pct = (
    SELECT s.g_ab_max_pct
    FROM substance s
    WHERE s.id = analysis.substance_id
)
WHERE g_ab_max_pct IS NULL;

-- Optional cleanup after full rollout:
-- ALTER TABLE substance DROP COLUMN e_ab_g;
-- ALTER TABLE substance DROP COLUMN g_ab_min_pct;
-- ALTER TABLE substance DROP COLUMN g_ab_max_pct;
