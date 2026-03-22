# Spec: Tagesansicht UX-Redesign

**Date:** 2026-03-22
**Status:** Approved
**Approach:** Incremental — all changes build on existing code, no refactoring

---

## Problem Statement

The Tagesansicht is the primary entry point for TAs during lab sessions. It has several critical UX issues:

1. No GroupRotation UI exists — the data model and service logic are in place, but there is no way to create or edit GroupRotation records, causing "Keine Rotation" badges everywhere.
2. When the current day is not a practical day, an unhelpful error message appears with a wrong date format (YYYY-MM-DD instead of DD.MM.YYYY).
3. No timeline/navigation overview — TAs cannot see at a glance which practical days exist in the semester.
4. Analysis badges use full names, making them variable-width and hard to scan.
5. Badge states include a non-existent "Ausstehend" state.
6. The "Weitere offene Analysen" column does not distinguish between retries and not-yet-started analyses.
7. Passed analyses with missing protocol checks are not visible.
8. Clicking on an analysis badge does not navigate to the Ansage window.

---

## Design Decisions

- **Timeline:** Horizontal sticky ribbon, always pinned to the top of the Tagesansicht.
- **GroupRotation management:** Mini-UI inline on the Tagesansicht + full configuration on the existing PracticalDay admin edit form.
- **Rotation algorithm:** Cyclic — group at position `i` → analysis at index `(i + block_day_number - 1) % len(analyses)` (analyses ordered by `ordinal`).
- **Architecture:** Incremental, no new blueprints or refactoring.

---

## Components

### 1. Timeline Ribbon

**Location:** Top of `templates/praktikum/tagesansicht.html`, before all other content.

**Sticky behavior:** `position: sticky; top: 0; z-index: 100`. The base template's navbar (`base.html`) is not sticky (no `sticky-top` or `fixed-top` class), so `top: 0` is correct.

The ribbon shows all `PracticalDay` objects in the active semester sorted by `date` ascending. Since blocks run sequentially in time and do not interleave dates, chronological order naturally produces block-grouped output. Sort by `date` only (no join to `Block` needed).

Each day is a clickable chip (`<a href="?date=YYYY-MM-DD">`).

**Chip content:**
- Normal day: `DD.MM. T{block_day_number}` (e.g., `08.10. T3`)
- Nachkochtag: `DD.MM. N`

**Chip states** — determined by comparing `day.date` (ISO string) to `today_str` (also ISO string, passed from the route — ISO lexicographic comparison is correct for dates):
- `past`: `day.date < today_str`, grey/muted
- `selected`: `day.date == selected_date`, green highlight, bold
- `future`: `day.date > today_str`, dark green/muted
- If `selected_date` is not a practical day, no chip is `selected`

**Block separators:** A vertical separator and a small block label badge (`Block I`, `Block II`, …) precede each block's chip group. In the template, detect a block change by comparing `loop.previtem.block_id` to `day.block_id`.

**Route change (`app.py`):** Add `today_str` and `all_days` to the template context:
```python
from datetime import date as _date
today_str = _date.today().isoformat()
all_days = (
    PracticalDay.query
    .filter_by(semester_id=semester.id)
    .order_by(PracticalDay.date)
    .all()
) if semester else []
```

---

### 2. No-Practical-Day State

**Current:** `"Für den {{ selected_date }} ist kein Praktikumstag definiert."` (YYYY-MM-DD format, below the date picker only)

**New:** The timeline ribbon is shown as always. Below it, a single `alert-info`:
```
Für den DD.MM.YYYY ist kein Praktikumstag definiert.
Wähle einen Tag in der Leiste oben aus.
```
No other content is shown (no student table, no rotation section).

Date formatted via the existing split macro (§9).

---

### 3. GroupRotation Mini-UI (Tagesansicht)

Shown on **normal practical days only** (`practical_day.day_type == "normal"`), between the day header badge and the student table.

**Route adds to template context:**
- `block_analyses`: all `Analysis` objects for `practical_day.block`, ordered by `ordinal`
- `suggested_rotation`: result of `suggest_rotation(practical_day.block, practical_day.block_day_number, semester.active_group_count)` — a `dict[str, Analysis]`
- The `practical_day.group_rotations` relationship is already available on the passed `practical_day`

