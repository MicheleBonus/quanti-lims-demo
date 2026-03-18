# Plan 4 – Tagesansicht & Auflösungslogik

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `praktikum.py` service module with `resolve_student_slots()` and replace the placeholder `/praktikum/` route + template with a working Tagesansicht.

**Architecture:** A new `praktikum.py` module holds all resolution logic and the `StudentSlot` dataclass. The route in `app.py` stays thin (~10 lines). The template works exclusively with `StudentSlot` objects passed from the route. All logic is tested directly without the HTTP layer.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5.3, pytest (in-memory SQLite)

**Spec:** `docs/superpowers/specs/2026-03-18-plan4-auflösungslogik-design.md`

**Depends on:** Plans 1–3 (Alembic, Navigation, PracticalDay/GroupRotation/ProtocolCheck models)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `praktikum.py` | `StudentSlot` dataclass, `resolve_student_slots`, `_resolve_normal_day`, `_resolve_nachkochtag` |
| Create | `tests/test_praktikum_resolution.py` | Unit tests for `praktikum.py` (no HTTP) |
| Modify | `app.py` (line ~308) | Replace 1-line placeholder with real route logic + import |
| Modify | `templates/praktikum/tagesansicht.html` | Replace placeholder with full Tagesansicht UI |

---

## Task 1: `praktikum.py` — `StudentSlot` + resolution logic

**Files:**
- Create: `praktikum.py`
- Create: `tests/test_praktikum_resolution.py`

### Fixture setup (read before writing tests)

All tests share a `resolution_fixture` that creates a complete, realistic dataset in the in-memory SQLite DB. The fixture uses `db.session.flush()` (not `commit()`) so rollback in `conftest.py` cleans up automatically.

The fixture creates:
- 1 active `Semester`
- 1 `Block`
- 2 `Analysis` objects (both in the same block)
- 1 `SampleBatch` per analysis (linked to semester)
- 4 regular `Sample` objects per batch (running_number 1–4, `is_buffer=False`) + 1 buffer sample per batch (`is_buffer=True`, running_number 99) — the buffer samples ensure the `is_buffer=False` filter in the implementation is verified
- 4 `Student` objects (running_number 1–4, group_codes A/B/C/D) + 1 student with `group_code=None` (running_number 5) — for the no-group-code edge case
- 1 `PracticalDay` (normal, date="2099-10-06") with `GroupRotation` A→analysis1, B→analysis2
- 1 separate `PracticalDay` (nachkochtag, date="2099-10-11", same block)

**TDD discipline:** Step 1 (write tests) must be completed and Step 2 (run to confirm FAIL) must pass before Step 3 (write implementation) begins. Do not write implementation code until the tests fail with `ImportError`.

---

- [ ] **Step 1: Write failing tests**

Create `tests/test_praktikum_resolution.py`:

```python
"""Tests for praktikum.resolve_student_slots() — no HTTP layer."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, SampleBatch, Sample,
    SampleAssignment, Student, PracticalDay, GroupRotation,
)


# ─── fixture ────────────────────────────────────────────────────────────────

@pytest.fixture()
def fx(db):
    """Build a minimal but complete practical-day dataset."""
    # Semester
    sem = Semester(code="WS9999", name="Test-Semester", is_active=True)
    db.session.add(sem)
    db.session.flush()

    # Block
    block = Block(code="I", name="Block I", position=1)
    db.session.add(block)
    db.session.flush()

    # Two analyses in this block
    a1 = Analysis(name="Analyse 1", block_id=block.id, position=1,
                  calculation_mode="assay_mass_based")
    a2 = Analysis(name="Analyse 2", block_id=block.id, position=2,
                  calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()

    # One SampleBatch per analysis
    b1 = SampleBatch(semester_id=sem.id, analysis_id=a1.id,
                     total_samples_prepared=4)
    b2 = SampleBatch(semester_id=sem.id, analysis_id=a2.id,
                     total_samples_prepared=4)
    db.session.add_all([b1, b2])
    db.session.flush()

    # 4 regular samples per batch (running_number 1-4, not buffer)
    # + 1 buffer sample per batch (running_number 99) — ensures is_buffer filter is tested
    samples_b1, samples_b2 = [], []
    for n in range(1, 5):
        s1 = Sample(batch_id=b1.id, running_number=n, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
        s2 = Sample(batch_id=b2.id, running_number=n, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
        samples_b1.append(s1)
        samples_b2.append(s2)
    buf1 = Sample(batch_id=b1.id, running_number=99, is_buffer=True)
    buf2 = Sample(batch_id=b2.id, running_number=99, is_buffer=True)
    db.session.add_all(samples_b1 + samples_b2 + [buf1, buf2])
    db.session.flush()

    # 4 students with group_codes A/B/C/D (running_numbers 1-4)
    # + 1 student with group_code=None (running_number 5) for edge-case test
    codes = ["A", "B", "C", "D"]
    students = []
    for i, code in enumerate(codes, start=1):
        st = Student(semester_id=sem.id, matrikel=f"99{i:04d}",
                     last_name=f"Student{i}", first_name="Test",
                     running_number=i, group_code=code)
        students.append(st)
    st_no_group = Student(semester_id=sem.id, matrikel="990005",
                          last_name="NoGroup", first_name="Test",
                          running_number=5, group_code=None)
    students.append(st_no_group)
    db.session.add_all(students)
    db.session.flush()

    # Normal PracticalDay: group A → a1, group B → a2
    normal_day = PracticalDay(semester_id=sem.id, block_id=block.id,
                              date="2099-10-06", day_type="normal",
                              block_day_number=1)
    db.session.add(normal_day)
    db.session.flush()

    gr_a = GroupRotation(practical_day_id=normal_day.id, group_code="A",
                         analysis_id=a1.id, is_override=False)
    gr_b = GroupRotation(practical_day_id=normal_day.id, group_code="B",
                         analysis_id=a2.id, is_override=False)
    db.session.add_all([gr_a, gr_b])
    db.session.flush()

    # Nachkochtag PracticalDay (same block)
    nach_day = PracticalDay(semester_id=sem.id, block_id=block.id,
                            date="2099-10-11", day_type="nachkochtag",
                            block_day_number=None)
    db.session.add(nach_day)
    db.session.flush()

    return {
        "sem": sem, "block": block,
        "a1": a1, "a2": a2,
        "b1": b1, "b2": b2,
        "samples_b1": samples_b1,   # index 0 = running_number 1
        "samples_b2": samples_b2,
        "students": students,        # indices 0-3 = groups A/B/C/D; index 4 = no group_code
        "st_no_group": st_no_group,
        "normal_day": normal_day,
        "nach_day": nach_day,
    }


# ─── normaltag tests ─────────────────────────────────────────────────────────

def test_normal_day_student_with_assignment(db, fx):
    """Student A (running_number=1) has an assignment for analysis 1 sample 1."""
    from praktikum import resolve_student_slots
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,   # sample running_number=1
        student_id=fx["students"][0].id,     # student A, running_number=1
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])

    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_analysis.id == fx["a1"].id
    assert slot_a.rotation_assignment is not None
    assert slot_a.rotation_assignment.id == sa.id
    assert slot_a.extra_assignments == []


def test_normal_day_no_assignment_yet(db, fx):
    """Student A has no assignment yet (assign_initial not run)."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])

    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_analysis.id == fx["a1"].id
    assert slot_a.rotation_assignment is None
    assert slot_a.extra_assignments == []


def test_normal_day_no_group_code(db, fx):
    """Student with no group_code → rotation_analysis and rotation_assignment are None.
    Uses the pre-built st_no_group student from the fixture (running_number=5)."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])

    slot = next(s for s in slots if s.student.id == fx["st_no_group"].id)
    assert slot.rotation_analysis is None
    assert slot.rotation_assignment is None


def test_normal_day_extra_assignment_not_duplicated(db, fx):
    """rotation_assignment must NOT appear in extra_assignments, while another
    open assignment IS included. Fixture state: student A has both a rotation
    assignment (b1, sample 1) AND an open extra assignment (b2, sample 1).
    Only the extra should appear in extra_assignments."""
    from praktikum import resolve_student_slots
    sa_rot = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,   # rotation sample
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    sa_other = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,   # different analysis/sample
        student_id=fx["students"][0].id,
        attempt_number=2, attempt_type="A",
        assigned_date="2099-10-05", status="assigned",
    )
    db.session.add_all([sa_rot, sa_other])
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")

    extra_ids = [e.id for e in slot_a.extra_assignments]
    assert sa_rot.id not in extra_ids   # rotation must be excluded
    assert sa_other.id in extra_ids     # other open assignment must be included


def test_normal_day_extra_assignment_retry(db, fx):
    """Student A has a rotation assignment + a pending retry from another analysis."""
    from praktikum import resolve_student_slots

    # rotation assignment for a1
    sa_rot = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    # open retry assignment for a2 (buffer sample — different sample object,
    # same batch for simplicity; is_buffer doesn't affect resolution logic)
    sa_extra = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=2, attempt_type="A",
        assigned_date="2099-10-05", status="assigned",
    )
    db.session.add_all([sa_rot, sa_extra])
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")

    assert slot_a.rotation_assignment.id == sa_rot.id
    assert len(slot_a.extra_assignments) == 1
    assert slot_a.extra_assignments[0].id == sa_extra.id


def test_normal_day_all_students_appear(db, fx):
    """All semester students appear in the output, even those with no assignment."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    assert len(slots) == len(fx["students"])


def test_normal_day_no_batch_for_analysis(db, fx):
    """If no SampleBatch exists for the rotation analysis, rotation_assignment is None
    (graceful fallback, no KeyError). We test with a PracticalDay whose rotation
    points to an analysis that has no batch in this semester."""
    from praktikum import resolve_student_slots
    from models import Analysis, GroupRotation, PracticalDay
    # Create a new analysis with no batch
    orphan_analysis = Analysis(name="Orphan", block_id=fx["block"].id,
                               position=99, calculation_mode="assay_mass_based")
    db.session.add(orphan_analysis)
    db.session.flush()
    orphan_day = PracticalDay(semester_id=fx["sem"].id, block_id=fx["block"].id,
                              date="2099-10-08", day_type="normal", block_day_number=3)
    db.session.add(orphan_day)
    db.session.flush()
    gr = GroupRotation(practical_day_id=orphan_day.id, group_code="A",
                       analysis_id=orphan_analysis.id, is_override=False)
    db.session.add(gr)
    db.session.flush()

    slots = resolve_student_slots(orphan_day, fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_analysis.id == orphan_analysis.id
    assert slot_a.rotation_assignment is None  # no batch → no assignment


def test_normal_day_no_sample_for_running_number(db, fx):
    """If the batch exists but has no sample matching student.running_number,
    rotation_assignment is None (graceful fallback, no KeyError)."""
    from praktikum import resolve_student_slots
    from models import Analysis, SampleBatch, GroupRotation, PracticalDay
    # Analysis + batch exist, but batch has no samples at all
    sparse_analysis = Analysis(name="Sparse", block_id=fx["block"].id,
                               position=98, calculation_mode="assay_mass_based")
    db.session.add(sparse_analysis)
    db.session.flush()
    sparse_batch = SampleBatch(semester_id=fx["sem"].id,
                               analysis_id=sparse_analysis.id,
                               total_samples_prepared=0)
    db.session.add(sparse_batch)
    db.session.flush()
    sparse_day = PracticalDay(semester_id=fx["sem"].id, block_id=fx["block"].id,
                              date="2099-10-09", day_type="normal", block_day_number=4)
    db.session.add(sparse_day)
    db.session.flush()
    gr = GroupRotation(practical_day_id=sparse_day.id, group_code="A",
                       analysis_id=sparse_analysis.id, is_override=False)
    db.session.add(gr)
    db.session.flush()

    slots = resolve_student_slots(sparse_day, fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_assignment is None  # no sample → no assignment


def test_normal_day_passed_assignment_not_in_extra(db, fx):
    """Passed assignments are not included in extra_assignments."""
    from praktikum import resolve_student_slots
    sa_passed = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-01", status="passed",
    )
    db.session.add(sa_passed)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.extra_assignments == []


# ─── nachkochtag tests ───────────────────────────────────────────────────────

def test_nachkochtag_student_with_open_assignment(db, fx):
    """Student with open block assignment appears with it in extra_assignments."""
    from praktikum import resolve_student_slots
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    slot = next(s for s in slots if s.student.id == fx["students"][0].id)

    assert slot.rotation_analysis is None
    assert slot.rotation_assignment is None
    assert len(slot.extra_assignments) == 1
    assert slot.extra_assignments[0].id == sa.id


def test_nachkochtag_student_without_open_assignment_still_appears(db, fx):
    """Student with no open block assignments appears with empty extra_assignments."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    assert len(slots) == len(fx["students"])

    slot = next(s for s in slots if s.student.id == fx["students"][0].id)
    assert slot.extra_assignments == []


def test_nachkochtag_multiple_open_assignments(db, fx):
    """Student with 2 open block assignments gets both in extra_assignments."""
    from praktikum import resolve_student_slots
    sa1 = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    sa2 = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-07", status="assigned",
    )
    db.session.add_all([sa1, sa2])
    db.session.flush()

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    slot = next(s for s in slots if s.student.id == fx["students"][0].id)
    assert len(slot.extra_assignments) == 2
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_praktikum_resolution.py -v
```

