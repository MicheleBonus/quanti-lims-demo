# Tagesansicht UX-Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Tagesansicht into a usable TA entry point: add a sticky timeline ribbon, build the missing GroupRotation UI (inline + admin), replace oversized badges with uniform chips, add protocol-missing tracking, and fix the date format bug.

**Architecture:** All changes are incremental additions to existing files. New logic goes in `praktikum.py` (pure functions, testable without HTTP). Route changes in `app.py` add context variables. Templates consume them. One new route handles GroupRotation saves.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5.3, pytest (in-memory SQLite)

**Spec:** `docs/superpowers/specs/2026-03-22-tagesansicht-ux-redesign.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `praktikum.py` | Add `GROUP_CODES`, `suggest_rotation()`, `_load_protocol_missing()`, `protocol_missing_assignments` on `StudentSlot` |
| Modify | `tests/test_praktikum_resolution.py` | Tests for `suggest_rotation()` and `protocol_missing_assignments` |
| Create | `tests/test_tagesansicht_routes.py` | Route-level tests for timeline, chips, GroupRotation mini-UI |
| Modify | `app.py` | Extend `praktikum_tagesansicht` route context; add `POST /praktikum/rotation/save`; extend `admin_practical_day_new` and `admin_practical_day_edit` |
| Modify | `templates/praktikum/tagesansicht.html` | Timeline ribbon, date fix, no-day state, GroupRotation mini-UI, student table redesign |
| Modify | `templates/admin/practical_day_form.html` | Add GroupRotation section with JS |

---

## Task 1: `suggest_rotation()` and `GROUP_CODES` in `praktikum.py`

**Files:**
- Modify: `praktikum.py`
- Modify: `tests/test_praktikum_resolution.py`

- [ ] **Step 1: Write failing tests** — append to `tests/test_praktikum_resolution.py`:

```python
# ─── suggest_rotation tests ──────────────────────────────────────────────────

def test_suggest_rotation_day1(db, fx):
    """Day 1: group A → first analysis, B → second."""
    from praktikum import suggest_rotation
    result = suggest_rotation(fx["block"], block_day_number=1, active_group_count=2)
    assert result["A"].id == fx["a1"].id
    assert result["B"].id == fx["a2"].id

def test_suggest_rotation_day2_wraps(db, fx):
    """Day 2: shifts by one, wraps around."""
    from praktikum import suggest_rotation
    result = suggest_rotation(fx["block"], block_day_number=2, active_group_count=2)
    assert result["A"].id == fx["a2"].id
    assert result["B"].id == fx["a1"].id

def test_suggest_rotation_more_groups_than_analyses(db, fx):
    """4 groups, 2 analyses — wraps modulo len(analyses)."""
    from praktikum import suggest_rotation
    result = suggest_rotation(fx["block"], block_day_number=1, active_group_count=4)
    assert len(result) == 4
    assert result["A"].id == fx["a1"].id
    assert result["C"].id == fx["a1"].id  # wraps back

def test_suggest_rotation_empty_block(db, fx):
    """Block with no analyses → empty dict."""
    from praktikum import suggest_rotation
    from models import Block
    empty_block = Block(code="EMPTY", name="Empty")
    db.session.add(empty_block)
    db.session.flush()
    assert suggest_rotation(empty_block, block_day_number=1, active_group_count=2) == {}

def test_suggest_rotation_null_day_number(db, fx):
    """Nachkochtag has block_day_number=None → empty dict."""
    from praktikum import suggest_rotation
    assert suggest_rotation(fx["block"], block_day_number=None, active_group_count=2) == {}
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_praktikum_resolution.py::test_suggest_rotation_day1 -v
```
Expected: `ImportError: cannot import name 'suggest_rotation'`

- [ ] **Step 3: Implement in `praktikum.py`** — add at module top, after imports:

```python
GROUP_CODES = ["A", "B", "C", "D"]
# Constrained by GROUP_CODE_ENUM in models.py — max 4 groups.


def suggest_rotation(block, block_day_number, active_group_count: int) -> dict:
    """Return {group_code: Analysis} cyclic suggestion for a normal practical day.

    Group at position i → analysis at index (i + block_day_number - 1) % len(analyses).
    Returns {} when block has no analyses or block_day_number is None (Nachkochtag).
    """
    analyses = sorted(block.analyses, key=lambda a: a.ordinal)
    if not analyses or block_day_number is None:
        return {}
    groups = GROUP_CODES[:active_group_count]
    return {
        group: analyses[(i + block_day_number - 1) % len(analyses)]
        for i, group in enumerate(groups)
    }
```

- [ ] **Step 4: Run all new tests**

```
pytest tests/test_praktikum_resolution.py -k "suggest_rotation" -v
```
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
git add praktikum.py tests/test_praktikum_resolution.py
git commit -m "feat: add suggest_rotation() and GROUP_CODES to praktikum.py"
```

---

## Task 2: `protocol_missing_assignments` on `StudentSlot`

**Files:**
- Modify: `praktikum.py`
- Modify: `tests/test_praktikum_resolution.py`

- [ ] **Step 1: Write failing tests** — append to `tests/test_praktikum_resolution.py`:

```python
# ─── protocol_missing_assignments tests ──────────────────────────────────────

def test_protocol_missing_passed_no_check(db, fx):
    """Passed assignment without ProtocolCheck → in protocol_missing_assignments."""
    from praktikum import resolve_student_slots
    from models import ProtocolCheck
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,  # group A, running_number=1
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="passed",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert len(slot_a.protocol_missing_assignments) == 1
    assert slot_a.protocol_missing_assignments[0].id == sa.id


def test_protocol_missing_passed_with_check(db, fx):
    """Passed assignment WITH ProtocolCheck → NOT in protocol_missing_assignments."""
    from praktikum import resolve_student_slots
    from models import ProtocolCheck
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="passed",
    )
    db.session.add(sa)
    db.session.flush()
    pc = ProtocolCheck(sample_assignment_id=sa.id,
                       checked_date="2099-10-07", checked_by="TA")
    db.session.add(pc)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.protocol_missing_assignments == []


def test_protocol_missing_assigned_status_excluded(db, fx):
    """Open (assigned) assignment → NOT in protocol_missing_assignments."""
    from praktikum import resolve_student_slots
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.protocol_missing_assignments == []


def test_protocol_missing_nachkochtag_block_scoped(db, fx):
    """Nachkochtag: protocol_missing_assignments scoped to current block only."""
    from praktikum import resolve_student_slots
    # passed assignment in same block → included
    sa1 = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="passed",
    )
    db.session.add(sa1)
    db.session.flush()

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert len(slot_a.protocol_missing_assignments) == 1
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_praktikum_resolution.py::test_protocol_missing_passed_no_check -v
```
Expected: `AttributeError: 'StudentSlot' object has no attribute 'protocol_missing_assignments'`

- [ ] **Step 3: Implement in `praktikum.py`**

3a. Add field to `StudentSlot` dataclass:
```python
@dataclass
class StudentSlot:
    student: Student
    rotation_analysis: Analysis | None
    rotation_assignment: SampleAssignment | None
    extra_assignments: list[SampleAssignment] = field(default_factory=list)
    protocol_missing_assignments: list[SampleAssignment] = field(default_factory=list)
```

3b. Add the helper function (add after `suggest_rotation`):
```python
def _load_protocol_missing(semester_id: int, block_id: int | None = None) -> dict:
    """Return {student_id: [SampleAssignment]} for passed assignments missing a ProtocolCheck.

    block_id: if given, restrict to analyses in that block (used for Nachkochtag).
    Uses selectinload to avoid N+1 on protocol_check.
    """
    from sqlalchemy.orm import selectinload
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
        q = q.join(Analysis, SampleBatch.analysis_id == Analysis.id).filter(
            Analysis.block_id == block_id
        )
    result: dict[int, list] = {}
    for sa in q.all():
        if sa.protocol_check is None:
            result.setdefault(sa.student_id, []).append(sa)
    return result
```

3c. Call it in both resolve functions. At the end of `_resolve_normal_day`, just before building slots:
```python
    # Protocol-missing (full semester scope for normal days)
    protocol_missing = _load_protocol_missing(semester.id)

    # Step 4: Build one slot per student
    slots: list[StudentSlot] = []
    for student in students:
        # ... existing rotation logic unchanged ...
        slots.append(StudentSlot(
            student=student,
            rotation_analysis=rotation_analysis,
            rotation_assignment=rotation_assignment,
            extra_assignments=extra,
            protocol_missing_assignments=protocol_missing.get(student.id, []),
        ))
    return slots
```

At the end of `_resolve_nachkochtag`, add block-scoped protocol-missing:
```python
    protocol_missing = _load_protocol_missing(semester.id, block_id=block_id)
    return [
        StudentSlot(
            student=student,
            rotation_analysis=None,
            rotation_assignment=None,
            extra_assignments=by_student.get(student.id, []),
            protocol_missing_assignments=protocol_missing.get(student.id, []),
        )
        for student in students
    ]
```

Note: `_resolve_nachkochtag` already has `block_id = practical_day.block_id` — use that variable.

- [ ] **Step 4: Run all new tests**

```
pytest tests/test_praktikum_resolution.py -k "protocol_missing" -v
```
Expected: all 4 PASS. Then run the full suite to ensure no regressions:
```
pytest tests/test_praktikum_resolution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add praktikum.py tests/test_praktikum_resolution.py
git commit -m "feat: add protocol_missing_assignments to StudentSlot"
```

---

## Task 3: Extend `praktikum_tagesansicht` route context

**Files:**
- Modify: `app.py` (route at line ~444)

- [ ] **Step 1: Write failing test** — create `tests/test_tagesansicht_routes.py`:

```python
"""Route-level tests for the Tagesansicht."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, SampleBatch, Sample,
    SampleAssignment, Student, PracticalDay, GroupRotation, Substance,
)


@pytest.fixture()
def tages_fx(db):
    """Minimal dataset for Tagesansicht route tests."""
    sem = Semester(code="WS_TAGES", name="Tages-Test", is_active=True, active_group_count=2)
    db.session.add(sem)
    db.session.flush()

    block = Block(code="RT", name="Route Test Block")
    db.session.add(block)
    db.session.flush()

    sub = Substance(name="TagesSubstanz", formula="Y", molar_mass_gmol=50.0)
    db.session.add(sub)
    db.session.flush()

    a1 = Analysis(name="Route Analyse 1", block_id=block.id, code="RT.1",
                  ordinal=1, substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="Route Analyse 2", block_id=block.id, code="RT.2",
                  ordinal=2, substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()

    day = PracticalDay(semester_id=sem.id, block_id=block.id,
                       date="2099-11-01", day_type="normal", block_day_number=1)
    db.session.add(day)
    db.session.flush()

    return {"sem": sem, "block": block, "a1": a1, "a2": a2, "day": day}


def test_tagesansicht_passes_all_days(client, tages_fx):
    """Route passes all_days to template (timeline ribbon data)."""
    resp = client.get("/praktikum/?date=2099-11-01")
    assert resp.status_code == 200
    assert b"RT" in resp.data  # block code appears in timeline


def test_tagesansicht_no_practical_day_shows_hint(client, tages_fx):
    """Non-practical-day shows hint message, not raw ISO date."""
    resp = client.get("/praktikum/?date=2099-11-02")
    assert resp.status_code == 200
    assert b"2099-11-02" not in resp.data          # raw ISO must not appear
    assert "02.11.2099".encode() in resp.data       # DD.MM.YYYY format
    assert "oben" in resp.data.decode("utf-8")      # hint references the ribbon
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_tagesansicht_routes.py -v
```
Expected: `test_tagesansicht_no_practical_day_shows_hint` FAIL (raw ISO date still shown)

- [ ] **Step 3: Update `praktikum_tagesansicht` route in `app.py`**