**State A — Not yet configured** (`not practical_day.group_rotations`):

A card with a `<form method="POST" action="/praktikum/rotation/save">`:
- Hidden field: `<input type="hidden" name="practical_day_id" value="{{ practical_day.id }}">`
- CSRF: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
- One row per active group (A … `semester.active_group_count` groups, max 4):
  `Gruppe {code}` → `<select name="group_{code}">` populated with all `block_analyses`, pre-selected to `suggested_rotation[code].id`
- The form element carries the suggestions as JSON: `data-suggestions="{{ suggested_rotation | tojson_ids }}"` where `tojson_ids` is a Jinja filter or macro that serialises `{code: analysis_id}`. Alternatively, embed as a JS variable in the `{% block scripts %}`.
- Submit button: "Rotation speichern"
- "Rotation automatisch berechnen" button (type="button"): client-side JS reads the embedded suggestions dict and resets each `<select>` to the corresponding `analysis_id`

**State B — Already configured** (`practical_day.group_rotations` is non-empty):

Read-only card showing `Gruppe {code} → {analysis.code} – {analysis.name}`. Entries with `is_override=True` show a small ⚙ icon.

An "✎ Bearbeiten" button (type="button") triggers a client-side JS toggle: hides the read-only `<div id="rotation-readonly">` and shows `<div id="rotation-edit" class="d-none">`. **Both divs are rendered server-side in the initial HTML response.** The edit div contains the same form structure as State A (including a `csrf_token` hidden field), pre-filled with the current `group_rotations` values, with submit label "Rotation aktualisieren". No page reload required for this toggle.

**Override logic (server-side, in the save route):** `is_override=True` when the submitted `analysis_id` for a group differs from `suggested_rotation[group].id`. `is_override=False` otherwise.

---

### 4. GroupRotation Admin Configuration

**Location:** `templates/admin/practical_day_form.html` — new section appended after the existing fields, inside the existing `<form>`.

