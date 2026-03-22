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

**Location:** Top of `templates/praktikum/tagesansicht.html`, before all other content
**Behavior:** `position: sticky; top: 0; z-index: 100`

The ribbon shows all `PracticalDay` objects in the active semester, grouped by block in chronological order. Each day is a clickable chip linking to `?date=YYYY-MM-DD`.

**Chip content:**
- Normal day: `DD.MM. T{block_day_number}` (e.g., `08.10. T3`)
- Nachkochtag: `DD.MM. N`

**Chip states:**
- `past`: date < today, grey/muted
- `selected`: matches `selected_date`, green highlight, bold
- `future`: date > today, dark green/muted
- If today is not a practical day, no chip is selected

**Block separators:** A vertical separator and a small block label badge (`Block I`, `Block II`, …) precede each block's chips.

**Route change (`app.py`):** Pass all practical days of the active semester to the template:
```python
all_days = PracticalDay.query.filter_by(semester_id=semester.id)\
    .order_by(PracticalDay.date).all() if semester else []
```
Pass as `all_days` to the template.

---

### 2. No-Practical-Day State

**Current:** `"Für den {{ selected_date }} ist kein Praktikumstag definiert."` (YYYY-MM-DD format)

**New:** Timeline ribbon is shown (same as always). Below it:
```
Für den DD.MM.YYYY ist kein Praktikumstag definiert.
Wähle einen Tag oben aus.
```
Date is formatted as DD.MM.YYYY using a Jinja filter or inline split. No other content is shown.

---

### 3. GroupRotation Mini-UI (Tagesansicht)

Shown on normal practical days only (not Nachkochtag), between the day header badge and the student table.

**State A — Not yet configured** (no `GroupRotation` records for this day):
Show a card with:
- Auto-suggested rotation computed from the cyclic algorithm (see §6)
- Each group shown as: `Gruppe A → I.1 (Einstellung HCl)` with an analysis `<select>` pre-set to the suggestion
- A `POST /praktikum/rotation/save` button labelled "Rotation speichern"
- A "Rotation automatisch berechnen" link that resets the selects to suggestions (client-side JS)

**State B — Already configured:**
Show a read-only card displaying group→analysis mappings. Manually overridden entries (where `is_override=True`) are marked with a small ⚙ icon. An "✎ Bearbeiten" button switches to an inline edit mode (same form as State A, pre-filled).

**Override logic:** When the TA manually selects an analysis that differs from the auto-suggestion, `is_override=True` is set on that `GroupRotation`. If the TA accepts the auto-suggestion, `is_override=False`.

---

### 4. GroupRotation Admin Configuration

**Location:** `templates/admin/practical_day_form.html` — new section added below the existing fields.

Shows a table with one row per active group (A through `semester.active_group_count`):

| Gruppe | Analyse | Auto-Vorschlag |
|--------|---------|----------------|
| A | `<select>` | I.1 – Einstellung HCl |
| B | `<select>` | I.2 – Alkalimetrie |
| … | … | … |

An "Auto-ausfüllen" button fills all `<select>` elements with the cyclic suggestion (client-side JS). The existing `admin_practical_day_edit` POST handler is extended to also save `GroupRotation` records from this form.

---

### 5. New Route: Save GroupRotation

```
POST /praktikum/rotation/save
Form fields: practical_day_id, group_<code> = analysis_id for each group
```

For each group:
- Delete existing `GroupRotation` for this day + group (if any)
- Create new `GroupRotation(practical_day_id, group_code, analysis_id, is_override=<bool>)`
- `is_override=True` when the submitted analysis differs from the cyclic suggestion

Redirects back to `?date=<day.date>`.

---

### 6. Cyclic Rotation Algorithm

New function `suggest_rotation(block, block_day_number, active_group_count) -> dict[str, Analysis]` in `praktikum.py`:

