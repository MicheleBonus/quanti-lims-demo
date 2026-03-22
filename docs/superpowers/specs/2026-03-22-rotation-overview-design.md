# Rotation Overview — Design Spec
**Date:** 2026-03-22
**Feature:** Vorbereitung → Semesterplanung → Rotationszuweisung

---

## Context

`GroupRotation` records (model fields: `practical_day_id`, `group_code` A/B/C/D, `analysis_id`, `is_override`) are currently only configurable:
- one day at a time via the admin practical-day edit form, or
- as an emergency override in the Tagesansicht.

There is no pre-semester bulk-configuration UI. This spec adds a dedicated overview page in the Vorbereitung → Semesterplanung section.

---

## Goal

Allow TAs to configure group-to-analysis rotations for all practical days of a semester before it starts — with auto-fill (cyclic algorithm) and per-cell manual overrides.

---

## Architecture

### New routes (in `app.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vorbereitung/rotation` | Render rotation overview for the active (or selected) semester |
| POST | `/vorbereitung/rotation/save` | Upsert `GroupRotation` rows from submitted form |

### New template

`templates/admin/rotation_overview.html`
(No `templates/vorbereitung/` directory exists; all Vorbereitung routes use `templates/admin/`.)

### Nav change

`templates/base.html` — add one `<li>` in the Semesterplanung dropdown:
```html
<li><a class="dropdown-item" href="{{ url_for('vorbereitung_rotation') }}">Rotationszuweisung</a></li>
```

---

## Data Flow

### GET `/vorbereitung/rotation`

1. Determine target semester: use `?semester_id=` query param if present, otherwise `Semester.query.filter_by(is_active=True).first()`. If no active semester exists, redirect to dashboard with a flash message.
2. Load all `PracticalDay` rows for that semester where `day_type = "normal"`, ordered by date.
3. Group days by `block_id`. Order blocks by `Block.ordinal`; order days within each block by `block_day_number`.
4. For each day, load its existing `GroupRotation` rows keyed by `group_code` → `{A: GroupRotation|None, B: …, C: …, D: …}`.
5. Load all `Analysis` rows (for dropdown options).
6. Load all `Semester` rows (for the semester selector in the header).
7. Render template with: `blocks` (ordered dict of Block → [PracticalDay]), `rotations` (dict keyed by `day.id`), `analyses`, `semesters`, `active_semester`.

### POST `/vorbereitung/rotation/save`

Form field naming convention:
```
rotation[<day_id>][<group_code>] = <analysis_id>   # empty string = no rotation
semester_id = <id>                                  # hidden field
```

Processing steps:
1. Parse and validate `semester_id` from hidden form field (abort 400 if missing/invalid). Load the `Semester` row — its `active_group_count` is needed for step 4.
2. Collect all valid `day_id` values for this semester (normal days only, i.e. `day_type = "normal"`) into a set — reject any `day_id` not in this set (abort 400), since days from other semesters must never be modified.
3. Collect all valid `analysis_id` values into a set. If a submitted `analysis_id` is unknown, skip that cell silently and include the analysis code in a flash warning at the end (consistent with the existing `_save_group_rotations_from_form` pattern; aborting the whole form would break multi-block saves).
4. Only process group codes within `GROUP_CODES[:semester.active_group_count]` (i.e. A/B/C/D up to the active count). Submitted group codes outside this range are silently ignored, consistent with `_save_group_rotations_from_form`.

   For each (day_id, group_code, analysis_id) triple (where group_code is within the active range):
   - If `analysis_id` is blank: delete any existing `GroupRotation` for this (day, group) if one exists. Blank means "no rotation assigned" — the row is removed, not marked as override. This is intentional.
   - Otherwise: upsert — create or update the `GroupRotation` row.
   - Determine `is_override`: call `suggest_rotation(day.block, day.block_day_number, semester.active_group_count)` which returns `{group_code: Analysis}` (or `{}` if the block has no analyses). Let `suggested = suggested_map.get(group_code)`. If `suggested is None` OR `int(submitted_analysis_id) != suggested.id`, set `is_override = True`; otherwise `False`. Use integer comparison to avoid string/int type mismatch.
5. Commit, flash "Rotationen gespeichert." (and any skip warnings), redirect to `GET /vorbereitung/rotation?semester_id=<id>`.

**Authentication:** This route follows the same access model as other Vorbereitung routes in the app (no additional `@login_required` decorator beyond the existing app-wide session check, consistent with `/vorbereitung/stammdaten` and other admin routes).

