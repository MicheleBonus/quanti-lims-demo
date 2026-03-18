# Neue Semesterplanungs-Modelle: Gruppen, Kalender, Dienste

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four new database models (`group_code` on Student, `PracticalDay`, `GroupRotation`, `DutyAssignment`) with Alembic migrations and basic UI in the Semesterplanung section so a TA can define the semester calendar, student groups, and daily duty assignments.

**Architecture:** New SQLAlchemy models added to `models.py`. Each model gets its own Alembic migration (generated via `flask db migrate`). UI additions are minimal forms/views under the existing `admin_students` and `admin_semesters` routes — no new URL structure needed for this plan. GroupRotation is auto-generated from PracticalDay but overridable.

**Tech Stack:** SQLAlchemy 3.x, Flask-Migrate / Alembic, Flask, Jinja2, Bootstrap 5.3

**Spec:** `docs/superpowers/specs/2026-03-18-ux-redesign-two-phase-design.md` (section "Neue Datenmodell-Konzepte")

**Depends on:** Plan 1 (Flask-Migrate must be initialized), Plan 2 (navbar structure)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `models.py` | Add group_code to Student; add PracticalDay, GroupRotation, DutyAssignment models |
| Create | `migrations/versions/<hash>_add_group_code.py` | Auto-generated |
| Create | `migrations/versions/<hash>_add_practical_day_models.py` | Auto-generated |
| Modify | `templates/admin/student_form.html` | Add group_code dropdown |
| Modify | `templates/admin/students.html` | Show group column |
| Create | `templates/admin/practical_days.html` | Calendar list view |
| Create | `templates/admin/practical_day_form.html` | Form to add/edit a practical day |
| Modify | `app.py` | Add routes for PracticalDay CRUD and group rotation generation |
| Modify | `templates/base.html` | Add "Praktikumskalender" link under Semesterplanung |

---

### Task 1: Add group_code to Student model

**Files:**
- Modify: `models.py` (Student class, line ~549)
- Modify: `templates/admin/student_form.html`
- Modify: `templates/admin/students.html`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_student_group.py
def test_student_has_group_code_attribute(db):
    from models import Student, Semester
    with db.session.begin_nested():
        sem = Semester(code="TEST", name="Test")
        db.session.add(sem)
    db.session.flush()
    s = Student(semester_id=sem.id, matrikel="123", last_name="Test",
                first_name="A", running_number=1, group_code="A")
    db.session.add(s)
    db.session.flush()
    assert s.group_code == "A"

def test_student_group_code_nullable(db):
    from models import Student, Semester
    with db.session.begin_nested():
        sem = Semester(code="TEST2", name="Test2")
        db.session.add(sem)
    db.session.flush()
    s = Student(semester_id=sem.id, matrikel="456", last_name="Test",
                first_name="B", running_number=2)
    db.session.add(s)
    db.session.flush()
    assert s.group_code is None

def test_student_group_code_must_be_valid(db):
    from models import Student, Semester
    import pytest
    with db.session.begin_nested():
        sem = Semester(code="TEST3", name="Test3")
        db.session.add(sem)
    db.session.flush()
    s = Student(semester_id=sem.id, matrikel="789", last_name="Test",
                first_name="C", running_number=3, group_code="X")
    db.session.add(s)
    with pytest.raises(Exception):
        db.session.flush()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_student_group.py -v
```
Expected: `AttributeError` or `TypeError` — group_code doesn't exist yet

- [ ] **Step 3: Add group_code to Student model in models.py**

In the `Student` class (after the `email` field):
```python
GROUP_CODES = ("A", "B", "C", "D")
GROUP_CODE_ENUM = db.Enum(*GROUP_CODES, name="group_code_enum",
                          native_enum=False, create_constraint=True,
                          validate_strings=True)

# In Student class:
group_code = db.Column(GROUP_CODE_ENUM, nullable=True)
```

Place the `GROUP_CODES` / `GROUP_CODE_ENUM` constants near the top of models.py alongside `UNIT_DEFINITIONS`.

- [ ] **Step 4: Generate and apply migration**

```bash
flask db migrate -m "add group_code to student"
flask db upgrade
```
Expected: migration file created, `ALTER TABLE student ADD COLUMN group_code` applied

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_student_group.py -v
```
Expected: first two PASS; third test (invalid group_code) depends on DB-level constraint — acceptable if it only raises at flush/commit time

