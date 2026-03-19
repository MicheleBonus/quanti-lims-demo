# Quanti-LIMS Improvements — Design Spec
**Date:** 2026-03-19
**Status:** Approved by user

---

## Overview

Three-phase improvement plan for Quanti-LIMS covering critical bug fixes, new features, and UX improvements. All changes must remain compatible with `quanti_lims_updated.db` as the new baseline database.

---

## Phase 1 — Critical Bugs + DB Migration

### 1.1 New Baseline Database

- Rename `quanti_lims_updated.db` → `quanti_lims.db` (keep old file as backup)
- All new Alembic migrations are written idempotently and run against this new baseline
- No changes to `config.py` required

### 1.2 Hydrate Correction Factor

**Problem:** When a substance is the hydrate form (e.g. Lithium citrate tetrahydrate, M = 282.1 g/mol) but the pharmacopoeial content limit is expressed on the anhydrous basis (M = 210.1 g/mol), the conversion factor is currently missing from all calculations. Results are systematically too high.

**Solution:**

- Add nullable `anhydrous_molar_mass_gmol` (Float) to `Substance` model
- New idempotent Alembic migration
- `hydrate_factor = anhydrous_molar_mass_gmol / molar_mass_gmol` when set, else `1.0`
- Apply in `MassBasedEvaluator._g_wahr`: `g_wahr = (m_s / m_ges) × p_effective × hydrate_factor`
- Access path: `sample.batch.analysis.substance.anhydrous_molar_mass_gmol`; guard against `molar_mass_gmol == 0` or `None`
- Tolerances `a_min`/`a_max` are already on anhydrous basis (Arzneibuch) — comparison is valid after correction
- Admin UI: new optional field „Wasserfreie Molmasse (g/mol)" in substance form with tooltip: *„Nur angeben wenn Arzneibuch-Gehalt auf wasserfreie Form bezogen wird (z.B. Lithiumcitrat-Tetrahydrat → 210,1 g/mol). Leer lassen bei direkter Bezugnahme."*
- Field only on `Substance`, not on `Reagent` (irrelevant for reagents)

### 1.3 Weighing Mask (Einwaagemaske) — Option C

**Problem:** Current system shows a "minimum total mass" (`target_m_ges_g`) but does not enforce a *maximum* total mass. A TA can weigh the minimum substance mass (e.g. 2.2 g) with excess diluent (e.g. 7.8 g) resulting in actual content of 22% instead of the required ≥50%.

**Correct constraint:**
```
m_ges_max = m_s_actual × p_effective / p_min
```

**New design (Option C — orientation + dynamic maximum):**

**At page load:**
- Show `m_s_min` from `batch.target_m_s_min_g`
- Show `m_ges_richtwert` from `batch.target_m_ges_g` as orientation only (not a hard constraint)
- Show `m_ges_max_at_min` = `m_s_min × p_effective / p_min` as the maximum if exactly `m_s_min` is weighed

**Live during input (JavaScript):**
- As TA enters `m_s_actual`, recalculate `m_ges_max` dynamically
- Display prominently: „Max. Gesamteinwaage: X,XX g" — green if `m_ges ≤ m_ges_max`, red + warning icon if exceeded
- `G_wahr` calculated and displayed live with red/green colour coding

**Server-side validation on submit:**
- Existing check: `m_s ≥ m_s_min` ✓ (keep)
- **Remove** the existing `m_ges_target_violation` minimum check (`m_ges_actual_g < batch.target_m_ges_g`) from `evaluate_weighing_limits` — `target_m_ges_g` is orientation only, not a hard minimum
- **New check (replace):** `m_ges > m_s_actual × p_effective / p_min` → violation, reject with error message

### 1.4 German Date Format Everywhere (Flatpickr)

**Problem:** HTML5 `<input type="date">` renders in browser locale — not controllable. Dates must be DD.MM.YYYY everywhere including inputs.