Replace the existing route body (lines ~445–461):

```python
@app.route("/praktikum/")
def praktikum_tagesansicht():
    from datetime import date as _date
    from praktikum import resolve_student_slots, suggest_rotation, GROUP_CODES
    import json

    today_str = _date.today().isoformat()
    date_str = request.args.get("date") or today_str
    semester = Semester.query.filter_by(is_active=True).first()

    all_days = (
        PracticalDay.query
        .filter_by(semester_id=semester.id)
        .order_by(PracticalDay.date)
        .all()
    ) if semester else []

    practical_day = (
        PracticalDay.query.filter_by(semester_id=semester.id, date=date_str).first()
        if semester else None
    )
    slots = resolve_student_slots(practical_day, semester) if practical_day else []

    block_analyses = []
    suggested_rotation = {}
    suggested_rotation_json = "{}"
    if practical_day and practical_day.day_type == "normal":
        block_analyses = sorted(practical_day.block.analyses, key=lambda a: a.ordinal)
        suggested_rotation = suggest_rotation(
            practical_day.block, practical_day.block_day_number, semester.active_group_count
        )
        suggested_rotation_json = json.dumps(
            {code: a.id for code, a in suggested_rotation.items()}
        )

    return render_template(
        "praktikum/tagesansicht.html",
        practical_day=practical_day,
        semester=semester,
        slots=slots,
        selected_date=date_str,
        today_str=today_str,
        all_days=all_days,
        block_analyses=block_analyses,
        suggested_rotation=suggested_rotation,
        suggested_rotation_json=suggested_rotation_json,
    )
```

- [ ] **Step 4: Run tests** (templates haven't changed yet — test for `all_days` passes because `block.code` "RT" will still appear in the existing template's rotation section if a practical day is loaded; the no-day test still fails until Task 4 fixes the template)

```
pytest tests/test_tagesansicht_routes.py::test_tagesansicht_passes_all_days -v
```
Expected: PASS (block code appears in existing template output)

```
pytest tests/test_tagesansicht_routes.py::test_tagesansicht_no_practical_day_shows_hint -v
```
Expected: still FAIL — fixed in Task 4

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: extend praktikum_tagesansicht route with timeline and rotation context"
```

---

## Task 4: Timeline ribbon, date format fix, no-day state in `tagesansicht.html`

**Files:**
- Modify: `templates/praktikum/tagesansicht.html`

This task replaces the top of the template. The Flatpickr date picker in the header stays unchanged.

- [ ] **Step 1: Replace the template content** — rewrite `templates/praktikum/tagesansicht.html` as follows. The structure is:

```jinja
{% extends "base.html" %}
{% block title %}Tagesansicht – Quanti-LIMS{% endblock %}