```python
GROUP_CODES = ["A", "B", "C", "D"]  # extend if active_group_count > 4

def suggest_rotation(block, block_day_number, active_group_count):
    analyses = sorted(block.analyses, key=lambda a: a.ordinal)
    if not analyses:
        return {}
    groups = GROUP_CODES[:active_group_count]
    return {
        group: analyses[(i + block_day_number - 1) % len(analyses)]
        for i, group in enumerate(groups)
    }
```

Used in both the Tagesansicht mini-UI and the admin form.

---

### 7. Student Table Redesign

**Columns:** `#` | `Name` | `Gr.` | `Heute` | `Überfällig` | `Protokoll fehlt`

**"Heute" column:** Contains the rotation chip for today. Click navigates to `/results/submit/<rotation_assignment.id>`. If `rotation_assignment` is None (assignment not yet created — should not occur in normal workflow), show the analysis code as a non-clickable badge with a warning colour.

**Analysis chip design:**
- Fixed size: `62px × 28px`, centered, bold
- Label: `{analysis.code}·{attempt_abbr}` where `attempt_abbr` is:
  - `E` for Erstanalyse (attempt_number == 1)
  - `W` for Wiederholung (attempt_number == 2)
  - `W{n-1}` for attempt_number > 2
- Hover tooltip (CSS `::after`, 400ms delay via JS class toggle): full analysis name + context

**Chip colour states** (replaces current badge logic):

| State | Condition | Colour |
|-------|-----------|--------|
| Offen | `status == "assigned"`, no result | Blue |
| Wiederholung fällig | `active_result` exists and `passed == False` | Red |
| Bestanden ✓ | `status == "passed"` | Green |
| Protokoll fehlt | `status == "passed"` AND `assignment.protocol_check is None` | Orange |

**Remove:** The "Ausstehend" state (`passed is None`) — this state does not occur in the current workflow.

**"Überfällig" column:** All `extra_assignments` from `StudentSlot` (non-rotation, non-passed, non-cancelled). These are assignments from previous days that were not completed. Shows blue (not started) or red (retry needed) chips.

**"Protokoll fehlt" column:** Assignments where `status == "passed"` AND `assignment.protocol_check is None`. These are computed in the route (not in `praktikum.py`) as a separate list per student, using the same student's assignments.

**Nachkochtag:** No "Heute" or rotation columns. All open assignments shown in "Überfällig". Students with no open assignments: grey row with "Block abgeschlossen ✓".

---

### 8. `praktikum.py` Changes

- Add `suggest_rotation()` function (see §6).
- Add `protocol_missing_assignments: list[SampleAssignment]` field to `StudentSlot`.
- In `_resolve_normal_day` and `_resolve_nachkochtag`: populate `protocol_missing_assignments` = assignments where `status == "passed"` AND `protocol_check is None`.

---

### 9. Date Format Fix

In `tagesansicht.html`, replace all raw `{{ selected_date }}` (YYYY-MM-DD) with a Jinja macro that reformats to DD.MM.YYYY:

```jinja
{% set _p = selected_date.split('-') %}{{ _p[2] }}.{{ _p[1] }}.{{ _p[0] }}
```

(The display input already does this; apply consistently everywhere.)

---

## Files Changed

| File | Change |
|------|--------|
| `templates/praktikum/tagesansicht.html` | Timeline ribbon, GroupRotation mini-UI, table redesign, date format fix |
| `templates/admin/practical_day_form.html` | Add GroupRotation section |
| `app.py` | Pass `all_days` to tagesansicht; add `POST /praktikum/rotation/save`; extend `admin_practical_day_edit` POST |
| `praktikum.py` | Add `suggest_rotation()`; add `protocol_missing_assignments` to `StudentSlot` |

---

## Out of Scope

- Absence (A) recording — not modelled; can be added in a future spec
- Protocol submission workflow beyond checking presence of `ProtocolCheck` record
- Authentication / role-based access for the GroupRotation save route