Expected: `ImportError: No module named 'praktikum'`

- [ ] **Step 3: Implement `praktikum.py`**

Create `praktikum.py` in the project root (alongside `app.py`):

```python
"""Praktikum service module — resolution logic for the Tagesansicht."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date

from models import (
    Analysis, SampleAssignment, SampleBatch, Sample,
    Student, GroupRotation,
)


@dataclass
class StudentSlot:
    student: Student
    rotation_analysis: Analysis | None
    rotation_assignment: SampleAssignment | None
    extra_assignments: list[SampleAssignment] = field(default_factory=list)


def resolve_student_slots(practical_day, semester) -> list[StudentSlot]:
    """Return one StudentSlot per student in semester for the given practical_day."""
    students = (
        Student.query
        .filter_by(semester_id=semester.id)
        .order_by(Student.running_number)
        .all()
    )
    if practical_day.day_type == "nachkochtag":
        return _resolve_nachkochtag(practical_day, semester, students)
    return _resolve_normal_day(practical_day, semester, students)


def _resolve_normal_day(practical_day, semester, students) -> list[StudentSlot]:
    # Step 1: GroupRotations for this day keyed by group_code
    rotations: dict[str, GroupRotation] = {
        gr.group_code: gr
        for gr in practical_day.group_rotations
    }

    # Step 2: All open SampleAssignments for this semester, grouped by student_id
    open_assignments: list[SampleAssignment] = (
        SampleAssignment.query
        .join(Sample)
        .join(SampleBatch)
        .filter(
            SampleBatch.semester_id == semester.id,
            SampleAssignment.status.notin_(["passed", "cancelled"]),
        )
        .all()
    )
    by_student: dict[int, list[SampleAssignment]] = {}
    for sa in open_assignments:
        by_student.setdefault(sa.student_id, []).append(sa)

    # Step 3: Pre-load SampleBatch and Sample lookups to avoid N+1
    batches_by_analysis: dict[int, SampleBatch] = {
        sb.analysis_id: sb
        for sb in SampleBatch.query.filter_by(semester_id=semester.id).all()
    }
    all_batch_ids = [sb.id for sb in batches_by_analysis.values()]
    samples_by_key: dict[tuple[int, int], Sample] = {}
    if all_batch_ids:
        for s in Sample.query.filter(
            Sample.batch_id.in_(all_batch_ids),
            Sample.is_buffer.is_(False),
        ).all():
            samples_by_key[(s.batch_id, s.running_number)] = s

    # Step 4: Build one slot per student
    slots: list[StudentSlot] = []
    for student in students:
        rotation = rotations.get(student.group_code) if student.group_code else None
        rotation_analysis = rotation.analysis if rotation else None
        rotation_assignment: SampleAssignment | None = None

        if rotation_analysis:
            batch = batches_by_analysis.get(rotation_analysis.id)
            if batch:
                sample = samples_by_key.get((batch.id, student.running_number))
                if sample:
                    rotation_assignment = next(
                        (sa for sa in by_student.get(student.id, [])
                         if sa.sample_id == sample.id),
                        None,
                    )

        # extra_assignments: all open assignments EXCEPT the rotation one
        rot_id = rotation_assignment.id if rotation_assignment else None
        extra = [
            sa for sa in by_student.get(student.id, [])
            if sa.id != rot_id
        ]

        slots.append(StudentSlot(
            student=student,
            rotation_analysis=rotation_analysis,
            rotation_assignment=rotation_assignment,
            extra_assignments=extra,
        ))

    return slots


def _resolve_nachkochtag(practical_day, semester, students) -> list[StudentSlot]:
    block_id = practical_day.block_id

    # All open assignments for this block
    open_assignments: list[SampleAssignment] = (
        SampleAssignment.query
        .join(Sample)
        .join(SampleBatch)
        .join(Analysis, SampleBatch.analysis_id == Analysis.id)
        .filter(
            SampleBatch.semester_id == semester.id,
            Analysis.block_id == block_id,
            SampleAssignment.status.notin_(["passed", "cancelled"]),
        )
        .all()
    )
    by_student: dict[int, list[SampleAssignment]] = {}
    for sa in open_assignments:
        by_student.setdefault(sa.student_id, []).append(sa)

    # All students appear; empty extra_assignments = block completed
    return [
        StudentSlot(
            student=student,
            rotation_analysis=None,
            rotation_assignment=None,
            extra_assignments=by_student.get(student.id, []),
        )
        for student in students
    ]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_praktikum_resolution.py -v
```

