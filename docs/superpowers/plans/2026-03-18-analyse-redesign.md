# Analyse-Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the A-Analyse/Erstanalyse terminology throughout the app, fix two calculation bugs (assignment count, tolerance formula), and add result revocation + live evaluation feedback.

**Architecture:** All changes land in one PR. Shared `attempt_type_for()` helper eliminates duplicated attempt-type logic. Schema changes go through the existing `migrate_schema()` in `models.py`. Live evaluation is plain JavaScript in `submit.html`, mirrored server-side in a pure Python helper function.

**Tech Stack:** Flask 3, Flask-SQLAlchemy, SQLite, Flask-WTF (CSRF), Bootstrap 5, plain JS (no framework), pytest + pytest-flask for tests.

---

## File Map

| File | What changes |
|------|-------------|
| `calculation_modes.py` | Add `attempt_type_for()` helper; fix `TitrantStandardizationEvaluator.calculate_sample()`; add `compute_evaluation_label()` |
| `models.py` | `attempt_type` String(2)→String(20); `results` relationship gains `order_by`; `SampleAssignment.active_result` property; `Result` gains `revoked`, `revoked_by`, `revoked_date`, `evaluation_label`; `migrate_schema()` extended |
| `app.py` | `admin_batch_assign_initial()`: einwage guard + `attempt_type_for()`; `assign_buffer()`: `attempt_type_for()`; new `POST /results/<id>/revoke` route; `results_submit()`: compute + store `evaluation_label`, pass JSON context for live eval |
| `init_db.py` | Seed data: `attempt_type="A"` → `attempt_type_for(1)` |
| `templates/assignments/overview.html` | Badge logic: "Erstanalyse" vs "X-Analyse"; "Probe noch nicht bereit" row; Widerruf-Button (mit CSRF) |
| `templates/results/overview.html` | Widerruf-Button (CSRF); `evaluation_label` anzeigen; widerrufene Ergebnisse durchgestrichen |
| `templates/results/submit.html` | Versuch-Zeile anpassen; Live-Bewertungs-JS + Badge-Block |
| `tests/conftest.py` | Pytest fixtures: Flask test app (in-memory SQLite), seeded test data |
| `tests/test_attempt_type.py` | Unit tests für `attempt_type_for()` |
| `tests/test_tolerance.py` | Unit tests für `TitrantStandardizationEvaluator` |
| `tests/test_assignment.py` | Integration tests für Zuweisungs-Bug + Widerruf |
| `tests/test_evaluation_label.py` | Unit tests für `compute_evaluation_label()` |

---

## Task 1: Test Infrastructure

**Files:**
- Modify: `app.py:133` — `create_app()` accepts optional `test_config`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Install test dependencies**

```bash
pip install pytest pytest-flask
```

Expected output: `Successfully installed pytest-flask-...`

- [ ] **Step 2: Modify `create_app()` in `app.py` to accept an optional test config**

The config override must be applied **before** `db.create_all()` and `migrate_schema()` run, otherwise the in-memory DB is never set up.

Change the signature and config block (lines 133-148):

```python
def create_app(test_config: dict | None = None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    CSRFProtect(app)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        migrate_schema()
        from init_db import seed_database
        seed_database()

    register_routes(app)
    register_filters(app)
    register_error_handlers(app)
    return app
```

- [ ] **Step 3: Create `tests/__init__.py`** (empty)