**CSRF:** The app uses `flask_wtf.csrf.CSRFProtect` globally. The form must include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` — consistent with all other POST forms in the app.

**Trust model:** TAs have access to all semesters. Submitting an arbitrary valid `semester_id` is within the intended access scope — no additional semester-ownership check is required.

---

## UI Layout

### Page header

- Title: "Rotationszuweisung"
- Subtitle: semester name (e.g., "WS 2024/25")
- If multiple semesters exist: small `<select>` in the header to switch semester (submits via GET)

### Per-block card

One Bootstrap card per block, in block order.

```
┌──────────────────────────────────────────────────────────────┐
│ Block I                                  [Auto-fill Block I] │
├──────────┬──────────────┬──────────────┬──────────┬──────────┤
│  Tag     │   Gruppe A   │   Gruppe B   │ Gruppe C │ Gruppe D │
├──────────┼──────────────┼──────────────┼──────────┼──────────┤
│ Tag 1    │  [I.1  ▾]   │  [I.2  ▾]   │ [II.1 ▾] │ [II.2 ▾] │
│ 15.10.   │              │              │          │          │
├──────────┼──────────────┼──────────────┼──────────┼──────────┤
│ Tag 2    │  [I.2  ▾]   │  [II.1 ▾]   │ [II.2 ▾] │ [I.1  ▾] │
│ 22.10.   │              │              │          │          │
└──────────┴──────────────┴──────────────┴──────────┴──────────┘
```

- Each cell: `<select name="rotation[<day_id>][<group>]">` with blank option + all analyses ("`<code> — <name>`")
- Cells saved with `is_override = True`: small orange dot indicator (consistent with Tagesansicht override visual language)
- **Auto-fill button** (per block, JS only — no server round-trip):
  - Template emits a JSON data variable per block in an inline `<script>` block:
    ```js
    const BLOCK_DATA = {
      "<block_id>": {
        "active_group_count": 4,  // from semester.active_group_count (not a block attribute)
        "days": [
          {"day_id": 12, "block_day_number": 1},
          {"day_id": 13, "block_day_number": 2},
          ...
        ],
        // per-block analysis IDs ordered by Analysis.ordinal — used ONLY by JS auto-fill,
        // not for populating <select> options (those use the full analyses list from context)
        "analyses": [12, 7, 9, ...]  // integer IDs matching <option value="{{ a.id }}">
      }
    };
    ```
  - The auto-fill JS iterates `days`. For each day, for group at 0-based index `i`:
    pick `analyses[(i + block_day_number - 1) % analyses.length]` — modulo is over `analyses.length`, not `active_group_count`. This mirrors the Python `suggest_rotation()` formula exactly.
    Iterate only over `GROUP_CODES.slice(0, active_group_count)` (i.e. A/B/C/D up to `active_group_count` groups).
  - Cells populated by auto-fill do NOT have a visual override indicator; they are treated as non-override on save

### Form submission

- Single `<form>` wrapping all block cards
- One "Speichern" button at the bottom
- Hidden field: `semester_id`
- On success: flash "Rotationen gespeichert." and stay on the page

### Empty state

If the selected semester has no normal practical days:
> "Noch keine Praktikumstage angelegt. Bitte zuerst den Praktikumskalender konfigurieren."

---

## Testing

New file: `tests/test_rotation_overview_routes.py`

| # | Test name | What it verifies |
|---|-----------|-----------------|
| 1 | `test_get_rotation_overview_returns_200` | GET with practical days → 200, block headings present |
| 2 | `test_get_rotation_overview_empty_state` | GET with no practical days → 200, empty-state message |
| 3 | `test_get_rotation_overview_semester_param` | GET with `?semester_id=<id>` loads the correct semester's data |
| 4 | `test_post_rotation_save_creates_group_rotations` | POST valid data → `GroupRotation` rows in DB, redirect to GET |
| 5 | `test_post_rotation_save_upserts_existing` | POST over existing rotations → updates in place, no duplicates |
| 6 | `test_post_rotation_save_sets_override_flag` | Submitted value differs from `suggest_rotation()` → `is_override = True` |
| 7 | `test_post_rotation_save_clears_override_flag` | Submitted value matches `suggest_rotation()` → `is_override = False` |
| 8 | `test_post_rotation_save_blank_deletes_rotation` | Blank `analysis_id` for a cell with an existing row → row deleted |
| 9 | `test_post_rotation_save_blank_noop` | Blank `analysis_id` for a cell with no existing row → no error, no row created |
| 10 | `test_post_rotation_save_no_analyses_on_block` | Block with no analyses → `suggest_rotation()` returns `{}`, all submitted values set `is_override = True` |
| 11 | `test_post_rotation_save_ignores_nachkochtag` | POST with a Nachkochtag `day_id` directly → 400 (Nachkochtag IDs are excluded from the valid set in step 2, so submission is treated as an invalid day_id) |
| 12 | `test_post_rotation_save_rejects_invalid_day_id` | `day_id` not in semester → 400 |
| 13 | `test_post_rotation_save_skips_invalid_analysis_id` | Unknown `analysis_id` → cell skipped, flash warning, other cells saved |

No JS unit tests needed — the auto-fill algorithm is already covered in `tests/test_praktikum_resolution.py` (`test_suggest_rotation_*`).

---

## Out of Scope

- Nachkochtag rotation (no group rotation applies; `day_type = "nachkochtag"` days are excluded)
- Bulk-delete all rotations for a semester (can be done day-by-day in emergency via Tagesansicht)
- Per-analysis group-count configuration (uses existing `active_group_count` from semester)