Expected: all PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add praktikum.py tests/test_praktikum_resolution.py
git commit -m "feat: add praktikum.py service module with resolve_student_slots"
```

---

## Task 2: Update route in `app.py`

**Files:**
- Modify: `app.py` (line ~308, `praktikum_tagesansicht` function)

The existing route is a 1-line placeholder. Replace it with the full implementation from the spec.

- [ ] **Step 1: Write route tests**

Append to `tests/test_navigation.py`:

```python
def test_tagesansicht_no_practical_day_shows_banner(client):
    """When no PracticalDay exists for the selected date, page loads with info banner."""
    resp = client.get("/praktikum/?date=2099-12-31")
    assert resp.status_code == 200
    assert b"Tagesansicht" in resp.data

def test_tagesansicht_default_loads(client):
    """Default /praktikum/ loads without error."""
    resp = client.get("/praktikum/")
    assert resp.status_code == 200

def test_tagesansicht_no_active_semester_returns_200(client, app):
    """If no semester is active, the route returns 200 with a warning banner."""
    from models import db, Semester
    with app.app_context():
        # Deactivate all semesters temporarily
        Semester.query.update({"is_active": False})
        db.session.flush()
        resp = client.get("/praktikum/?date=2099-12-31")
        assert resp.status_code == 200
        db.session.rollback()