- [ ] **Step 6: Update student_form.html to include group_code**

In `templates/admin/student_form.html`, add a select field for group_code:
```html
<div class="mb-3">
  <label class="form-label">Gruppe</label>
  <select name="group_code" class="form-select">
    <option value="">— keine —</option>
    {% for code in ("A", "B", "C", "D") %}
    <option value="{{ code }}" {% if student and student.group_code == code %}selected{% endif %}>
      Gruppe {{ code }}
    </option>
    {% endfor %}
  </select>
</div>
```

- [ ] **Step 7: Update student POST route in app.py to save group_code**

In the student create/edit route, add:
```python
group_code = request.form.get("group_code") or None
student.group_code = group_code
```

- [ ] **Step 8: Show group_code column in students.html table**

Add `<th>Gruppe</th>` to the header and `<td>{{ student.group_code or "—" }}</td>` to the rows.

- [ ] **Step 9: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add models.py migrations/ templates/admin/student_form.html templates/admin/students.html app.py tests/test_student_group.py
git commit -m "feat: add group_code (A/B/C/D) to Student model with UI"
```

---

### Task 2: Add PracticalDay model

**Files:**
- Modify: `models.py`
- Create: `tests/test_practical_day.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_practical_day.py
import pytest

@pytest.fixture
def seeded(db):
    """Ensure a Semester and Block exist for these tests."""
    from models import Semester, Block
    sem = Semester.query.first()
    block = Block.query.first()
    if sem is None or block is None:
        pytest.skip("Seed data (Semester/Block) not available in test DB")
    return {"sem": sem, "block": block}

def test_practical_day_creation(db, seeded):
    from models import PracticalDay
    pd = PracticalDay(
        semester_id=seeded["sem"].id,
        block_id=seeded["block"].id,
        date="2026-10-06",
        day_type="normal",
        block_day_number=1,
    )
    db.session.add(pd)
    db.session.flush()
    assert pd.id is not None
    assert pd.day_type == "normal"

def test_practical_day_nachkochtag(db, seeded):
    from models import PracticalDay
    pd = PracticalDay(
        semester_id=seeded["sem"].id,
        block_id=seeded["block"].id,
        date="2026-10-11",
        day_type="nachkochtag",
        block_day_number=None,
    )
    db.session.add(pd)
    db.session.flush()
    assert pd.day_type == "nachkochtag"
    assert pd.block_day_number is None
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_practical_day.py -v
```
Expected: FAIL — PracticalDay doesn't exist

- [ ] **Step 3: Add PracticalDay to models.py**

```python
PRACTICAL_DAY_TYPES = ("normal", "nachkochtag")
PRACTICAL_DAY_TYPE_ENUM = db.Enum(*PRACTICAL_DAY_TYPES, name="practical_day_type",
                                   native_enum=False, create_constraint=True,
                                   validate_strings=True)

class PracticalDay(db.Model):
    __tablename__ = "practical_day"
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semester.id"), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    day_type = db.Column(PRACTICAL_DAY_TYPE_ENUM, nullable=False, default="normal")
    block_day_number = db.Column(db.Integer, nullable=True)  # 1–4 for normal days; NULL for Nachkochtag
    notes = db.Column(db.Text)

    semester = db.relationship("Semester", backref="practical_days")
    block = db.relationship("Block", backref="practical_days")
    group_rotations = db.relationship("GroupRotation", back_populates="practical_day",
                                      cascade="all, delete-orphan")
    duty_assignments = db.relationship("DutyAssignment", back_populates="practical_day",
                                       cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("semester_id", "date"),
    )
```

- [ ] **Step 4: Generate and apply migration**

```bash
flask db migrate -m "add practical_day model"
flask db upgrade
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_practical_day.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add models.py migrations/ tests/test_practical_day.py
git commit -m "feat: add PracticalDay model"
```

---

### Task 3: Add GroupRotation and DutyAssignment models

**Files:**
- Modify: `models.py`
- Create: `tests/test_group_rotation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_group_rotation.py
import pytest

@pytest.fixture
def seeded_day(db):
    """Create a PracticalDay with all required FK objects."""
    from models import PracticalDay, Semester, Block, Analysis
    sem = Semester.query.first()
    block = Block.query.first()
    analysis = Analysis.query.first()
    if sem is None or block is None or analysis is None:
        pytest.skip("Seed data (Semester/Block/Analysis) not available")
    pd = PracticalDay(semester_id=sem.id, block_id=block.id,
                      date="2026-10-07", day_type="normal", block_day_number=2)
    db.session.add(pd)
    db.session.flush()
    return {"pd": pd, "analysis": analysis, "sem": sem}