**Solution:**
- Add Flatpickr via CDN in `base.html` (CSS + JS) with `locale: "de"`
- All `<input type="date">` → `<input type="text" class="flatpickr-date">`
- Single JS initialisation block in `base.html` activates all `.flatpickr-date` inputs
- New server-side helper `parse_de_date(s)` converts `DD.MM.YYYY` → ISO before DB storage
- Existing `de_date_filter` Jinja2 filter (display) unchanged
- Internal storage remains ISO throughout

### 1.5 Verschnitt Placeholder Fix

- Change placeholder from: `"z.B. 50% Acetylsalicylsäure + 50% Lactose - Beschreibt die Zusammensetzung des Probengemisches"`
- To: `"z.B. Mannitol"`
- One-line template change

---

## Phase 2 — New Features

### 2.1 Colloquium Tracking

**Structure:** 3 colloquiums per semester (one before each block), up to 3 attempts per colloquium (Erstversuch, Nachholkolloquium, beim Chef).

**New model `Colloquium`:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer PK | |
| `student_id` | FK → student | |
| `block_id` | FK → block | Which block this colloquium precedes |
| `attempt_number` | Integer (1–3) | 1 = first attempt, 2 = Nachholkolloquium, 3 = beim Chef |
| `scheduled_date` | String (ISO), nullable | Planned date (pre-plannable) |
| `conducted_date` | String (ISO), nullable | Actual date (filled in afterwards) |
| `examiner` | String, nullable | Examiner name |
| `passed` | Boolean, nullable | NULL = not yet held / pending |
| `notes` | Text, nullable | Optional remarks |

Unique constraint: `(student_id, block_id, attempt_number)`

**Workflow:**
1. **Plan:** Enter `scheduled_date` + `examiner` in advance. `passed = NULL`
2. **Record result:** Set `conducted_date` + `passed`. If failed, next attempt is automatically suggested
3. **Exclusion:** After attempt 3 fails → `Student.is_excluded = True` (new boolean field on `Student`)