- [ ] **Step 4: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for quanti-lims tests."""

import sys
import os
import pytest

# Add project root to sys.path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from models import db as _db


TEST_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "WTF_CSRF_ENABLED": False,
    "SECRET_KEY": "test-secret",
}


@pytest.fixture(scope="session")
def app():
    """Flask app using in-memory SQLite — shared across all tests.

    test_config is passed to create_app() so the URI is set before
    db.create_all() and migrate_schema() run inside create_app().
    """
    test_app = create_app(test_config=TEST_CONFIG)
    return test_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    """Yields db inside app context. Note: integration tests that commit
    via the route will not be rolled back by this fixture — test ordering
    may matter for integration tests that modify shared session state."""
    with app.app_context():
        yield _db
        _db.session.rollback()
```

- [ ] **Step 5: Run pytest to verify setup**

```bash
cd C:\Users\Miche\Documents\GitHub\quanti-lims
pytest tests/ -v --tb=short
```

Expected: `no tests ran` (no test files yet), exit code 5 (no tests collected — that's OK here).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/ && git commit -m "test: add pytest infrastructure with in-memory Flask fixture"
```

---

## Task 2: `attempt_type_for()` Helper + Terminology Fix

**Files:**
- Modify: `calculation_modes.py`
- Modify: `models.py:672` (String(2)→String(20)), `models.py:680-685` (results order_by), `models.py:313` (migrate_schema)
- Modify: `app.py:1159` (assign_initial), `app.py:1357-1358` (assign_buffer)
- Modify: `init_db.py:332` (seed data)
- Modify: `templates/assignments/overview.html:35` (badge logic)
- Modify: `templates/results/submit.html:15` (Versuch-Zeile)
- Create: `tests/test_attempt_type.py`

### Step 2a: Write failing tests

- [ ] **Step 1: Create `tests/test_attempt_type.py`**

```python
"""Tests for attempt_type_for() mapping."""
from calculation_modes import attempt_type_for


def test_attempt_1_is_erstanalyse():
    assert attempt_type_for(1) == "Erstanalyse"


def test_attempt_2_is_A():
    assert attempt_type_for(2) == "A"


def test_attempt_3_is_B():
    assert attempt_type_for(3) == "B"


def test_attempt_27_is_Z():
    assert attempt_type_for(27) == "Z"


def test_attempt_28_fallback():
    result = attempt_type_for(28)
    assert result == "#28"


def test_attempt_large_fallback():
    assert attempt_type_for(100) == "#100"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_attempt_type.py -v
```

Expected: `ImportError: cannot import name 'attempt_type_for'`

### Step 2b: Implement the helper

- [ ] **Step 3: Add `attempt_type_for()` to `calculation_modes.py`** — append after the existing imports/dataclasses, before `class AssayMassBasedEvaluator`:

```python
def attempt_type_for(attempt_number: int) -> str:
    """Map attempt_number to the correct attempt_type label.

    attempt_number=1 → 'Erstanalyse' (the initial analysis, no repeat letter)
    attempt_number=2 → 'A'  (first repeat)
    attempt_number=3 → 'B'  (second repeat)
    attempt_number=n → chr(ord('A') + n - 2) for n in [2..27]
    attempt_number>27 → '#N' fallback (edge case, not expected in practice)
    """
    if attempt_number == 1:
        return "Erstanalyse"
    n = attempt_number - 2
    if 0 <= n <= 25:
        return chr(ord("A") + n)
    return f"#{attempt_number}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_attempt_type.py -v
```

Expected: 6 passed

### Step 2c: Update `models.py`

- [ ] **Step 5: Widen `attempt_type` column in model definition** (`models.py:672`):

Change:
```python
attempt_type = db.Column(db.String(2), nullable=False, default="A")
```
To:
```python
attempt_type = db.Column(db.String(20), nullable=False, default="Erstanalyse")
```

- [ ] **Step 6: Add `order_by` to the `results` relationship** (`models.py:680-685`):

Change:
```python
    results = db.relationship(
        "Result",
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
```
To:
```python
    results = db.relationship(
        "Result",
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Result.id",
    )
```

- [ ] **Step 7: Extend `migrate_schema()` in `models.py`** — add a new block at the end of the existing function (before the final `conn.close()` or wherever it ends):

```python
        # ── attempt_type: remap to new terminology ──────────────────
        sa_cols = {row[1] for row in conn.exec_driver_sql(
            "PRAGMA table_info(sample_assignment)").fetchall()}
        if "attempt_type" in sa_cols:
            # Idempotent: the WHERE clauses only touch rows that still hold
            # the OLD mapping values (e.g. attempt_number=1 with 'A').
            # The letter re-mappings (CHAR) are also idempotent since
            # CHAR(65 + 2 - 2) = 'A', so re-running produces the same value.
            conn.exec_driver_sql(
                "UPDATE sample_assignment SET attempt_type = 'Erstanalyse' "
                "WHERE attempt_number = 1 AND attempt_type != 'Erstanalyse'"
            )
            conn.exec_driver_sql(
                "UPDATE sample_assignment SET attempt_type = CHAR(65 + attempt_number - 2) "
                "WHERE attempt_number >= 2 AND attempt_number <= 27"
            )
            conn.exec_driver_sql(
                "UPDATE sample_assignment SET attempt_type = '#' || attempt_number "
                "WHERE attempt_number > 27"
            )
```

Note: SQLite ignores VARCHAR length constraints, so widening is implicit; the PRAGMA change is not needed for SQLite. The model definition change ensures correctness for any future DB engine.

### Step 2d: Update assignment routes

- [ ] **Step 8: Update `admin_batch_assign_initial()` in `app.py:1159`** — change the hardcoded `attempt_type="A"` to use the helper:

At the top of `app.py`, add to the imports from `calculation_modes`:
```python
from calculation_modes import (
    MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION, resolve_mode,
    attempt_type_for,
)
```

Then change line 1158-1160:
```python
            sa = SampleAssignment(
                sample=sample, student=st, attempt_number=1, attempt_type="A",
```
To:
```python
            sa = SampleAssignment(
                sample=sample, student=st, attempt_number=1, attempt_type=attempt_type_for(1),
```

- [ ] **Step 9: Update `assign_buffer()` in `app.py:1357-1368`** — replace the `types` list with `attempt_type_for()`:

Change:
```python
        types = ["A", "B", "C", "D"]
        attempt_type = types[min(prev_count, len(types) - 1)]
        sa = SampleAssignment(
            sample=buffer_sample, student_id=student_id,
            attempt_number=prev_count + 1, attempt_type=attempt_type,
```
To:
```python
        new_attempt_number = prev_count + 1
        attempt_type = attempt_type_for(new_attempt_number)
        sa = SampleAssignment(
            sample=buffer_sample, student_id=student_id,
            attempt_number=new_attempt_number, attempt_type=attempt_type,
```

Also update the flash message (line 1367) which still says `({attempt_type}-Analyse)`:
```python
        label = "Erstanalyse" if attempt_type == "Erstanalyse" else f"{attempt_type}-Analyse"
        flash(f"Pufferprobe #{buffer_sample.running_number} ({label}) zugewiesen.", "success")
```

### Step 2e: Fix seed data

- [ ] **Step 10: Fix `init_db.py:332`** — in the loop that creates initial `SampleAssignment` objects:

Change:
```python
        sa = SampleAssignment(
            sample=sample, student=st, attempt_number=1, attempt_type="A",
```
To:
```python
        sa = SampleAssignment(
            sample=sample, student=st, attempt_number=1, attempt_type=attempt_type_for(1),
```

Add the import at the top of `init_db.py`:
```python
from calculation_modes import attempt_type_for
```

### Step 2f: Fix templates

- [ ] **Step 11: Fix badge in `assignments/overview.html:35`**

Change:
```html
      <td><span class="badge {% if sa.attempt_type == 'A' %}bg-primary{% else %}bg-warning text-dark{% endif %}">{{ sa.attempt_type }}-Analyse</span></td>
```
To:
```html
      <td>
        {% if sa.attempt_type == 'Erstanalyse' %}
          <span class="badge bg-secondary">Erstanalyse</span>
        {% else %}
          <span class="badge {% if sa.attempt_type == 'A' %}bg-primary{% else %}bg-warning text-dark{% endif %}">{{ sa.attempt_type }}-Analyse</span>
        {% endif %}
      </td>
```

- [ ] **Step 12: Fix Versuch-Zeile in `results/submit.html:15`**

Change:
```html
          <tr><th>Versuch</th><td>{{ assignment.attempt_type }}-Analyse (Versuch {{ assignment.attempt_number }})</td></tr>
```
To:
```html
          <tr><th>Versuch</th><td>
            {% if assignment.attempt_type == 'Erstanalyse' %}
              Erstanalyse (Versuch 1)
            {% else %}
              {{ assignment.attempt_type }}-Analyse (Versuch {{ assignment.attempt_number }})
            {% endif %}
          </td></tr>
```

Also fix `results/overview.html:48` — the `Versuch`-Spalte shows `{{ sa.attempt_type }}` raw:
```html
  <td>{{ sa.attempt_type }}</td>
```
Change to:
```html
  <td>
    {% if sa.attempt_type == 'Erstanalyse' %}
      <span class="badge bg-secondary">Erstanalyse</span>
    {% else %}
      <span class="badge bg-primary">{{ sa.attempt_type }}-Analyse</span>
    {% endif %}
  </td>
```

- [ ] **Step 13: Commit**

```bash
git add calculation_modes.py models.py app.py init_db.py templates/ tests/
git commit -m "feat: add attempt_type_for() helper, rename Erstanalyse, widen attempt_type column"
```

---

## Task 3: Assignment Count Bug Fix (Einwage Check)

**Files:**
- Modify: `app.py:1142-1167` (`admin_batch_assign_initial`)
- Modify: `templates/assignments/overview.html` (add "Probe noch nicht bereit" rows)
- Create: `tests/test_assignment.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_assignment.py`:

```python
"""Tests for assignment logic."""
import pytest
from models import db, SampleBatch, Sample, SampleAssignment, Student, Semester, Analysis


def _get_batch_and_unweighed_sample(db_session):
    """Helper: return a batch where sample #1 has no weighing data.
    Clears m_ges_actual_g (required for both modes) to simulate unweighed."""
    batch = SampleBatch.query.first()
    sample = Sample.query.filter_by(batch_id=batch.id, running_number=1).first()
    # Clear m_ges_actual_g — required by is_weighed for both modes
    sample.m_s_actual_g = None
    sample.m_ges_actual_g = None
    db_session.session.flush()
    return batch, sample


def test_assign_initial_skips_unweighed_samples(client, db):
    """Zuweisen soll Proben ohne Einwagedaten überspringen."""
    batch, sample = _get_batch_and_unweighed_sample(db)
    # Count existing assignments before
    before = SampleAssignment.query.filter_by(sample_id=sample.id).count()

    response = client.post(f"/admin/batches/{batch.id}/assign-initial",
                           follow_redirects=True)
    assert response.status_code == 200

    after = SampleAssignment.query.filter_by(sample_id=sample.id).count()
    # The unweighed sample should NOT have gained a new assignment
    assert after == before
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_assignment.py::test_assign_initial_skips_unweighed_samples -v
```

Expected: FAIL — the current code assigns regardless of weighing status.

- [ ] **Step 3: Fix `admin_batch_assign_initial()` in `app.py`**

After the existing `if not sample: continue` check (line 1148), add the weighing guard using the existing `Sample.is_weighed` property (defined in `models.py:650-655`) which already handles the `titrant_standardization` mode correctly (for that mode, only `m_ges_actual_g` is checked; for `assay_mass_based`, both fields must be present):

```python
            if not sample:
                continue
            # New guard: skip samples not yet weighed.
            # sample.is_weighed already handles mode differences:
            #   titrant_standardization → only m_ges_actual_g required
            #   assay_mass_based → both m_s_actual_g and m_ges_actual_g required
            if not sample.is_weighed:
                continue
```

Also update the flash message to show counts (change line 1166):
```python
        flash(f"{count} Erstanalysen zugewiesen.", "success")
```
To:
```python
        total_students = len(students)
        skipped = total_students - count
        if skipped > 0:
            flash(
                f"{count} von {total_students} Erstanalysen zugewiesen "
                f"({skipped} Probe(n) noch nicht eingewogen).",
                "success" if count > 0 else "warning",
            )
        else:
            flash(f"{count} Erstanalysen zugewiesen.", "success")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_assignment.py::test_assign_initial_skips_unweighed_samples -v
```

Expected: PASS

- [ ] **Step 5: Verify `d.assignments` is not used elsewhere in templates**

```bash
grep -r "d\.assignments" templates/
```

Expected: only `templates/assignments/overview.html`. If other templates reference it, update them too before continuing.

- [ ] **Step 6: Update assignments overview view function** to pass per-student status

Find the `assignments_overview` view function in `app.py`. It currently builds `data[a.code]["assignments"]` as a list of `SampleAssignment` objects. Update it to also pass students without assignments.

Find the relevant section (search for `"assignments":` in `app.py`) and update the dict to include a student-keyed view:

```python
        # Build per-student rows (including students without assignments)
        all_students = Student.query.filter_by(semester_id=sem.id).order_by(Student.running_number).all()
        # Map student_id → assignment(s) for this batch
        assignment_map = {}
        for sa in assignments:
            assignment_map.setdefault(sa.student_id, []).append(sa)

        student_rows = []
        for st in all_students:
            st_assignments = assignment_map.get(st.id, [])
            if st_assignments:
                for sa in st_assignments:
                    student_rows.append({"student": st, "assignment": sa, "sample_ready": True})
            else:
                # Check if sample exists and is weighed
                sample = next(
                    (s for s in batch.samples if s.running_number == st.running_number and not s.is_buffer),
                    None
                )
                sample_ready = sample is not None and sample.is_weighed
                student_rows.append({"student": st, "assignment": None, "sample_ready": sample_ready})

        data[a.code]["student_rows"] = student_rows
```

- [ ] **Step 7: Update `assignments/overview.html`** — replace the `{% for sa in d.assignments %}` loop with the new `student_rows` structure:

Replace the `<tbody>` content:
```html
    {% for sa in d.assignments %}
    <tr>
      <td>{{ sa.student.running_number }}</td>
      <td>{{ sa.student.full_name }}</td>
      ...
    </tr>
    {% endfor %}
```
With:
```html
    {% for row in d.student_rows %}
    {% set sa = row.assignment %}
    <tr>
      <td>{{ row.student.running_number }}</td>
      <td>{{ row.student.full_name }}</td>
      {% if sa %}
        <td>
          {% if sa.attempt_type == 'Erstanalyse' %}
            <span class="badge bg-secondary">Erstanalyse</span>
          {% else %}
            <span class="badge {% if sa.attempt_type == 'A' %}bg-primary{% else %}bg-warning text-dark{% endif %}">{{ sa.attempt_type }}-Analyse</span>
          {% endif %}
        </td>
        <td>Probe #{{ sa.sample.running_number }}</td>
        <td>{{ status_badge(sa.status) }}</td>
        <td>
          {% if sa.latest_result %}
            {{ sa.latest_result.ansage_value|fmt(4) }} {{ sa.latest_result.ansage_unit }}
            {% if sa.latest_result.passed %}<i class="bi bi-check-circle-fill text-success"></i>{% else %}<i class="bi bi-x-circle-fill text-danger"></i>{% endif %}
          {% else %}–{% endif %}
        </td>
        <td>
          {% if sa.status == 'assigned' %}
            <a href="{{ url_for('results_submit', assignment_id=sa.id) }}" class="btn btn-outline-success btn-sm"><i class="bi bi-clipboard-check"></i> Ansage</a>
            <form method="POST" action="{{ url_for('assignment_cancel', id=sa.id) }}" class="d-inline" onsubmit="return confirm('Zuweisung stornieren? Ergebnisse bleiben als Historie erhalten.')">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button type="submit" class="btn btn-outline-danger btn-sm"><i class="bi bi-x-circle"></i></button>
            </form>
            <form method="POST" action="{{ url_for('assignment_delete', id=sa.id) }}" class="d-inline" onsubmit="return confirm('Zuweisung endgültig löschen? Dadurch werden ggf. auch Ergebnisse unwiderruflich entfernt.')">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="force" value="1">
              <button type="submit" class="btn btn-danger btn-sm"><i class="bi bi-trash"></i></button>
            </form>
          {% elif sa.status == 'failed' %}
            <form method="POST" action="{{ url_for('assign_buffer') }}" class="d-inline">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="student_id" value="{{ sa.student_id }}">
              <input type="hidden" name="analysis_id" value="{{ a.id }}">
              <button type="submit" class="btn btn-outline-warning btn-sm" {% if d.buffer_count == 0 %}disabled{% endif %}>
                <i class="bi bi-plus-circle"></i> Wiederholung
              </button>
            </form>
          {% endif %}
        </td>
      {% else %}
        <td><span class="badge bg-light text-muted border">–</span></td>
        <td>–</td>
        <td>
          {% if row.sample_ready %}
            <span class="badge bg-info text-white">Probe bereit, nicht zugewiesen</span>
          {% else %}
            <span class="badge bg-light text-muted border">Probe noch nicht bereit</span>
          {% endif %}
        </td>
        <td>–</td>
        <td>–</td>
      {% endif %}
    </tr>
    {% endfor %}
```

- [ ] **Step 8: Run all tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add app.py templates/assignments/overview.html tests/test_assignment.py
git commit -m "fix: skip unweighed samples during initial assignment, show per-student status in overview"
```

---

## Task 4: Tolerance Formula Bug Fix (Titrant Standardization)

**Files:**
- Modify: `calculation_modes.py:147-148` (`TitrantStandardizationEvaluator.calculate_sample`)
- Create: `tests/test_tolerance.py`

- [ ] **Step 1: Create `tests/test_tolerance.py`**

```python
"""Tests for TitrantStandardizationEvaluator tolerance formula."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import TitrantStandardizationEvaluator