def test_group_rotation_creation(db, seeded_day):
    from models import GroupRotation
    gr = GroupRotation(practical_day_id=seeded_day["pd"].id, group_code="B",
                       analysis_id=seeded_day["analysis"].id, is_override=False)
    db.session.add(gr)
    db.session.flush()
    assert gr.group_code == "B"
    assert gr.is_override is False

def test_duty_assignment_creation(db, seeded_day):
    from models import DutyAssignment, Student
    student = Student.query.first()
    if student is None:
        pytest.skip("Seed data (Student) not available")
    da = DutyAssignment(practical_day_id=seeded_day["pd"].id,
                        student_id=student.id, duty_type="Saaldienst")
    db.session.add(da)
    db.session.flush()
    assert da.duty_type == "Saaldienst"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_group_rotation.py -v
```
Expected: FAIL

- [ ] **Step 3: Add GroupRotation and DutyAssignment to models.py**

```python
DUTY_TYPES = ("Saaldienst", "Entsorgungsdienst")
DUTY_TYPE_ENUM = db.Enum(*DUTY_TYPES, name="duty_type_enum",
                          native_enum=False, create_constraint=True,
                          validate_strings=True)

class GroupRotation(db.Model):
    __tablename__ = "group_rotation"
    id = db.Column(db.Integer, primary_key=True)
    practical_day_id = db.Column(db.Integer, db.ForeignKey("practical_day.id"), nullable=False)
    group_code = db.Column(GROUP_CODE_ENUM, nullable=False)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analysis.id"), nullable=False)
    is_override = db.Column(db.Boolean, nullable=False, default=False)

    practical_day = db.relationship("PracticalDay", back_populates="group_rotations")
    analysis = db.relationship("Analysis")

    __table_args__ = (
        db.UniqueConstraint("practical_day_id", "group_code"),
    )