**Route change:** `admin_practical_day_edit` must pass to the template:
- `block_analyses_by_block`: a dict of `{block_id: [Analysis, …]}` for all blocks (needed to populate `<select>` when block changes), or more simply: pass all analyses and let JS filter by block
- `semester`: the active semester (for `active_group_count`); load with `Semester.query.filter_by(is_active=True).first()`
- `suggested_rotation`: computed after reading the submitted/existing block — can be computed server-side on GET only (on POST it's not needed for display)
- `existing_rotations`: `{gr.group_code: gr.analysis_id for gr in day.group_rotations}` when editing

**GroupRotation section in the form:**
- Hidden when `day_type == "nachkochtag"` is selected (JS toggle, consistent with existing `block_day_number` field hide behavior)
- One `<select name="rotation_group_{code}">` per active group, populated with analyses from the currently selected block
- An "Auto-ausfüllen" button (type="button"): JS reads the current block's analyses from embedded JSON and fills each `<select>` with the cyclic suggestion for the current `block_day_number`
- CSRF already provided by the surrounding existing form

**Saving:** The existing `admin_practical_day_edit` POST handler is extended. The GroupRotation fields (`rotation_group_A`, `rotation_group_B`, etc.) are submitted as part of the **same form** as the day fields, handled in the **same POST to `/admin/practical-days/<id>/edit`**, in the same `db.session.commit()`:

1. Save day fields as before
2. Only if `day_type == "normal"`: for each code in `GROUP_CODES[:semester.active_group_count]`, read `request.form.get(f"rotation_group_{code}")`. If the value is present and non-empty, delete existing `GroupRotation` for this day+group and insert a new one with the computed `is_override` flag.
3. If `day_type == "nachkochtag"`: delete all existing `GroupRotation` records for this day (in case it was previously a normal day).
4. All in the same `db.session.commit()`. On `IntegrityError`: rollback, flash error, re-render form.

---

### 5. New Route: Save GroupRotation (Tagesansicht Mini-UI)

```
POST /praktikum/rotation/save
```

**Form fields:** `practical_day_id` (int), `csrf_token`, `group_A`, `group_B`, `group_C`, `group_D` (each an `analysis_id` int; only groups up to `active_group_count` are submitted)

**Handler logic:**
```python
day = PracticalDay.query.get_or_404(practical_day_id)
semester = day.semester          # backref provides active_group_count
suggested = suggest_rotation(day.block, day.block_day_number, semester.active_group_count)
groups = GROUP_CODES[:semester.active_group_count]  # authoritative iteration order

for code in groups:
    raw = request.form.get(f"group_{code}")          # missing key → None
    if not raw:
        flash(f"Fehlender Wert für Gruppe {code}.", "danger")
        return redirect(url_for("praktikum_tagesansicht", date=day.date))
    analysis_id = int(raw)
    # Validate analysis belongs to this block
    analysis = Analysis.query.get_or_404(analysis_id)
    if analysis.block_id != day.block_id:
        flash("Ungültige Analyse für diesen Block.", "danger")
        return redirect(url_for("praktikum_tagesansicht", date=day.date))
    suggested_analysis = suggested.get(code)
    is_override = (suggested_analysis is None) or (analysis_id != suggested_analysis.id)
    GroupRotation.query.filter_by(practical_day_id=day.id, group_code=code).delete()
    db.session.add(GroupRotation(
        practical_day_id=day.id, group_code=code,
        analysis_id=analysis_id, is_override=is_override,
    ))

try:
    db.session.commit()
    flash("Rotation gespeichert.", "success")
except IntegrityError:
    db.session.rollback()
    flash("Fehler beim Speichern der Rotation.", "danger")
return redirect(url_for("praktikum_tagesansicht", date=day.date))
```

---

### 6. Cyclic Rotation Algorithm

New module-level constant and function in `praktikum.py`:

```python
GROUP_CODES = ["A", "B", "C", "D"]
# Note: constrained by GROUP_CODE_ENUM in models.py — max 4 groups.
# active_group_count must be ≤ 4.

def suggest_rotation(block, block_day_number, active_group_count: int) -> dict[str, "Analysis"]:
    """Return {group_code: Analysis} cyclic suggestion for a normal day."""
    analyses = sorted(block.analyses, key=lambda a: a.ordinal)
    if not analyses or block_day_number is None:
        return {}
    groups = GROUP_CODES[:active_group_count]
    return {
        group: analyses[(i + block_day_number - 1) % len(analyses)]
        for i, group in enumerate(groups)
    }
```

If `block.analyses` is empty, returns `{}`. The mini-UI renders nothing in that case (no `<select>` rows, no save button).

---

### 7. Student Table Redesign

**Columns:** `#` | `Name` | `Gr.` | `Heute` | `Überfällig` | `Protokoll fehlt`

**"Heute" column:**
- If `slot.rotation_analysis is None` (student has no `group_code` or no `GroupRotation` for their group): show `—`
- If `rotation_assignment` is not None: show a clickable chip linking to `/results/submit/<rotation_assignment.id>`
- If `rotation_analysis` is set but `rotation_assignment is None` (should not occur in normal workflow): show a non-clickable orange chip with the analysis code as a warning

**Analysis chip design:**
- Fixed size: `62px × 28px`, `display: inline-flex; align-items: center; justify-content: center`
- Font: `font-weight: 700; font-size: 12px`. If content is wider than the chip (max ~9 chars for `I.1·W12`), reduce to `font-size: 10px` via CSS `font-size: clamp(10px, 1.8vw, 12px)` or a fixed small class
- Label: `{analysis.code}·{attempt_abbr}` where `attempt_abbr` is derived from `assignment.attempt_type` (the stored string, source of truth):
  - `"Erstanalyse"` → display `E`
  - Any other value (e.g. `"A"`, `"B"`) → display as-is (already a single character)
- Hover tooltip: CSS `::after` with `content: attr(data-tooltip)`, shown after 400ms JS `setTimeout` toggle of a class, or via Bootstrap's `data-bs-toggle="tooltip"`

**Chip colour states — evaluated in this priority order:**

| Priority | State | Condition | Colour |
|----------|-------|-----------|--------|
| 1 | Protokoll fehlt | `status == "passed"` AND `protocol_check is None` | Orange |
| 2 | Bestanden ✓ | `status == "passed"` AND `protocol_check is not None` | Green |
| 3 | Wiederholung fällig | `active_result` exists AND `active_result.passed == False` | Red |
| 4 | Offen | `status == "assigned"`, no result | Blue |

**Remove:** The "Ausstehend" state (`passed is None`) — does not occur in the current workflow.

**"Überfällig" column:** All `slot.extra_assignments` (non-rotation, non-passed, non-cancelled). Blue chips for not-yet-started (no result); red chips for retry needed (failed result). All originate from previous practical days (`assigned_date < today`).

**"Protokoll fehlt" column:** `slot.protocol_missing_assignments` — passed assignments with no `ProtocolCheck` record. Orange chips, clickable to `/results/submit/<assignment.id>` (where the TA can review and add the protocol check).

**Nachkochtag:** No "Heute" or "Überfällig" columns. All `slot.extra_assignments` shown in a single "Offene Analysen" column. Students with no extra assignments: grey row with "Block abgeschlossen ✓".

---

### 8. `praktikum.py` Changes

**`StudentSlot` dataclass:** Add field:
```python
protocol_missing_assignments: list[SampleAssignment] = field(default_factory=list)
```

**`suggest_rotation()` function:** Add (see §6).

**`_resolve_normal_day` and `_resolve_nachkochtag`:** Both functions receive `practical_day` and `semester`. Add a shared helper `_load_protocol_missing(semester_id, block_id=None)`:

```python
from sqlalchemy.orm import selectinload

def _load_protocol_missing(semester_id, block_id=None):
    """Return {student_id: [SampleAssignment]} for passed assignments missing a protocol check."""
    q = (
        SampleAssignment.query
        .options(selectinload(SampleAssignment.protocol_check))
        .join(Sample)
        .join(SampleBatch)
        .filter(
            SampleBatch.semester_id == semester_id,
            SampleAssignment.status == "passed",
        )
    )
    if block_id is not None:
        q = q.join(Analysis, SampleBatch.analysis_id == Analysis.id).filter(Analysis.block_id == block_id)
    result = {}
    for sa in q.all():
        if sa.protocol_check is None:
            result.setdefault(sa.student_id, []).append(sa)
    return result
```

- In `_resolve_normal_day`: call with `block_id=None` (show all semester protocol missing, not just current block — TAs need to see all missing protocols regardless of which block is active today)
- In `_resolve_nachkochtag`: call with `block_id=practical_day.block_id` (scope to current block only, consistent with how Nachkochtag already scopes open assignments to the current block)

Both Nachkochtag and normal day views display a "Protokoll fehlt" column, populated from `slot.protocol_missing_assignments`.

Use `selectinload` to avoid N+1 queries on `protocol_check`.

---

### 9. Date Format Fix

Define a reusable Jinja macro in `tagesansicht.html` (or in a shared `_macros.html`):

```jinja
{% macro fmt_date(iso) %}{% set _p = iso.split('-') %}{{ _p[2] }}.{{ _p[1] }}.{{ _p[0] }}{% endmacro %}
```

Apply consistently everywhere `selected_date` is displayed as text. The Flatpickr display input already converts correctly and is not affected.

---

## Files Changed

| File | Change |
|------|--------|
| `templates/praktikum/tagesansicht.html` | Timeline ribbon, GroupRotation mini-UI, table redesign (new columns + chips), date format macro |
| `templates/admin/practical_day_form.html` | Add GroupRotation section (hidden for Nachkochtag); pass `semester` and analyses to template |
| `app.py` | Pass `all_days`, `today_str`, `block_analyses`, `suggested_rotation` to tagesansicht; add `POST /praktikum/rotation/save`; extend `admin_practical_day_edit` GET/POST |
| `praktikum.py` | Add `GROUP_CODES`, `suggest_rotation()`; add `protocol_missing_assignments` to `StudentSlot`; add protocol-missing query to both resolve functions |

---

## Out of Scope

- Absence (A) recording — not modelled; can be added in a future spec
- Protocol submission workflow beyond checking presence of `ProtocolCheck` record
- Authentication / role-based access for the GroupRotation save route