def _make_sample(titer_expected, tol_min, tol_max):
    """Build a mock sample/batch/analysis chain."""
    analysis = MagicMock()
    analysis.tol_min = tol_min
    analysis.tol_max = tol_max
    batch = MagicMock()
    batch.analysis = analysis
    batch.titer = titer_expected
    sample = MagicMock()
    sample.batch = batch
    return sample


def test_tolerance_relative_to_true_value():
    """Grenzen müssen relativ zum Probenfaktor berechnet werden, nicht absolut."""
    sample = _make_sample(titer_expected=0.9400, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert abs(result.a_min - 0.9212) < 0.0001, f"Expected 0.9212, got {result.a_min}"
    assert abs(result.a_max - 0.9588) < 0.0001, f"Expected 0.9588, got {result.a_max}"


def test_tolerance_with_titer_1_unchanged():
    """Für titer_expected=1.0 ergibt die neue Formel identische Werte wie die alte."""
    sample = _make_sample(titer_expected=1.0000, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert abs(result.a_min - 0.9800) < 0.0001
    assert abs(result.a_max - 1.0200) < 0.0001


def test_tolerance_none_when_tol_missing():
    sample = _make_sample(titer_expected=0.9400, tol_min=None, tol_max=None)
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert result.a_min is None
    assert result.a_max is None


def test_evaluate_result_passes_within_tolerance():
    sample = _make_sample(titer_expected=0.9400, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = MagicMock()
    result.ansage_value = 0.9400  # exactly the expected value → should pass
    result.assignment.sample = sample
    eval_result = evaluator.evaluate_result(result)
    assert eval_result.passed is True


def test_evaluate_result_fails_outside_tolerance():
    sample = _make_sample(titer_expected=0.9400, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = MagicMock()
    result.ansage_value = 0.9800  # 1.0000 old bound, outside new bounds [0.9212, 0.9588]
    result.assignment.sample = sample
    eval_result = evaluator.evaluate_result(result)
    assert eval_result.passed is False
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/test_tolerance.py -v
```

Expected: `test_tolerance_relative_to_true_value` FAILS, others may fail too.

- [ ] **Step 3: Fix `TitrantStandardizationEvaluator.calculate_sample()` in `calculation_modes.py:147-148`**

Change:
```python
        titer_min = round(analysis.tol_min / 100.0, 4) if analysis.tol_min is not None else None
        titer_max = round(analysis.tol_max / 100.0, 4) if analysis.tol_max is not None else None
```
To:
```python
        titer_expected = sample.batch.titer
        titer_min = (
            round(titer_expected * analysis.tol_min / 100.0, 4)
            if titer_expected is not None and analysis.tol_min is not None
            else None
        )
        titer_max = (
            round(titer_expected * analysis.tol_max / 100.0, 4)
            if titer_expected is not None and analysis.tol_max is not None
            else None
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tolerance.py -v
```

Expected: 5 passed

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add calculation_modes.py tests/test_tolerance.py
git commit -m "fix: compute titer tolerance bounds relative to sample's true titer_expected"
```

---

## Task 5: Result Revocation

**Files:**
- Modify: `models.py` — `Result` model (new fields), `SampleAssignment` (new property), `migrate_schema()`
- Modify: `app.py` — new `POST /results/<id>/revoke` route
- Modify: `templates/results/overview.html` — Widerruf-Button, widerrufene Ergebnisse
- Add tests to: `tests/test_assignment.py`

### Step 5a: Data model + migration

- [ ] **Step 1: Add fields to `Result` in `models.py`** — after line 710 (`passed = db.Column(db.Boolean)`):

```python
    revoked       = db.Column(db.Boolean, nullable=False, default=False)
    revoked_by    = db.Column(db.String(100), nullable=True)
    revoked_date  = db.Column(db.String(20), nullable=True)
```

- [ ] **Step 2: Add `active_result` property to `SampleAssignment` in `models.py`** — after the existing `latest_result` property (after line 691):

```python
    @property
    def active_result(self):
        """The most recent non-revoked result, or None."""
        for r in sorted(self.results, key=lambda r: r.id, reverse=True):
            if not r.revoked:
                return r
        return None
```

- [ ] **Step 3: Extend `migrate_schema()` in `models.py`** — add at the end of the function:

```python
        # ── Result: revocation fields ───────────────────────────────
        result_cols = {row[1] for row in conn.exec_driver_sql(
            "PRAGMA table_info(result)").fetchall()}
        if "revoked" not in result_cols:
            conn.exec_driver_sql(
                "ALTER TABLE result ADD COLUMN revoked BOOLEAN NOT NULL DEFAULT 0"
            )
        if "revoked_by" not in result_cols:
            conn.exec_driver_sql(
                "ALTER TABLE result ADD COLUMN revoked_by VARCHAR(100)"
            )
        if "revoked_date" not in result_cols:
            conn.exec_driver_sql(
                "ALTER TABLE result ADD COLUMN revoked_date VARCHAR(20)"
            )
```

### Step 5b: Revoke route

- [ ] **Step 4: Add `POST /results/<id>/revoke` route to `app.py`** — add after the `results_submit` route (after line ~1518):

```python
    @app.route("/results/<int:result_id>/revoke", methods=["POST"])
    def result_revoke(result_id):
        """Admin-only: revoke a submitted result and reset assignment to 'assigned'."""
        result = Result.query.get_or_404(result_id)
        if result.revoked:
            flash("Dieses Ergebnis ist bereits widerrufen.", "info")
        else:
            assignment = result.assignment
            result.revoked = True
            result.revoked_by = session.get("username", "Admin")
            result.revoked_date = date.today().isoformat()
            assignment.status = "assigned"
            db.session.commit()
            flash(
                f"Ansage {result.ansage_value} {result.ansage_unit} widerrufen. "
                "Zuweisung wieder offen.",
                "warning",
            )
        analysis_id = result.assignment.sample.batch.analysis_id
        return redirect(url_for("results_overview", analysis_id=analysis_id))
```

### Step 5c: Tests

- [ ] **Step 5: Add revocation tests to `tests/test_assignment.py`**

```python
def test_revoke_result_resets_assignment_to_assigned(client, db):
    """Widerruf eines Ergebnisses setzt Zuweisung zurück auf 'assigned'."""
    from models import SampleAssignment, Result
    # Find an assignment with a result (if none, create one)
    sa = SampleAssignment.query.filter(
        SampleAssignment.status.in_(["passed", "failed", "submitted"])
    ).first()
    if sa is None:
        pytest.skip("No submitted assignment in test data")
    result = sa.active_result or sa.latest_result
    assert result is not None

    response = client.post(f"/results/{result.id}/revoke", follow_redirects=True)
    assert response.status_code == 200

    db.session.refresh(result)
    db.session.refresh(sa)
    assert result.revoked is True
    assert result.revoked_date is not None
    assert sa.status == "assigned"


def test_revoke_idempotent(client, db):
    """Zweifacher Widerruf desselben Ergebnisses ist harmlos."""
    from models import SampleAssignment, Result
    sa = SampleAssignment.query.filter(
        SampleAssignment.status.in_(["passed", "failed", "submitted"])
    ).first()
    if sa is None:
        pytest.skip("No submitted assignment in test data")
    result = sa.active_result or sa.latest_result
    client.post(f"/results/{result.id}/revoke")
    response = client.post(f"/results/{result.id}/revoke", follow_redirects=True)
    assert response.status_code == 200  # no crash


def test_active_result_ignores_revoked(db):
    """active_result gibt None zurück wenn alle Ergebnisse widerrufen sind."""
    from models import SampleAssignment
    sa = SampleAssignment.query.filter(
        SampleAssignment.status.in_(["passed", "failed"])
    ).first()
    if sa is None:
        pytest.skip("No completed assignment in test data")
    for r in sa.results:
        r.revoked = True
    db.session.flush()
    assert sa.active_result is None
```

- [ ] **Step 6: Run revocation tests**

```bash
pytest tests/test_assignment.py -v
```

Expected: all pass (some may be skipped if no submitted assignments in seed data — that's OK)

### Step 5d: Update `results/overview.html`

- [ ] **Step 7: Update `templates/results/overview.html`** — replace the `<td>` for Ansage (lines 59-63) and the Aktion column (lines 65-71) with the new revocation-aware version:

Replace the full `<tbody>` content:
```html
{% for sa in assignments %}
{% set s = sa.sample %}
{% set r = sa.latest_result %}
<tr>
  <td>{{ sa.student.running_number }}</td>
  <td>{{ sa.student.full_name }}</td>
  <td>{{ sa.attempt_type }}</td>
  <td>#{{ s.running_number }}</td>
  {% if selected_analysis and selected_analysis.calculation_mode == 'titrant_standardization' %}
  <td>{{ s.titer_expected|fmt(4) }}</td>
  <td>{{ s.a_min|fmt(4) }}</td>
  <td>{{ s.a_max|fmt(4) }}</td>
{% else %}
  <td>{{ s.g_wahr|fmt(4) }}</td>
  <td>{{ s.a_min|fmt(4) }}</td>
  <td>{{ s.a_max|fmt(4) }}</td>
{% endif %}
  <td>
    {% if r %}
      <strong>{{ r.ansage_value|fmt(4) }}</strong> {{ r.ansage_unit }}
    {% else %}–{% endif %}
  </td>
  <td>{{ status_badge(sa.status) }}</td>
  <td>
    {% if sa.status == 'assigned' %}
      <a href="{{ url_for('results_submit', assignment_id=sa.id) }}" class="btn btn-sm btn-outline-success">
        <i class="bi bi-pencil"></i> Eingeben
      </a>
    {% endif %}
  </td>
</tr>
{% endfor %}
```
With:
```html
{% for sa in assignments %}
{% set s = sa.sample %}
{% set active_r = sa.active_result %}
<tr>
  <td>{{ sa.student.running_number }}</td>
  <td>{{ sa.student.full_name }}</td>
  <td>
    {% if sa.attempt_type == 'Erstanalyse' %}
      <span class="badge bg-secondary">Erstanalyse</span>
    {% else %}
      <span class="badge bg-primary">{{ sa.attempt_type }}-Analyse</span>
    {% endif %}
  </td>
  <td>#{{ s.running_number }}</td>
  {% if selected_analysis and selected_analysis.calculation_mode == 'titrant_standardization' %}
  <td>{{ s.titer_expected|fmt(4) }}</td>
  <td>{{ s.a_min|fmt(4) }}</td>
  <td>{{ s.a_max|fmt(4) }}</td>
  {% else %}
  <td>{{ s.g_wahr|fmt(4) }}</td>
  <td>{{ s.a_min|fmt(4) }}</td>
  <td>{{ s.a_max|fmt(4) }}</td>
  {% endif %}
  <td>
    {% if active_r %}
      <strong>{{ active_r.ansage_value|fmt(4) }}</strong> {{ active_r.ansage_unit }}
      {% if active_r.evaluation_label %}<span class="ms-1 text-muted">{{ active_r.evaluation_label }}</span>{% endif %}
    {% else %}–{% endif %}
    {% for r in sa.results %}
      {% if r.revoked %}
        <div class="text-muted small"><s>{{ r.ansage_value|fmt(4) }} {{ r.ansage_unit }}</s>
          <span class="text-danger">widerrufen {{ r.revoked_date }} ({{ r.revoked_by }})</span>
        </div>
      {% endif %}
    {% endfor %}
  </td>
  <td>{{ status_badge(sa.status) }}</td>
  <td>
    {% if sa.status == 'assigned' %}
      <a href="{{ url_for('results_submit', assignment_id=sa.id) }}" class="btn btn-sm btn-outline-success">
        <i class="bi bi-pencil"></i> Eingeben
      </a>
    {% endif %}
    {% if active_r %}
      <form method="POST" action="{{ url_for('result_revoke', result_id=active_r.id) }}" class="d-inline"
            onsubmit="return confirm('Ansage widerrufen? Zuweisung wird wieder geöffnet.')">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" class="btn btn-sm btn-outline-warning">
          <i class="bi bi-arrow-counterclockwise"></i> Widerruf
        </button>
      </form>
    {% endif %}
  </td>
</tr>
{% endfor %}
```

- [ ] **Step 8: Run all tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add models.py app.py templates/results/overview.html tests/test_assignment.py
git commit -m "feat: add result revocation (revoke route, active_result property, revoked history display)"
```

---

## Task 6: Live Evaluation + `evaluation_label`

**Files:**
- Modify: `calculation_modes.py` — add `compute_evaluation_label()`
- Modify: `models.py` — `Result.evaluation_label` field + `migrate_schema()`
- Modify: `app.py:1490-1518` — `results_submit()`: store `evaluation_label`, pass JSON context
- Modify: `templates/results/submit.html` — add live-eval JS + badge block
- Create: `tests/test_evaluation_label.py`

### Step 6a: `compute_evaluation_label()` helper

- [ ] **Step 1: Write failing tests**

Create `tests/test_evaluation_label.py`:

```python
"""Tests for compute_evaluation_label()."""
from calculation_modes import compute_evaluation_label


def test_label_correct():
    assert compute_evaluation_label(0.9400, 0.9400, 98.0, 102.0, "Erstanalyse") == "✓"


def test_label_f_up_erstanalyse():
    # 0.9700 is above 0.9588 but within 2×T_max → f↑
    assert compute_evaluation_label(0.9700, 0.9400, 98.0, 102.0, "Erstanalyse") == "f↑ → A"


def test_label_f_up_a_analyse():
    assert compute_evaluation_label(0.9700, 0.9400, 98.0, 102.0, "A") == "f↑ → B"


def test_label_f_down():
    # 0.9100 is below 0.9212 (titer_min), δ ≈ -3.19%, T_min=2% → -2T_min < δ → f↓↓? Let's check:
    # T_min = 100 - 98 = 2; -4*T_min=-8 < δ=-3.19 < -2*T_min=-4 → f↓↓ NOT f↓
    # Actually δ = (0.9100 - 0.9400)/0.9400 * 100 = -3.19%
    # -T_min=-2; -2*T_min=-4 → -4 < -3.19 < -2 → f↓↓
    assert compute_evaluation_label(0.9100, 0.9400, 98.0, 102.0, "Erstanalyse") == "f↓↓ → A"


def test_label_f_up_up_up():
    # very far above: δ >> 4*T_max
    assert compute_evaluation_label(1.100, 0.9400, 98.0, 102.0, "Erstanalyse") == "f↑↑↑ → A"


def test_label_none_when_tol_missing():
    assert compute_evaluation_label(0.9400, 0.9400, None, None, "Erstanalyse") is None


def test_label_none_when_true_value_zero():
    assert compute_evaluation_label(1.0, 0.0, 98.0, 102.0, "Erstanalyse") is None
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/test_evaluation_label.py -v
```

Expected: `ImportError: cannot import name 'compute_evaluation_label'`

- [ ] **Step 3: Add `compute_evaluation_label()` to `calculation_modes.py`**

Add after the `attempt_type_for()` function:

```python
def _next_attempt_label(attempt_type: str) -> str:
    """Return the label of the next repeat analysis after a failure."""
    if attempt_type == "Erstanalyse":
        return "A"
    # Current is a letter (A, B, C...); next is the following letter
    if len(attempt_type) == 1 and attempt_type.isalpha():
        return chr(ord(attempt_type) + 1)
    return "?"


def compute_evaluation_label(
    ansage_value: float,
    true_value: float,
    tol_min_pct: float | None,
    tol_max_pct: float | None,
    attempt_type: str,
) -> str | None:
    """Compute the evaluation label for a result (e.g. 'f↑ → A' or '✓').

    Uses the same δ-based formula as the live JS in submit.html.

    Args:
        ansage_value: The submitted result value.
        true_value:   The expected true value (titer_expected or g_wahr).
        tol_min_pct:  Lower tolerance bound as % of true value (e.g. 98.0).
        tol_max_pct:  Upper tolerance bound as % of true value (e.g. 102.0).
        attempt_type: Current attempt type ('Erstanalyse', 'A', 'B', ...).

    Returns:
        Label string like 'f↑ → A', '✓', 'f↓↓ → B', or None if undetermined.
    """
    if tol_min_pct is None or tol_max_pct is None:
        return None
    if not true_value:  # zero or None
        return None

    delta = (ansage_value - true_value) / true_value * 100.0
    T_min = 100.0 - tol_min_pct   # e.g. 100 - 98 = 2.0
    T_max = tol_max_pct - 100.0   # e.g. 102 - 100 = 2.0

    if -T_min <= delta <= T_max:
        return "✓"

    # Determine magnitude symbol
    if delta > 0:
        if delta > 4 * T_max:
            symbol = "f↑↑↑"
        elif delta > 2 * T_max:
            symbol = "f↑↑"
        else:
            symbol = "f↑"
    else:
        if delta < -4 * T_min:
            symbol = "f↓↓↓"
        elif delta < -2 * T_min:
            symbol = "f↓↓"
        else:
            symbol = "f↓"

    next_label = _next_attempt_label(attempt_type)
    return f"{symbol} → {next_label}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_evaluation_label.py -v
```

Expected: all pass

### Step 6b: DB field + migration

- [ ] **Step 5: Add `evaluation_label` field to `Result` in `models.py`** — after the `revoked_date` field:

```python
    evaluation_label = db.Column(db.String(20), nullable=True)
```

- [ ] **Step 6: Extend `migrate_schema()` in `models.py`** — add after the revocation fields block:

```python
        if "evaluation_label" not in result_cols:
            conn.exec_driver_sql(
                "ALTER TABLE result ADD COLUMN evaluation_label VARCHAR(20)"
            )
```

### Step 6c: Store `evaluation_label` server-side

- [ ] **Step 7: Update `results_submit()` in `app.py`** — after `r.evaluate()` (line ~1495), add label computation:

Add import at top of `app.py` (in the calculation_modes import line):
```python
from calculation_modes import (
    MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION, resolve_mode,
    attempt_type_for, compute_evaluation_label,
)
```

Then in `results_submit()`, after `r.evaluate()` and before `db.session.add(r)`:

```python
            # Compute evaluation label (same logic as live JS)
            sample_calc = r.assignment.sample
            if mode == MODE_TITRANT_STANDARDIZATION:
                true_val = sample_calc.titer_expected
            else:
                true_val = sample_calc.g_wahr
            r.evaluation_label = compute_evaluation_label(
                ansage_value=val,
                true_value=true_val,
                tol_min_pct=analysis.tol_min,
                tol_max_pct=analysis.tol_max,
                attempt_type=assignment.attempt_type,
            )
```

### Step 6d: Pass JSON context to submit template

- [ ] **Step 8: Update the `GET` return of `results_submit()` in `app.py:1518`**

Change:
```python
        return render_template("results/submit.html", assignment=assignment, analysis=analysis, titer_label=mode_titer_label(analysis.calculation_mode))
```
To:
```python
        # Prepare live-evaluation context for JS (None if tolerances not configured)
        live_eval_ctx = None
        if analysis.tol_min is not None and analysis.tol_max is not None:
            sample = assignment.sample
            if mode == MODE_TITRANT_STANDARDIZATION:
                true_val = sample.titer_expected
            else:
                true_val = sample.g_wahr
            if true_val is not None:
                live_eval_ctx = {
                    "true_value": true_val,
                    "tol_min_pct": analysis.tol_min,
                    "tol_max_pct": analysis.tol_max,
                    "attempt_type": assignment.attempt_type,
                    "mode": mode,
                }
        return render_template(
            "results/submit.html",
            assignment=assignment,
            analysis=analysis,
            titer_label=mode_titer_label(analysis.calculation_mode),
            live_eval_ctx=live_eval_ctx,
        )
```

### Step 6e: Add live evaluation JS to submit template

- [ ] **Step 9: Update `templates/results/submit.html`** — add live eval block after the input field `<div class="mb-3">` block (after line 34, before the submit button):

```html
          {% if live_eval_ctx %}
          <div id="live-eval-badge" class="mb-3 fs-5 fw-bold text-center" style="min-height:2rem;letter-spacing:.05em;"></div>
          <script>
          (function() {
            var ctx = {{ live_eval_ctx | tojson }};
            var T_min = 100 - ctx.tol_min_pct;
            var T_max = ctx.tol_max_pct - 100;

            function nextLabel(attempt_type) {
              if (attempt_type === 'Erstanalyse') return 'A';
              var code = attempt_type.charCodeAt(0);
              return String.fromCharCode(code + 1);
            }

            function evalLabel(val) {
              if (isNaN(val) || ctx.true_value === 0) return '';
              var delta = (val - ctx.true_value) / ctx.true_value * 100;
              if (delta >= -T_min && delta <= T_max) return '✓';
              var symbol;
              if (delta > 0) {
                if      (delta > 4 * T_max) symbol = 'f↑↑↑';
                else if (delta > 2 * T_max) symbol = 'f↑↑';
                else                        symbol = 'f↑';
              } else {
                if      (delta < -4 * T_min) symbol = 'f↓↓↓';
                else if (delta < -2 * T_min) symbol = 'f↓↓';
                else                         symbol = 'f↓';
              }
              return symbol + ' → ' + nextLabel(ctx.attempt_type);
            }

            function colorClass(label) {
              if (!label)           return 'text-muted';
              if (label === '✓')    return 'text-success';
              if (label.startsWith('f↑↑↑') || label.startsWith('f↓↓↓')) return 'text-danger';
              if (label.startsWith('f↑↑')  || label.startsWith('f↓↓'))  return 'text-danger';
              return 'text-warning';
            }

            var input  = document.querySelector('input[name="ansage_value"]');
            var badge  = document.getElementById('live-eval-badge');

            function update() {
              // Accept both comma and period as decimal separator
              var raw = input.value.replace(',', '.');
              var val = parseFloat(raw);
              var label = (raw === '' || isNaN(val)) ? '' : evalLabel(val);
              badge.textContent = label;
              badge.className = 'mb-3 fs-5 fw-bold text-center ' + colorClass(label);
            }

            input.addEventListener('input', update);
            update();
          })();
          </script>
          {% endif %}
```

- [ ] **Step 10: Run all tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 11: Commit**

```bash
git add calculation_modes.py models.py app.py templates/results/submit.html templates/results/overview.html tests/test_evaluation_label.py
git commit -m "feat: add live result evaluation badge (JS) and server-side evaluation_label persistence"
```

---

## Task 7: Final Smoke Test + Plan Review

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass, 0 failures.

- [ ] **Step 2: Start the dev server and manual smoke test**

```bash
python app.py
```

Open `http://localhost:5000` and verify:
1. Zuweisungsübersicht: Erstanalyse-Badge ist grau, heißt "Erstanalyse" (nicht "A-Analyse")
2. Wiederholungszuweisung: Pufferprobe bekommt "A-Analyse" Badge
3. Zuweisen mit nicht-eingewogenen Proben → Flash zeigt "N von M zugewiesen (X Proben noch nicht eingewogen)"
4. Ergebnis für eine Titereinstellungs-Probe eingeben → Titer-min/max passen sich zum Probenfaktor an
5. Live-Badge beim Tippen eines Ergebniswertes sichtbar
6. Nach Submission: evaluation_label in Ergebnisübersicht sichtbar
7. Widerruf-Button klicken → Zuweisung geht zurück auf "assigned", Ergebnis durchgestrichen mit Datum

- [ ] **Step 3: Final commit if any minor fixes**

```bash
git add -A && git commit -m "fix: smoke test corrections"
```