**Exclusion consequences (active):**
- When attempt 3 is saved with `passed=False`, the route handler sets `Student.is_excluded = True` and cancels all open `SampleAssignment` records for the student in the same transaction
- This is a **one-way operation** — no automatic reinstatement; cancelled assignments are not reopened if `is_excluded` is manually cleared
- No new assignments can be created for excluded students (guard in assignment creation route)
- Student visually marked throughout UI (red badge „Ausgeschieden")

**Navigation:**
- Colloquium overview accessible from both **Admin area** and **Praktikum area** (nav link in both)

**UI views:**
- Overview table per semester, filterable by block (Block I / II / III tabs)
- Columns: student name/group, Versuch 1, Versuch 2, Versuch 3, overall status
- Status badges: Bestanden (green), Nicht bestanden (red), Ausstehend/geplant (yellow), Noch nicht geplant (grey)
- „+ Kolloquium planen" button per block
- Detail view per student with full attempt history

### 2.2 Auto Group Assignment

**Trigger:** „⚡ Gruppen auto-zuteilen (N ungruppiete)" button in student list

**Algorithm:**
1. Fetch all students in semester with `group_code = NULL`, sorted alphabetically by `last_name`
2. Determine active groups: `GROUP_CODES[:semester.active_group_count]` (e.g. `["A","B","C","D"]` for 4, `["A","B","C"]` for 3)
3. Distribute round-robin over active groups: student 1 → A, 2 → B, 3 → C, 4 → D, 5 → A, ...
4. Students already having a group are skipped entirely

**Preview dialog (before saving):**
- Table showing all ungrouped students with their proposed group as an editable `<select>` dropdown
- „💾 Zuteilung speichern" and „Abbrechen" buttons
- Changes in the dialog are reflected on save

**„Alle Gruppen löschen" button:**
- Separate button in student list header
- Confirmation dialog: „Alle Gruppen-Zuteilungen für N Studierende werden gelöscht. Dies kann nicht rückgängig gemacht werden."
- Sets `group_code = NULL` for all students in the semester

### 2.3 Block Configurability

**Data model changes:**
- Add `max_days` (Integer, nullable) to `Block` model — orientation value for UI, not a hard constraint
- Add `active_group_count` (Integer, default 4) to `Semester` model — allows using 2 or 3 groups without code changes
- Remove implicit 1–4 constraint on `PracticalDay.block_day_number` — any positive integer allowed
- `GROUP_CODES = ("A", "B", "C", "D")` remains hardcoded in Python (sufficient for foreseeable use)

**Admin UI:**
- Block list gets edit buttons
- Editable fields: name (e.g. „Acidimetrie"), code (e.g. „I"), `max_days`
- New block creation and deletion (deletion blocked if PracticalDays are linked)

**Praktikum UI:**
- `block_day_number` input changed from dropdown (1–4) to free integer field

---

## Phase 3 — UX Improvements

### 3.1 V Lösung / V Aliquot — Checkbox + Clearer Labels

**Problem:** Current labels say „Leer lassen bei Direkttitration" which is misleading — direct titrations *can* use aliquots. The concept of V_Lösung is ambiguous (volume before or after adding excess reagent?).

**Solution:**

**New DB field:** `aliquot_enabled` (Boolean, default False) on `Method` model

**Data migration:** After adding the column, set `aliquot_enabled = True` for all existing `Method` rows where `v_solution_ml IS NOT NULL AND v_aliquot_ml IS NOT NULL` to avoid regressions on existing data.

**Form redesign:**
- Checkbox „Aliquotierung verwenden" controls visibility of both fields
- When unchecked: `V_Lösung` and `V_Aliquot` disabled/hidden; aliquot factor = 1.0 in calculations
- When checked: both fields enabled
- On form save with `aliquot_enabled = False`: set `v_solution_ml = NULL` and `v_aliquot_ml = NULL`

**Revised labels and descriptions:**
- „Kolbenvolumen V_Lösung (mL)" — *„Gesamtvolumen des Messkolbens (z.B. 100,0 mL). Bei Rücktitration: Kolbenvolumen nach Zugabe der Vorlage und Auffüllen."*
- „Aliquotvolumen V_Aliquot (mL)" — *„Volumen des entnommenen Aliquots für jede Titration (z.B. 20,0 mL). Aliquotfaktor = V_Aliquot / V_Lösung"*

**Calculation:** `aliquot_factor = v_aliquot_ml / v_solution_ml` when enabled, else `1.0`

**Update `_validate_aliquot`:** Only enforce `v_solution_ml`/`v_aliquot_ml` co-presence when `aliquot_enabled = True`. Update `Method.has_aliquot` property to gate on `aliquot_enabled` (remove dual truth source).

**Bug verification during implementation:** Check whether `v_solution_ml` is actually used in the ASS back-titration calculation path in `calculation_modes.py` (user reports no effect when changed — may be a silent bug).

### 3.2 Block Day Number Flexibility

- Already covered in Phase 2.3 (remove 1–4 constraint, free integer input)
- No additional changes needed

---

## Database Compatibility

- All Alembic migrations are idempotent (skip if column/table already exists)
- `quanti_lims_updated.db` is the new baseline — all new migrations run cleanly on it
- No breaking changes to existing data

## Migration Summary

| Phase | Migration | What |
|-------|-----------|------|
| 1 | `add_anhydrous_molar_mass_to_substance` | Adds `anhydrous_molar_mass_gmol` to `substance` |
| 2a | `add_colloquium_table` | New `colloquium` table with unique constraint `(student_id, block_id, attempt_number)` |
| 2b | `add_is_excluded_to_student` | Adds `is_excluded` boolean to `student` |
| 2c | `add_block_max_days_and_semester_group_count` | Adds `max_days` to `block`, `active_group_count` to `semester` |
| 3 | `add_aliquot_enabled_to_method` | Adds `aliquot_enabled` boolean to `method` |
