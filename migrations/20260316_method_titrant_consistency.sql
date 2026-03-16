-- Migration: make method_reagent.is_titrant authoritative and keep legacy method.titrant_name in sync.

-- 1) For standardization analyses, titrant flag must not be set.
UPDATE method_reagent
SET is_titrant = 0
WHERE is_titrant = 1
  AND method_id IN (
    SELECT method.id
    FROM method
    JOIN analysis ON analysis.id = method.analysis_id
    WHERE analysis.calculation_mode = 'titrant_standardization'
  );

-- 2) Legacy bootstrap: if a method has no titrant flag, infer from method.titrant_name.
UPDATE method_reagent
SET is_titrant = 1
WHERE id IN (
    SELECT mr.id
    FROM method_reagent mr
    JOIN method m ON m.id = mr.method_id
    LEFT JOIN (
        SELECT method_id, SUM(CASE WHEN is_titrant = 1 THEN 1 ELSE 0 END) AS titrant_count
        FROM method_reagent
        GROUP BY method_id
    ) c ON c.method_id = m.id
    WHERE COALESCE(c.titrant_count, 0) = 0
      AND m.titrant_name IS NOT NULL
      AND trim(m.titrant_name) <> ''
      AND lower(trim(m.titrant_name)) = lower(trim((SELECT r.name FROM reagent r WHERE r.id = mr.reagent_id)))
);

-- 3) Enforce max one titrant per method (keep lowest id as winner).
UPDATE method_reagent
SET is_titrant = 0
WHERE id IN (
    SELECT newer.id
    FROM method_reagent newer
    JOIN method_reagent older
      ON older.method_id = newer.method_id
     AND older.is_titrant = 1
     AND newer.is_titrant = 1
     AND older.id < newer.id
);

-- 4) Keep method.titrant_name as denormalized display fallback.
UPDATE method
SET titrant_name = (
    SELECT r.name
    FROM method_reagent mr
    JOIN reagent r ON r.id = mr.reagent_id
    WHERE mr.method_id = method.id
      AND mr.is_titrant = 1
    ORDER BY mr.id
    LIMIT 1
);

-- 5) Constraint: at most one titrant flag per method.
CREATE UNIQUE INDEX IF NOT EXISTS uq_method_reagent_single_titrant
ON method_reagent(method_id)
WHERE is_titrant = 1;