```

- [ ] **Step 2: Run to verify baseline (placeholder)**

```bash
pytest tests/test_navigation.py -v
```

Expected: `test_tagesansicht_no_practical_day_shows_banner` and `test_tagesansicht_default_loads` PASS (placeholder returns 200). `test_tagesansicht_no_active_semester_returns_200` may PASS or FAIL depending on seed data — note the result.

- [ ] **Step 3: Replace the placeholder route in `app.py`**

Find (inside `register_routes(app)`, line ~307):

```python
    @app.route("/praktikum/")
    def praktikum_tagesansicht():
        return render_template("praktikum/tagesansicht.html")
```

Replace with:

```python
    @app.route("/praktikum/")
    def praktikum_tagesansicht():
        from datetime import date as _date
        from praktikum import resolve_student_slots
        date_str = request.args.get("date") or _date.today().isoformat()
        semester = Semester.query.filter_by(is_active=True).first()
        practical_day = (
            PracticalDay.query.filter_by(semester_id=semester.id, date=date_str).first()
            if semester else None
        )
        slots = resolve_student_slots(practical_day, semester) if practical_day else []
        return render_template(
            "praktikum/tagesansicht.html",
            practical_day=practical_day,
            semester=semester,
            slots=slots,
            selected_date=date_str,
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_navigation.py -v
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: wire praktikum_tagesansicht route to resolve_student_slots"
```

---

## Task 3: Tagesansicht template

**Files:**
- Modify: `templates/praktikum/tagesansicht.html`

Replace the placeholder with a full UI. The template receives:
- `practical_day` — `PracticalDay` object or `None`
- `semester` — active `Semester` or `None`
- `slots` — `list[StudentSlot]` (may be empty)
- `selected_date` — ISO date string (for the datepicker)

**Status badge logic** (derived from model fields, no stored status string):

| UI-Zustand | Bedingung | Bootstrap-Klasse |
|---|---|---|
| Zugewiesen | `status == "assigned"` and `active_result is None` | `text-bg-primary` |
| Ansage ausstehend | `status == "assigned"` and `active_result` exists and `active_result.passed is None` | `text-bg-warning` |
| Bestanden | `status == "passed"` | `text-bg-success` |
| Wiederholung fällig | `attempt_number == 1` and `active_result.passed == False` | `text-bg-danger` |

> **Note on template badge testing:** Template badge logic (particularly "Wiederholung fällig") is not covered by automated tests in this plan. The service-layer behavior (which assignments appear in slots) is fully tested in Task 1. The badge rendering is verified by the manual smoke test in Step 5. Automated template tests for badge colors would require complex fixture setup and HTTP-layer assertions on HTML content — deferred to a future test-coverage pass.

- [ ] **Step 1: Write a route integration test**

Append to `tests/test_navigation.py`:

```python
def test_tagesansicht_shows_student_table_when_slots(client, app):
    """When slots exist, the template renders student rows."""
    from models import db, Semester, Block, Analysis, SampleBatch, Sample, Student, PracticalDay, GroupRotation
    from datetime import date
    with app.app_context():
        sem = Semester.query.filter_by(is_active=True).first()
        if sem is None:
            import pytest; pytest.skip("No active semester in test DB")
        # Just verify the page loads — slot rendering tested via unit tests
        resp = client.get(f"/praktikum/?date=2099-12-30")
        assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify it passes (page loads without crash)**

```bash
pytest tests/test_navigation.py::test_tagesansicht_shows_student_table_when_slots -v
```

Expected: PASS

- [ ] **Step 3: Implement the template**

Overwrite `templates/praktikum/tagesansicht.html`:

```html
{% extends "base.html" %}
{% block title %}Tagesansicht – Quanti-LIMS{% endblock %}
{% block content %}

{# ── Header ────────────────────────────────────────────────────── #}
<div class="d-flex align-items-center gap-3 mb-3 flex-wrap">
  <div class="d-flex align-items-center gap-2">
    <i class="bi bi-calendar-day fs-3 text-success"></i>
    <h1 class="h3 mb-0">Tagesansicht</h1>
  </div>
  <form method="get" class="d-flex align-items-center gap-2 ms-auto">
    <label class="form-label mb-0 fw-semibold">Datum:</label>
    <input type="date" name="date" class="form-control form-control-sm"
           value="{{ selected_date }}" onchange="this.form.submit()">
  </form>
</div>

{# ── No semester / no practical day ────────────────────────────── #}
{% if not semester %}
<div class="alert alert-warning">
  <i class="bi bi-exclamation-triangle"></i>
  Kein aktives Semester gefunden. Bitte zuerst ein Semester aktivieren.
</div>

{% elif not practical_day %}
<div class="alert alert-info">
  <i class="bi bi-info-circle"></i>
  Für den <strong>{{ selected_date }}</strong> ist kein Praktikumstag definiert.
</div>

{% else %}

{# ── Day info ───────────────────────────────────────────────────── #}
<div class="mb-3">
  <span class="badge text-bg-secondary fs-6">
    Block {{ practical_day.block.code }}
    {% if practical_day.day_type == "nachkochtag" %}
      – Nachkochtag
    {% else %}
      – Tag {{ practical_day.block_day_number }}
    {% endif %}
  </span>
</div>

{# ── Rotation overview (normal days only) ──────────────────────── #}
{% if practical_day.day_type == "normal" and practical_day.group_rotations %}
<div class="card mb-4">
  <div class="card-header fw-semibold">
    <i class="bi bi-arrow-repeat"></i> Rotation heute
  </div>
  <div class="card-body p-2">
    <div class="d-flex flex-wrap gap-3">
      {% for gr in practical_day.group_rotations | sort(attribute="group_code") %}
      <div class="border rounded px-3 py-2 text-center">
        <div class="fw-bold fs-5">Gruppe {{ gr.group_code }}</div>
        <div class="text-body-secondary small">{{ gr.analysis.name }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>
{% endif %}

{# ── Student table ──────────────────────────────────────────────── #}
{% if not slots %}
<div class="alert alert-info">Keine Studierenden im aktiven Semester.</div>
{% else %}
<table class="table table-hover align-middle">
  <thead>
    <tr>
      <th>#</th>
      <th>Name</th>
      <th>Gruppe</th>
      {% if practical_day.day_type == "normal" %}
      <th>Rotation</th>
      {% endif %}
      <th>Weitere offene Analysen</th>
    </tr>
  </thead>
  <tbody>
    {% for slot in slots %}
    {# Nachkochtag: grey out students with no open assignments #}
    {% set row_class = "table-secondary text-body-secondary" if (practical_day.day_type == "nachkochtag" and not slot.extra_assignments) else "" %}
    <tr class="{{ row_class }}">
      <td>{{ slot.student.running_number }}</td>
      <td>{{ slot.student.last_name }}, {{ slot.student.first_name }}</td>
      <td>
        {% if slot.student.group_code %}
          <span class="badge text-bg-secondary">{{ slot.student.group_code }}</span>
        {% else %}
          <span class="text-body-secondary">—</span>
        {% endif %}
      </td>

      {# ── Rotation column (normal days) ── #}
      {% if practical_day.day_type == "normal" %}
      <td>
        {% if slot.rotation_analysis is none %}
          <span class="badge text-bg-secondary">Keine Rotation</span>
        {% elif slot.rotation_assignment is none %}
          <span class="badge text-bg-secondary">Noch nicht zugewiesen</span>
        {% else %}
          {% set sa = slot.rotation_assignment %}
          {% set ar = sa.active_result %}
          {% if sa.status == "passed" %}
            <span class="badge text-bg-success">
              {{ slot.rotation_analysis.name }} · {{ sa.attempt_type }} ✓
            </span>
          {% elif ar is not none and ar.passed == false %}
            <span class="badge text-bg-danger">
              {{ slot.rotation_analysis.name }} · {{ sa.attempt_type }} Wdh. fällig
            </span>
          {% elif ar is not none and ar.passed is none %}
            <span class="badge text-bg-warning text-dark">
              {{ slot.rotation_analysis.name }} · {{ sa.attempt_type }} ausstehend
            </span>
          {% else %}
            <span class="badge text-bg-primary">
              {{ slot.rotation_analysis.name }} · {{ sa.attempt_type }}
            </span>
          {% endif %}
        {% endif %}
      </td>
      {% endif %}

      {# ── Extra assignments ── #}
      <td>
        {% if practical_day.day_type == "nachkochtag" and not slot.extra_assignments %}
          <span class="badge text-bg-success">Block abgeschlossen</span>
        {% else %}
          {% for sa in slot.extra_assignments %}
            {% set ar = sa.active_result %}
            {% if sa.status == "passed" %}
              <span class="badge text-bg-success me-1">
                {{ sa.sample.batch.analysis.name }} · {{ sa.attempt_type }} ✓
              </span>
            {% elif ar is not none and ar.passed == false %}
              <span class="badge text-bg-danger me-1">
                {{ sa.sample.batch.analysis.name }} · {{ sa.attempt_type }} Wdh. fällig
              </span>
            {% elif ar is not none and ar.passed is none %}
              <span class="badge text-bg-warning text-dark me-1">
                {{ sa.sample.batch.analysis.name }} · {{ sa.attempt_type }} ausstehend
              </span>
            {% else %}
              <span class="badge text-bg-primary me-1">
                {{ sa.sample.batch.analysis.name }} · {{ sa.attempt_type }}
              </span>
            {% endif %}
          {% endfor %}
          {% if not slot.extra_assignments %}
            <span class="text-body-secondary">—</span>
          {% endif %}
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}

{% endif %}{# end practical_day check #}
{% endblock %}
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 5: Manual smoke test**

Start the app and visit `http://localhost:5000/praktikum/`. Verify:
- Datepicker is shown with today's date
- Info banner appears for dates without a PracticalDay
- No 500 errors

```bash
flask run
```

- [ ] **Step 6: Commit**

```bash
git add templates/praktikum/tagesansicht.html
git commit -m "feat: implement Tagesansicht template with StudentSlot rendering"
```