{# ── Date format macro ─────────────────────────────────────────────────── #}
{% macro fmt_date(iso) %}{% set _p = iso.split('-') %}{{ _p[2] }}.{{ _p[1] }}.{{ _p[0] }}{% endmacro %}

{% block content %}

{# ── Timeline ribbon ────────────────────────────────────────────────────── #}
<div class="d-flex align-items-center gap-2 flex-wrap px-2 py-2 mb-0 border-bottom bg-body-tertiary"
     style="position:sticky;top:0;z-index:100;">
  {% set ns = namespace(current_block_id=None) %}
  {% for day in all_days %}
    {% if day.block_id != ns.current_block_id %}
      {% if ns.current_block_id is not none %}
        <div class="vr mx-1" style="height:20px;"></div>
      {% endif %}
      <span class="badge text-bg-secondary" style="font-size:10px;">Block {{ day.block.code }}</span>
      {% set ns.current_block_id = day.block_id %}
    {% endif %}
    {% set chip_class = "btn btn-sm py-0 px-2 " %}
    {% if day.date == selected_date %}
      {% set chip_class = chip_class ~ "btn-success fw-bold" %}
    {% elif day.date < today_str %}
      {% set chip_class = chip_class ~ "btn-outline-secondary text-body-tertiary" %}
    {% else %}
      {% set chip_class = chip_class ~ "btn-outline-success" %}
    {% endif %}
    {% set chip_label = fmt_date(day.date) ~ " T" ~ day.block_day_number if day.day_type == "normal" else fmt_date(day.date) ~ " N" %}
    <a href="{{ url_for('praktikum_tagesansicht', date=day.date) }}"
       class="{{ chip_class }}" style="font-size:12px;">{{ chip_label }}</a>
  {% endfor %}
</div>

{# ── Header (date picker) ────────────────────────────────────────────────── #}
<div class="d-flex align-items-center gap-3 mb-3 flex-wrap mt-3">
  <div class="d-flex align-items-center gap-2">
    <i class="bi bi-calendar-day fs-3 text-success"></i>
    <h1 class="h3 mb-0">Tagesansicht</h1>
  </div>
  <form method="get" class="d-flex align-items-center gap-2 ms-auto" id="tagesansicht-date-form">
    <label class="form-label mb-0 fw-semibold">Datum:</label>
    <input type="hidden" name="date" id="date-iso" value="{{ selected_date }}">
    <input type="text" class="form-control form-control-sm flatpickr-date-nav" id="date-display"
           value="{{ fmt_date(selected_date) }}" style="width:130px">
  </form>
</div>

{# ── No semester ──────────────────────────────────────────────────────────── #}
{% if not semester %}
<div class="alert alert-warning">
  <i class="bi bi-exclamation-triangle"></i>
  Kein aktives Semester gefunden. Bitte zuerst ein Semester aktivieren.
</div>

{# ── No practical day ─────────────────────────────────────────────────────── #}
{% elif not practical_day %}
<div class="alert alert-info">
  <i class="bi bi-info-circle"></i>
  Für den <strong>{{ fmt_date(selected_date) }}</strong> ist kein Praktikumstag definiert.
  Wähle einen Tag in der Leiste oben aus.
</div>

{% else %}
  {# ... rest of content — day info, rotation mini-UI, table — added in Tasks 5 & 6 #}
  <div class="badge text-bg-secondary fs-6 mb-3">
    Block {{ practical_day.block.code }}
    {% if practical_day.day_type == "nachkochtag" %} – Nachkochtag
    {% else %} – Tag {{ practical_day.block_day_number }}{% endif %}
  </div>
  {# PLACEHOLDER: rotation mini-UI and table added in Tasks 5 & 6 #}
{% endif %}

{% endblock %}

{% block scripts %}
<script>
  flatpickr('#date-display', {
    locale: 'de',
    dateFormat: 'd.m.Y',
    allowInput: true,
    onChange: function(selectedDates, dateStr, instance) {
      if (selectedDates.length === 1) {
        const d = selectedDates[0];
        const iso = d.getFullYear() + '-'
          + String(d.getMonth() + 1).padStart(2, '0') + '-'
          + String(d.getDate()).padStart(2, '0');
        document.getElementById('date-iso').value = iso;
        document.getElementById('tagesansicht-date-form').submit();
      }
    },
  });
</script>
{% endblock %}
```

- [ ] **Step 2: Run tests**

```
pytest tests/test_tagesansicht_routes.py -v
```
Expected: both tests PASS. Then full suite:
```
pytest -v --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add templates/praktikum/tagesansicht.html
git commit -m "feat: add sticky timeline ribbon and fix date format in Tagesansicht"
```

---

## Task 5: Student table redesign

**Files:**
- Modify: `templates/praktikum/tagesansicht.html`
- Modify: `tests/test_tagesansicht_routes.py`

This task replaces the `{# PLACEHOLDER #}` in the `{% else %}` block with the redesigned student table.

- [ ] **Step 1: Add tests** — append to `tests/test_tagesansicht_routes.py`:

```python
def test_tagesansicht_chip_uses_analysis_code(client, tages_fx, db):
    """Analysis chip shows Analysis.code, not full name."""
    from models import Student, SampleBatch, Sample, SampleAssignment
    sem = tages_fx["sem"]
    day = tages_fx["day"]
    a1 = tages_fx["a1"]

    # Add GroupRotation so rotation_analysis is set
    gr = GroupRotation(practical_day_id=day.id, group_code="A",
                       analysis_id=a1.id, is_override=False)
    db.session.add(gr)

    # Add student + batch + sample + assignment
    sub_obj = tages_fx["block"]  # reuse block reference for student
    st = Student(semester_id=sem.id, matrikel="CHIP001", last_name="Chiptest",
                 first_name="Anna", running_number=1, group_code="A")
    db.session.add(st)
    db.session.flush()

    batch = SampleBatch(semester_id=sem.id, analysis_id=a1.id, total_samples_prepared=2)
    db.session.add(batch)
    db.session.flush()

    sample = Sample(batch_id=batch.id, running_number=1, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
    db.session.add(sample)
    db.session.flush()

    sa = SampleAssignment(sample_id=sample.id, student_id=st.id,
                          attempt_number=1, attempt_type="Erstanalyse",
                          assigned_date="2099-11-01", status="assigned")
    db.session.add(sa)
    db.session.flush()

    resp = client.get("/praktikum/?date=2099-11-01")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "RT.1·E" in body                          # short code used
    assert "Route Analyse 1" not in body             # full name NOT in chip
    assert "results/submit" in body                  # links to Ansage


def test_tagesansicht_protocol_missing_column(client, tages_fx, db):
    """Passed assignment without protocol check appears in Protokoll fehlt column."""
    from models import Student, SampleBatch, Sample, SampleAssignment
    sem = tages_fx["sem"]
    day = tages_fx["day"]
    a1 = tages_fx["a1"]

    st = Student(semester_id=sem.id, matrikel="PROTO001", last_name="Prototest",
                 first_name="Bob", running_number=2, group_code="B")
    db.session.add(st)
    db.session.flush()

    batch = SampleBatch(semester_id=sem.id, analysis_id=a1.id, total_samples_prepared=3)
    db.session.add(batch)
    db.session.flush()

    sample = Sample(batch_id=batch.id, running_number=2, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
    db.session.add(sample)
    db.session.flush()

    sa = SampleAssignment(sample_id=sample.id, student_id=st.id,
                          attempt_number=1, attempt_type="Erstanalyse",
                          assigned_date="2099-11-01", status="passed")
    db.session.add(sa)
    db.session.flush()

    resp = client.get("/praktikum/?date=2099-11-01")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Protokoll fehlt" in body
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_tagesansicht_routes.py::test_tagesansicht_chip_uses_analysis_code -v
```
Expected: FAIL — full names still shown in old badge markup

- [ ] **Step 3: Replace the `{% else %}` block content in `tagesansicht.html`**

Replace everything after the day badge and before `{% endif %}{# end practical_day check #}` with:

```jinja
  {# ── Day header badge ─── #}
  <div class="d-flex align-items-center gap-2 mb-3">
    <span class="badge text-bg-secondary fs-6">
      Block {{ practical_day.block.code }}
      {% if practical_day.day_type == "nachkochtag" %} – Nachkochtag
      {% else %} – Tag {{ practical_day.block_day_number }}{% endif %}
    </span>
  </div>

  {# ── GroupRotation mini-UI: added in Task 6 ─── #}

  {# ── Legend ─────────────────────────────────────────────────────────────── #}
  <div class="d-flex gap-3 flex-wrap mb-3" style="font-size:12px; color:#888;">
    <span><span class="badge text-bg-primary me-1"> </span>Offen</span>
    <span><span class="badge text-bg-danger me-1"> </span>Wiederholung fällig</span>
    <span><span class="badge me-1" style="background:#c07000"> </span>Protokoll fehlt</span>
    <span><span class="badge text-bg-success me-1"> </span>Bestanden ✓</span>
  </div>

  {# ── Student table ────────────────────────────────────────────────────────── #}
  {% if not slots %}
  <div class="alert alert-info">Keine Studierenden im aktiven Semester.</div>
  {% else %}

  {# ── Chip helper macro ─── #}
  {% macro analysis_chip(sa, analysis, is_today=false) %}
    {% if sa is none %}
      {# rotation_assignment not yet created — warning chip #}
      <span class="badge text-bg-warning" style="width:62px;height:28px;display:inline-flex;align-items:center;justify-content:center;font-size:12px;">
        {{ analysis.code }}?
      </span>
    {% else %}
      {% set abbr = "E" if sa.attempt_type == "Erstanalyse" else sa.attempt_type %}
      {% set label = analysis.code ~ "·" ~ abbr %}
      {% if sa.status == "passed" and sa.protocol_check is none %}
        {% set chip_style = "background:#8a5010;border-color:#c07000;" %}
        {% set tooltip = analysis.name ~ " – " ~ sa.attempt_type ~ " – bestanden, Protokoll fehlt" %}
      {% elif sa.status == "passed" %}
        {% set chip_style = "background:#0a2a1a;border-color:#1a6a3a;" %}
        {% set tooltip = analysis.name ~ " – " ~ sa.attempt_type ~ " – bestanden ✓" %}
        {% set label = label ~ " ✓" %}
      {% elif sa.active_result is not none and sa.active_result.passed == false %}
        {% set chip_style = "background:#3a0a0a;border-color:#8a1a1a;" %}
        {% set tooltip = analysis.name ~ " – " ~ sa.attempt_type ~ " – Wiederholung fällig" %}
      {% else %}
        {% set chip_style = "background:#0d2a5a;border-color:#1a4a9a;" %}
        {% set tooltip = analysis.name ~ " – " ~ sa.attempt_type %}
      {% endif %}
      {% set border_width = "2.5px" if is_today else "1.5px" %}
      <a href="{{ url_for('results_submit', assignment_id=sa.id) }}"
         data-bs-toggle="tooltip" title="{{ tooltip }}"
         style="display:inline-flex;align-items:center;justify-content:center;
                width:62px;height:28px;border-radius:6px;font-weight:700;
                font-size:11px;text-decoration:none;color:#eee;
                border:{{ border_width }} solid;{{ chip_style }}">
        {{ label }}
      </a>
    {% endif %}
  {% endmacro %}

  <table class="table table-hover align-middle">
    <thead>
      <tr>
        <th style="width:36px;">#</th>
        <th>Name</th>
        <th style="width:48px;">Gr.</th>
        {% if practical_day.day_type == "normal" %}
        <th style="width:90px;">Heute</th>
        <th>Überfällig</th>
        {% else %}
        <th>Offene Analysen</th>
        {% endif %}
        <th>Protokoll fehlt</th>
      </tr>
    </thead>
    <tbody>
      {% for slot in slots %}
      {% set row_dim = "table-secondary text-body-secondary" if practical_day.day_type == "nachkochtag" and not slot.extra_assignments and not slot.protocol_missing_assignments else "" %}
      <tr class="{{ row_dim }}">
        <td>{{ slot.student.running_number }}</td>
        <td>{{ slot.student.last_name }}, {{ slot.student.first_name }}</td>
        <td>
          {% if slot.student.group_code %}
            <span class="badge text-bg-secondary">{{ slot.student.group_code }}</span>
          {% else %}
            <span class="text-body-secondary">—</span>
          {% endif %}
        </td>

        {% if practical_day.day_type == "normal" %}
        {# Heute (rotation) #}
        <td>
          {% if slot.rotation_analysis is none %}
            <span class="text-body-secondary">—</span>
          {% else %}
            {{ analysis_chip(slot.rotation_assignment, slot.rotation_analysis, is_today=true) }}
          {% endif %}
        </td>
        {# Überfällig #}
        <td>
          <div class="d-flex gap-1 flex-wrap">
            {% for sa in slot.extra_assignments %}
              {{ analysis_chip(sa, sa.sample.batch.analysis) }}
            {% else %}
              <span class="text-body-secondary">—</span>
            {% endfor %}
          </div>
        </td>
        {% else %}
        {# Nachkochtag: single "Offene Analysen" column #}
        <td>
          {% if not slot.extra_assignments %}
            <span class="badge text-bg-success">Block abgeschlossen ✓</span>
          {% else %}
            <div class="d-flex gap-1 flex-wrap">
              {% for sa in slot.extra_assignments %}
                {{ analysis_chip(sa, sa.sample.batch.analysis) }}
              {% endfor %}
            </div>
          {% endif %}
        </td>
        {% endif %}

        {# Protokoll fehlt #}
        <td>
          <div class="d-flex gap-1 flex-wrap">
            {% for sa in slot.protocol_missing_assignments %}
              {{ analysis_chip(sa, sa.sample.batch.analysis) }}
            {% else %}
              <span class="text-body-secondary">—</span>
            {% endfor %}
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}{# end slots check #}
```

- [ ] **Step 4: Enable Bootstrap tooltips** — add tooltip initialization to the `{% block scripts %}` section (before the closing `</script>` tag of the Flatpickr block):

```javascript
  // Bootstrap tooltips
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el);
  });
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_tagesansicht_routes.py -v
```
Expected: all passing tests still pass, new chip and protocol tests PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/praktikum/tagesansicht.html tests/test_tagesansicht_routes.py
git commit -m "feat: redesign student table with uniform chips and protocol-missing column"
```

---

## Task 6: GroupRotation mini-UI (State A and State B)

**Files:**
- Modify: `templates/praktikum/tagesansicht.html`
- Modify: `tests/test_tagesansicht_routes.py`

- [ ] **Step 1: Add tests** — append to `tests/test_tagesansicht_routes.py`:

```python
def test_rotation_mini_ui_state_a_shows_form(client, tages_fx):
    """When no GroupRotations configured: form with selects is shown."""
    resp = client.get("/praktikum/?date=2099-11-01")
    body = resp.data.decode("utf-8")
    assert "rotation/save" in body          # save form action
    assert "Rotation speichern" in body     # submit button
    assert 'name="group_A"' in body         # select for group A


def test_rotation_mini_ui_state_b_shows_readonly(client, tages_fx, db):
    """When GroupRotations are configured: read-only view + edit button shown."""
    from models import GroupRotation
    gr = GroupRotation(practical_day_id=tages_fx["day"].id, group_code="A",
                       analysis_id=tages_fx["a1"].id, is_override=False)
    db.session.add(gr)
    db.session.flush()

    resp = client.get("/praktikum/?date=2099-11-01")
    body = resp.data.decode("utf-8")
    assert "rotation-readonly" in body       # read-only div present
    assert "rotation-edit" in body           # edit div pre-rendered (hidden)
    assert "Bearbeiten" in body              # edit button visible
    assert "RT.1" in body                    # analysis code shown
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_tagesansicht_routes.py::test_rotation_mini_ui_state_a_shows_form -v
```
Expected: FAIL — save form not yet in template

- [ ] **Step 3: Replace the `{# ── GroupRotation mini-UI: added in Task 6 ─── #}` placeholder** in the template with:

```jinja
  {# ── GroupRotation mini-UI (normal days only) ──────────────────────────── #}
  {% if practical_day.day_type == "normal" %}
  <div class="card mb-3 border-success-subtle">
    <div class="card-header d-flex align-items-center gap-2 py-2" style="background:rgba(25,135,84,.08);">
      <i class="bi bi-arrow-repeat text-success"></i>
      <span class="fw-semibold text-success">Rotation heute</span>
      {% if practical_day.group_rotations %}
      <button type="button" class="btn btn-sm btn-outline-secondary ms-auto"
              onclick="document.getElementById('rotation-readonly').classList.add('d-none');
                       document.getElementById('rotation-edit').classList.remove('d-none');">
        ✎ Bearbeiten
      </button>
      {% endif %}
    </div>
    <div class="card-body p-3">

      {# ── State B: read-only ─── #}
      {% if practical_day.group_rotations %}
      <div id="rotation-readonly">
        <div class="d-flex gap-3 flex-wrap">
          {% for gr in practical_day.group_rotations | sort(attribute="group_code") %}
          <div class="border rounded px-3 py-2 text-center position-relative">
            <div class="fw-bold fs-5">{{ gr.group_code }}</div>
            <div class="text-success small">→ {{ gr.analysis.code }}</div>
            <div class="text-body-secondary" style="font-size:11px;">{{ gr.analysis.name }}</div>
            {% if gr.is_override %}
            <span class="position-absolute top-0 end-0 me-1 mt-1" style="font-size:10px;"
                  title="Manuell überschrieben">⚙</span>
            {% endif %}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      {# ── State A: save form / State B: hidden edit form ─── #}
      <div id="rotation-edit" {% if practical_day.group_rotations %}class="d-none"{% endif %}>
        <form method="post" action="{{ url_for('praktikum_rotation_save') }}">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="practical_day_id" value="{{ practical_day.id }}">
          <div class="d-flex gap-3 flex-wrap mb-3">
            {% set active_groups = ["A","B","C","D"][:semester.active_group_count] %}
            {% for code in active_groups %}
            {% set existing_id = None %}
            {% for gr in practical_day.group_rotations %}
              {% if gr.group_code == code %}{% set existing_id = gr.analysis_id %}{% endif %}
            {% endfor %}
            <div class="border rounded px-3 py-2">
              <div class="fw-bold text-center mb-1">{{ code }}</div>
              <select name="group_{{ code }}" class="form-select form-select-sm" style="width:160px;">
                {% for a in block_analyses %}
                <option value="{{ a.id }}"
                  {% set suggested_id = suggested_rotation[code].id if code in suggested_rotation else None %}
                  {% if existing_id == a.id or (existing_id is none and suggested_id == a.id) %}selected{% endif %}>
                  {{ a.code }} – {{ a.name }}
                </option>
                {% endfor %}
              </select>
            </div>
            {% endfor %}
          </div>
          <button type="submit" class="btn btn-success btn-sm">
            {% if practical_day.group_rotations %}Rotation aktualisieren{% else %}Rotation speichern{% endif %}
          </button>
          <button type="button" class="btn btn-sm btn-outline-secondary ms-2"
                  onclick="resetToSuggestions()">
            ⟳ Rotation automatisch berechnen
          </button>
        </form>
      </div>

    </div>
  </div>
  {% endif %}{# end normal day rotation section #}
```

- [ ] **Step 4: Add JS for reset button** — append to the `{% block scripts %}` section (inside the existing `<script>` tag after the tooltip init):

```javascript
  // GroupRotation reset to suggestions
  var ROTATION_SUGGESTIONS = {{ suggested_rotation_json | safe }};
  function resetToSuggestions() {
    Object.entries(ROTATION_SUGGESTIONS).forEach(([code, analysisId]) => {
      var sel = document.querySelector('select[name="group_' + code + '"]');
      if (sel) sel.value = analysisId;
    });
  }
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_tagesansicht_routes.py -v
```
Expected: all PASS. Then full suite:
```
pytest -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add templates/praktikum/tagesansicht.html tests/test_tagesansicht_routes.py
git commit -m "feat: add GroupRotation mini-UI (State A/B) to Tagesansicht"
```

---

## Task 7: `POST /praktikum/rotation/save` route

**Files:**
- Modify: `app.py`
- Modify: `tests/test_tagesansicht_routes.py`

- [ ] **Step 1: Add tests** — append to `tests/test_tagesansicht_routes.py`:

```python
def test_rotation_save_creates_group_rotations(client, tages_fx, db):
    """POST to rotation/save creates GroupRotation records."""
    from models import GroupRotation
    day = tages_fx["day"]
    a1 = tages_fx["a1"]
    a2 = tages_fx["a2"]

    resp = client.post("/praktikum/rotation/save", data={
        "practical_day_id": day.id,
        "group_A": a1.id,
        "group_B": a2.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    grs = GroupRotation.query.filter_by(practical_day_id=day.id).all()
    assert len(grs) == 2
    codes = {gr.group_code for gr in grs}
    assert codes == {"A", "B"}


def test_rotation_save_sets_is_override(client, tages_fx, db):
    """is_override=True when submitted analysis differs from cyclic suggestion."""
    from models import GroupRotation
    day = tages_fx["day"]
    a1 = tages_fx["a1"]
    a2 = tages_fx["a2"]
    # Day 1 suggestion: A→a1, B→a2. Submit A→a2 (override), B→a2 (override for B too)
    client.post("/praktikum/rotation/save", data={
        "practical_day_id": day.id,
        "group_A": a2.id,   # differs from suggestion (a1)
        "group_B": a2.id,   # matches suggestion
    }, follow_redirects=True)
    gr_a = GroupRotation.query.filter_by(practical_day_id=day.id, group_code="A").first()
    gr_b = GroupRotation.query.filter_by(practical_day_id=day.id, group_code="B").first()
    assert gr_a.is_override is True
    assert gr_b.is_override is False


def test_rotation_save_rejects_wrong_block_analysis(client, tages_fx, db):
    """Analysis from a different block is rejected with flash error."""
    from models import Block, Analysis, Substance, GroupRotation
    other_sub = Substance(name="OtherSub99", formula="Z", molar_mass_gmol=1.0)
    db.session.add(other_sub)
    other_block = Block(code="OTHER99", name="Other Block")
    db.session.add(other_block)
    db.session.flush()
    other_a = Analysis(name="Other Analysis", block_id=other_block.id, code="OT.1",
                       ordinal=1, substance_id=other_sub.id, calculation_mode="assay_mass_based")
    db.session.add(other_a)
    db.session.flush()

    resp = client.post("/praktikum/rotation/save", data={
        "practical_day_id": tages_fx["day"].id,
        "group_A": other_a.id,
        "group_B": tages_fx["a2"].id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert GroupRotation.query.filter_by(practical_day_id=tages_fx["day"].id).count() == 0
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_tagesansicht_routes.py::test_rotation_save_creates_group_rotations -v
```
Expected: 404 — route does not exist yet

- [ ] **Step 3: Add the route to `app.py`** — add after the `praktikum_tagesansicht` route (around line 462):

```python
@app.route("/praktikum/rotation/save", methods=["POST"])
def praktikum_rotation_save():
    from praktikum import suggest_rotation, GROUP_CODES
    practical_day_id = int(request.form["practical_day_id"])
    day = db.get_or_404(PracticalDay, practical_day_id)
    semester = day.semester
    suggested = suggest_rotation(day.block, day.block_day_number, semester.active_group_count)
    groups = GROUP_CODES[:semester.active_group_count]
    for code in groups:
        raw = request.form.get(f"group_{code}")
        if not raw:
            flash(f"Fehlender Wert für Gruppe {code}.", "danger")
            return redirect(url_for("praktikum_tagesansicht", date=day.date))
        analysis_id = int(raw)
        analysis = db.get_or_404(Analysis, analysis_id)
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

Make sure `Analysis` and `GroupRotation` are imported at the top of `app.py` (they already are based on the existing imports at line 26).

- [ ] **Step 4: Run tests**

```
pytest tests/test_tagesansicht_routes.py -k "rotation_save" -v
```
Expected: all 3 PASS. Full suite:
```
pytest -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_tagesansicht_routes.py
git commit -m "feat: add POST /praktikum/rotation/save route"
```

---

## Task 8: Admin form GroupRotation section

**Files:**
- Modify: `templates/admin/practical_day_form.html`
- Modify: `app.py` (`admin_practical_day_new` and `admin_practical_day_edit`)
- Modify: `tests/test_practical_day_routes.py`

- [ ] **Step 1: Add tests** — append to `tests/test_practical_day_routes.py`:

```python
def test_admin_practical_day_edit_saves_group_rotations(client, db):
    """POST to admin edit form saves GroupRotation records."""
    from models import (
        Semester, Block, Analysis, Substance, PracticalDay, GroupRotation
    )
    sem = Semester(code="ADMIN_ROT", name="Admin Rot Test", is_active=True, active_group_count=2)
    db.session.add(sem)
    sub = Substance(name="AdminRotSub", formula="AR", molar_mass_gmol=1.0)
    db.session.add(sub)
    db.session.flush()
    block = Block(code="AR", name="Admin Rot Block")
    db.session.add(block)
    db.session.flush()
    a1 = Analysis(name="AR Analyse 1", block_id=block.id, code="AR.1",
                  ordinal=1, substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="AR Analyse 2", block_id=block.id, code="AR.2",
                  ordinal=2, substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()
    day = PracticalDay(semester_id=sem.id, block_id=block.id,
                       date="2099-12-01", day_type="normal", block_day_number=1)
    db.session.add(day)
    db.session.commit()

    resp = client.post(f"/admin/practical-days/{day.id}/edit", data={
        "date": "01.12.2099",
        "block_id": block.id,
        "day_type": "normal",
        "block_day_number": "1",
        "rotation_group_A": a1.id,
        "rotation_group_B": a2.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    grs = GroupRotation.query.filter_by(practical_day_id=day.id).all()
    assert len(grs) == 2
```

- [ ] **Step 2: Run to verify FAIL**

```
pytest tests/test_practical_day_routes.py::test_admin_practical_day_edit_saves_group_rotations -v
```
Expected: FAIL — GroupRotation records not created

- [ ] **Step 3: Add `_save_group_rotations` helper to `app.py`** — add near the top of the inner function scope (before the route definitions, or as a module-level helper):

```python
def _save_group_rotations_from_form(day, form, semester):
    """Delete and re-create GroupRotations for `day` from POSTed form data.

    Reads `rotation_group_{code}` keys. Skips missing keys silently.
    Computes is_override by comparing to cyclic suggestion.
    Called from admin_practical_day_new and admin_practical_day_edit.
    """
    from praktikum import suggest_rotation, GROUP_CODES
    if not day.block_day_number:
        return
    suggested = suggest_rotation(day.block, day.block_day_number, semester.active_group_count)
    for code in GROUP_CODES[:semester.active_group_count]:
        raw = form.get(f"rotation_group_{code}")
        if not raw:
            continue
        analysis_id = int(raw)
        suggested_analysis = suggested.get(code)
        is_override = (suggested_analysis is None) or (analysis_id != suggested_analysis.id)
        GroupRotation.query.filter_by(practical_day_id=day.id, group_code=code).delete()
        db.session.add(GroupRotation(
            practical_day_id=day.id, group_code=code,
            analysis_id=analysis_id, is_override=is_override,
        ))
```

Place this as a helper function defined inside `create_app()` or at module level (follow the existing pattern — check where other helpers like `_float` are defined).

- [ ] **Step 4: Extend `admin_practical_day_new` and `admin_practical_day_edit` in `app.py`**

In `admin_practical_day_new` POST handler, after `db.session.add(day)` and before `db.session.commit()`:
```python
db.session.flush()  # get day.id before commit
if day.day_type == "normal":
    _save_group_rotations_from_form(day, request.form, semester)
```
Also add `semester = Semester.query.filter_by(is_active=True).first()` before the POST block and pass it to the template render calls.

In `admin_practical_day_edit` POST handler, just before `db.session.commit()`:
```python
if day.day_type == "normal":
    _save_group_rotations_from_form(day, request.form, semester)
elif day.day_type == "nachkochtag":
    GroupRotation.query.filter_by(practical_day_id=day.id).delete()
```
Also load `semester = Semester.query.filter_by(is_active=True).first()` in the route handler and pass to both GET and POST `render_template` calls.

Both GET routes also need to pass `all_analyses` and `suggested_rotation_json` for the template:
```python
import json
all_analyses = Analysis.query.order_by(Analysis.block_id, Analysis.ordinal).all()
all_analyses_json = json.dumps([
    {"id": a.id, "block_id": a.block_id, "code": a.code,
     "name": a.name, "ordinal": a.ordinal}
    for a in all_analyses
])
suggested_rotation = {}
if day and day.day_type == "normal" and day.block_day_number and semester:
    from praktikum import suggest_rotation
    suggested_rotation = suggest_rotation(day.block, day.block_day_number, semester.active_group_count)
suggested_rotation_json = json.dumps(
    {code: a.id for code, a in suggested_rotation.items()}
)
# pass: semester=semester, all_analyses_json=all_analyses_json, suggested_rotation_json=suggested_rotation_json
```

- [ ] **Step 5: Update `practical_day_form.html`** — add GroupRotation section before the submit button (inside the existing `<form>`):

```jinja
{# GroupRotation section — hidden for Nachkochtag #}
<div class="mb-3" id="rotation_section">
  <label class="form-label fw-semibold">Rotation (Gruppen → Analysen)</label>
  <div class="d-flex gap-3 flex-wrap mb-2" id="rotation_rows">
    {% set active_groups = ["A","B","C","D"][:semester.active_group_count if semester else 4] %}
    {% for code in active_groups %}
    {% set existing_rot = None %}
    {% if day %}{% for gr in day.group_rotations %}{% if gr.group_code == code %}{% set existing_rot = gr %}{% endif %}{% endfor %}{% endif %}
    <div class="border rounded p-2">
      <div class="fw-bold text-center mb-1">{{ code }}</div>
      <select name="rotation_group_{{ code }}" class="form-select form-select-sm rotation-select"
              data-group="{{ code }}" style="width:180px;">
        <option value="">– keine –</option>
        {% for a in (day.block.analyses | sort(attribute='ordinal') if day else []) %}
        <option value="{{ a.id }}"
          {% if existing_rot and existing_rot.analysis_id == a.id %}selected{% endif %}>
          {{ a.code }} – {{ a.name }}
        </option>
        {% endfor %}
      </select>
      {# Auto-fill via adminAutoFill() JS; existing rotations pre-selected above #}
    </div>
    {% endfor %}
  </div>
  <button type="button" class="btn btn-sm btn-outline-secondary" onclick="adminAutoFill()">
    ⟳ Auto-ausfüllen
  </button>
</div>
```

Note: the `<option>` pre-selection logic in Jinja for the admin form is simplified — the JS `adminAutoFill()` handles the cyclic suggestion. The existing rotation records (`day.group_rotations`) are pre-selected by `existing_rot`.

- [ ] **Step 6: Add JS for admin form** — extend the existing `<script>` block in `practical_day_form.html`:

```javascript
  // Hide/show rotation section for Nachkochtag
  function updateRotationVisibility() {
    var isNach = document.getElementById('day_type_select').value === 'nachkochtag';
    document.getElementById('rotation_section').style.display = isNach ? 'none' : '';
  }
  document.getElementById('day_type_select').addEventListener('change', updateRotationVisibility);
  updateRotationVisibility();

  // Auto-fill rotation using cyclic algorithm
  var ALL_ANALYSES = {{ all_analyses_json | safe }};
  var ADMIN_SUGGESTIONS = {{ suggested_rotation_json | safe }};
  function adminAutoFill() {
    document.querySelectorAll('.rotation-select').forEach(function(sel) {
      var code = sel.dataset.group;
      if (ADMIN_SUGGESTIONS[code]) {
        sel.value = ADMIN_SUGGESTIONS[code];
      }
    });
  }
```

- [ ] **Step 7: Run tests**

```
pytest tests/test_practical_day_routes.py -v
```
Expected: all PASS. Full suite:
```
pytest -v --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add app.py templates/admin/practical_day_form.html tests/test_practical_day_routes.py
git commit -m "feat: add GroupRotation section to admin PracticalDay form"
```

---

## Final Check

- [ ] Run the full test suite one last time:

```
pytest -v --tb=short
```

- [ ] Manual smoke test: start the dev server (`flask run`), navigate to `/praktikum/`, verify timeline ribbon renders, check a practical day with and without configured rotations, enter a rotation, confirm chips appear with correct colors and links.