class DutyAssignment(db.Model):
    __tablename__ = "duty_assignment"
    id = db.Column(db.Integer, primary_key=True)
    practical_day_id = db.Column(db.Integer, db.ForeignKey("practical_day.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    duty_type = db.Column(DUTY_TYPE_ENUM, nullable=False)

    practical_day = db.relationship("PracticalDay", back_populates="duty_assignments")
    student = db.relationship("Student", backref="duty_assignments")
```

- [ ] **Step 4: Generate and apply migration**

```bash
flask db migrate -m "add group_rotation and duty_assignment models"
flask db upgrade
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add models.py migrations/ tests/test_group_rotation.py
git commit -m "feat: add GroupRotation and DutyAssignment models"
```

---

### Task 4: Praktikumskalender UI (list + add form)

**Files:**
- Create: `templates/admin/practical_days.html`
- Create: `templates/admin/practical_day_form.html`
- Modify: `app.py` — add CRUD routes
- Modify: `templates/base.html` — add link under Semesterplanung

- [ ] **Step 1: Write route tests**

```python
# tests/test_practical_day_routes.py
def test_practical_days_list_loads(client):
    resp = client.get("/admin/practical-days")
    assert resp.status_code == 200
    assert b"Praktikumskalender" in resp.data

def test_practical_day_form_loads(client):
    resp = client.get("/admin/practical-days/new")
    assert resp.status_code == 200
    assert b"Datum" in resp.data
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_practical_day_routes.py -v
```
Expected: FAIL (404)

- [ ] **Step 3: Create templates/admin/practical_days.html**

```html
{% extends "base.html" %}
{% block title %}Praktikumskalender{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h1 class="h3">Praktikumskalender</h1>
  <a href="{{ url_for('admin_practical_day_new') }}" class="btn btn-primary">
    <i class="bi bi-plus-lg"></i> Tag hinzufügen
  </a>
</div>

{% if not days %}
<div class="alert alert-info">Noch keine Praktikumstage definiert.</div>
{% else %}
<table class="table table-hover">
  <thead>
    <tr>
      <th>Datum</th>
      <th>Block</th>
      <th>Typ</th>
      <th>Blocktag</th>
      <th>Aktionen</th>
    </tr>
  </thead>
  <tbody>
    {% for day in days %}
    <tr>
      <td>{{ day.date }}</td>
      <td>{{ day.block.code }}</td>
      <td>{% if day.day_type == "nachkochtag" %}<span class="badge text-bg-warning">Nachkochtag</span>{% else %}Normal{% endif %}</td>
      <td>{{ day.block_day_number or "—" }}</td>
      <td>
        <a href="{{ url_for('admin_practical_day_edit', day_id=day.id) }}" class="btn btn-sm btn-outline-secondary">
          <i class="bi bi-pencil"></i>
        </a>
        <form method="post" action="{{ url_for('admin_practical_day_delete', day_id=day.id) }}" class="d-inline">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Tag löschen?')">
            <i class="bi bi-trash"></i>
          </button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Create templates/admin/practical_day_form.html**

```html
{% extends "base.html" %}
{% block title %}Praktikumstag{% endblock %}
{% block content %}
<h1 class="h3 mb-4">{{ "Tag bearbeiten" if day else "Tag hinzufügen" }}</h1>
<form method="post">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

  <div class="mb-3">
    <label class="form-label">Datum</label>
    <input type="date" name="date" class="form-control" required
           value="{{ day.date if day else '' }}">
  </div>

  <div class="mb-3">
    <label class="form-label">Block</label>
    <select name="block_id" class="form-select" required>
      {% for block in blocks %}
      <option value="{{ block.id }}" {% if day and day.block_id == block.id %}selected{% endif %}>
        Block {{ block.code }} — {{ block.name }}
      </option>
      {% endfor %}
    </select>
  </div>

  <div class="mb-3">
    <label class="form-label">Tagestyp</label>
    <select name="day_type" class="form-select" required id="day_type_select">
      <option value="normal" {% if not day or day.day_type == "normal" %}selected{% endif %}>Normal (Blocktag)</option>
      <option value="nachkochtag" {% if day and day.day_type == "nachkochtag" %}selected{% endif %}>Nachkochtag</option>
    </select>
  </div>

  <div class="mb-3" id="block_day_number_field">
    <label class="form-label">Blocktag-Nummer (1–4)</label>
    <input type="number" name="block_day_number" class="form-control"
           min="1" max="4" value="{{ day.block_day_number if day else '' }}">
  </div>

  <div class="mb-3">
    <label class="form-label">Notizen</label>
    <textarea name="notes" class="form-control" rows="2">{{ day.notes or "" }}</textarea>
  </div>

  <button type="submit" class="btn btn-primary">Speichern</button>
  <a href="{{ url_for('admin_practical_days') }}" class="btn btn-outline-secondary">Abbrechen</a>
</form>

<script>
  document.getElementById('day_type_select').addEventListener('change', function() {
    document.getElementById('block_day_number_field').style.display =
      this.value === 'nachkochtag' ? 'none' : '';
  });
  // Init
  if (document.getElementById('day_type_select').value === 'nachkochtag') {
    document.getElementById('block_day_number_field').style.display = 'none';
  }
</script>
{% endblock %}
```

- [ ] **Step 5: Add CRUD routes and helper to app.py**

> **Important:** All code below must be placed **inside the `register_routes(app)` function** in `app.py`, alongside existing route definitions. Do not place at module level.

First, add the helper near the top of `register_routes(app)`, alongside existing helpers:
```python
def _get_active_semester_id():
    """Returns the id of the active semester, or aborts with 400."""
    sem = Semester.query.filter_by(is_active=True).first()
    if sem is None:
        abort(400, "Kein aktives Semester gefunden.")
    return sem.id
```

Then add the four routes inside `register_routes(app)`:
```python
@app.route("/admin/practical-days")
def admin_practical_days():
    days = PracticalDay.query.order_by(PracticalDay.date).all()
    return render_template("admin/practical_days.html", days=days)

@app.route("/admin/practical-days/new", methods=["GET", "POST"])
def admin_practical_day_new():
    blocks = Block.query.order_by(Block.code).all()
    if request.method == "POST":
        day = PracticalDay(
            semester_id=_get_active_semester_id(),
            block_id=int(request.form["block_id"]),
            date=request.form["date"],
            day_type=request.form["day_type"],
            block_day_number=int(request.form["block_day_number"]) if request.form.get("block_day_number") else None,
            notes=request.form.get("notes") or None,
        )
        db.session.add(day)
        db.session.commit()
        flash("Praktikumstag gespeichert.", "success")
        return redirect(url_for("admin_practical_days"))
    return render_template("admin/practical_day_form.html", day=None, blocks=blocks)

@app.route("/admin/practical-days/<int:day_id>/edit", methods=["GET", "POST"])
def admin_practical_day_edit(day_id):
    day = db.get_or_404(PracticalDay, day_id)
    blocks = Block.query.order_by(Block.code).all()
    if request.method == "POST":
        day.block_id = int(request.form["block_id"])
        day.date = request.form["date"]
        day.day_type = request.form["day_type"]
        day.block_day_number = int(request.form["block_day_number"]) if request.form.get("block_day_number") else None
        day.notes = request.form.get("notes") or None
        db.session.commit()
        flash("Praktikumstag aktualisiert.", "success")
        return redirect(url_for("admin_practical_days"))
    return render_template("admin/practical_day_form.html", day=day, blocks=blocks)

@app.route("/admin/practical-days/<int:day_id>/delete", methods=["POST"])
def admin_practical_day_delete(day_id):
    day = db.get_or_404(PracticalDay, day_id)
    db.session.delete(day)
    db.session.commit()
    flash("Praktikumstag gelöscht.", "success")
    return redirect(url_for("admin_practical_days"))
```

Add `PracticalDay, GroupRotation, DutyAssignment` to the existing multi-line models import at the top of `app.py`. The current last import line in the `from models import (...)` block reads:
```python
    canonical_unit_label, get_amount_unit_type, get_unit_options, is_known_unit, normalize_unit,
```
Change it to:
```python
    canonical_unit_label, get_amount_unit_type, get_unit_options, is_known_unit, normalize_unit,
    PracticalDay, GroupRotation, DutyAssignment,
```

- [ ] **Step 6: Add link in base.html under Semesterplanung**

```html
<li><a class="dropdown-item" href="{{ url_for('admin_practical_days') }}">
  <i class="bi bi-calendar2-week"></i> Praktikumskalender</a></li>
```

- [ ] **Step 7: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add templates/admin/practical_days.html templates/admin/practical_day_form.html app.py templates/base.html tests/test_practical_day_routes.py
git commit -m "feat: add Praktikumskalender UI (list, add, edit, delete)"
```

---

### Task 5: Add ProtocolCheck model

> **Note:** This task adds only the model and migration. No route or UI for "Protokoll abhaken" is added here — that belongs to Plan 4 (Praktikum Live View). The model must exist before Plan 4 can build on it.

**Files:**
- Modify: `models.py`
- Create: `tests/test_protocol_check.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_protocol_check.py
def test_protocol_check_creation(db):
    from models import ProtocolCheck, SampleAssignment
    sa = SampleAssignment.query.first()
    if sa is None:
        import pytest; pytest.skip("No SampleAssignment in test DB")
    pc = ProtocolCheck(sample_assignment_id=sa.id,
                       checked_date="2026-10-06", checked_by="TA Demo")
    db.session.add(pc)
    db.session.flush()
    assert pc.id is not None

def test_protocol_check_unique_per_assignment(db):
    from models import ProtocolCheck, SampleAssignment
    import pytest
    sa = SampleAssignment.query.first()
    if sa is None:
        pytest.skip("No SampleAssignment in test DB")
    pc1 = ProtocolCheck(sample_assignment_id=sa.id,
                        checked_date="2026-10-06", checked_by="TA1")
    pc2 = ProtocolCheck(sample_assignment_id=sa.id,
                        checked_date="2026-10-07", checked_by="TA2")
    db.session.add(pc1)
    db.session.flush()
    db.session.add(pc2)
    with pytest.raises(Exception):
        db.session.flush()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_protocol_check.py -v
```
Expected: FAIL

- [ ] **Step 3: Add ProtocolCheck to models.py**

```python
class ProtocolCheck(db.Model):
    __tablename__ = "protocol_check"
    id = db.Column(db.Integer, primary_key=True)
    sample_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("sample_assignment.id"),
        nullable=False,
        unique=True,  # one protocol check per assignment
    )
    checked_date = db.Column(db.String(20), nullable=False)
    checked_by = db.Column(db.String(100), nullable=False)

    assignment = db.relationship("SampleAssignment", backref=db.backref("protocol_check", uselist=False))
```

- [ ] **Step 4: Generate and apply migration**

```bash
flask db migrate -m "add protocol_check model"
flask db upgrade
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add models.py migrations/ tests/test_protocol_check.py
git commit -m "feat: add ProtocolCheck model (unique per SampleAssignment)"
```
