# Rotation Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/vorbereitung/rotation` page where TAs can configure group-to-analysis rotations for all practical days of a semester before it starts.

**Architecture:** Two new routes in `app.py` (`GET` + `POST`), one new template `templates/admin/rotation_overview.html`, and a single nav entry in `templates/base.html`. The POST route upserts `GroupRotation` rows; `is_override` is determined by comparing the submitted value against `suggest_rotation()` output.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5.3, vanilla JS (inline script block), pytest with in-memory SQLite.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app.py` | Modify | Add `vorbereitung_rotation` (GET) and `vorbereitung_rotation_save` (POST) route functions |
| `templates/admin/rotation_overview.html` | Create | Rotation grid page with per-block cards, dropdowns, auto-fill button, Speichern button |
| `templates/base.html` | Modify | Add "Rotationszuweisung" nav link in Semesterplanung dropdown |
| `tests/test_rotation_overview_routes.py` | Create | 13 route-level tests covering GET and POST behaviour |

---

## Task 1: GET route + template skeleton

**Files:**
- Modify: `app.py` (after `vorbereitung_stammdaten` at line ~472)
- Create: `templates/admin/rotation_overview.html`
- Create: `tests/test_rotation_overview_routes.py`

- [ ] **Step 1: Write failing tests for the GET route**

Create `tests/test_rotation_overview_routes.py`:

```python
"""Route-level tests for /vorbereitung/rotation."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, PracticalDay,
    GroupRotation, Substance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def rot_fx(db):
    """Minimal dataset: one active semester, one block, two analyses, two normal days."""
    sem = Semester(code="WS_ROT", name="Rotation Test", is_active=True, active_group_count=2)
    db.session.add(sem)
    db.session.flush()

    sem2 = Semester(code="WS_ROT2", name="Rotation Test 2", is_active=False, active_group_count=2)
    db.session.add(sem2)
    db.session.flush()

    block = Block(code="RB", name="Rotation Block", ordinal=1)
    db.session.add(block)
    db.session.flush()

    sub = Substance(name="RotSubstanz", formula="Z", molar_mass_gmol=60.0)
    db.session.add(sub)
    db.session.flush()

    a1 = Analysis(name="Rot Analyse 1", block_id=block.id, code="RB.1",
                  ordinal=1, substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="Rot Analyse 2", block_id=block.id, code="RB.2",
                  ordinal=2, substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()

    day1 = PracticalDay(semester_id=sem.id, block_id=block.id,
                        date="2099-10-15", day_type="normal", block_day_number=1)
    day2 = PracticalDay(semester_id=sem.id, block_id=block.id,
                        date="2099-10-22", day_type="normal", block_day_number=2)
    nk = PracticalDay(semester_id=sem.id, block_id=block.id,
                      date="2099-10-29", day_type="nachkochtag", block_day_number=None)
    db.session.add_all([day1, day2, nk])
    db.session.flush()

    yield {
        "sem": sem, "sem2": sem2, "block": block,
        "a1": a1, "a2": a2, "day1": day1, "day2": day2, "nk": nk,
    }

    db.session.rollback()
    for model, filters in [
        (GroupRotation, {"practical_day_id": day1.id}),
        (GroupRotation, {"practical_day_id": day2.id}),
        (GroupRotation, {"practical_day_id": nk.id}),
        (PracticalDay, {"semester_id": sem.id}),
        (Analysis, {"block_id": block.id}),
        (Block, {"code": "RB"}),
        (Semester, {"code": "WS_ROT"}),
        (Semester, {"code": "WS_ROT2"}),
        (Substance, {"name": "RotSubstanz"}),
    ]:
        db.session.query(model).filter_by(**filters).delete()
    db.session.commit()


@pytest.fixture()
def rot_empty_fx(db):
    """Active semester with no practical days."""
    sem = Semester(code="WS_EMPTY", name="Empty Rotation", is_active=True, active_group_count=2)
    db.session.add(sem)
    db.session.flush()

    yield {"sem": sem}

    db.session.rollback()
    db.session.query(Semester).filter_by(code="WS_EMPTY").delete()
    db.session.commit()


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------

def test_get_rotation_overview_returns_200(client, rot_fx):
    """GET /vorbereitung/rotation returns 200 and shows block heading."""
    resp = client.get("/vorbereitung/rotation")
    assert resp.status_code == 200
    assert b"RB" in resp.data  # block code present


def test_get_rotation_overview_empty_state(client, rot_empty_fx):
    """GET with no practical days shows empty-state message."""
    resp = client.get("/vorbereitung/rotation")
    assert resp.status_code == 200
    assert "Praktikumskalender".encode() in resp.data


def test_get_rotation_overview_semester_param(client, rot_fx):
    """GET with ?semester_id= loads the specified semester."""
    sem2_id = rot_fx["sem2"].id
    resp = client.get(f"/vorbereitung/rotation?semester_id={sem2_id}")
    assert resp.status_code == 200
    # sem2 has no days, so empty-state message should appear
    assert "Praktikumskalender".encode() in resp.data
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_rotation_overview_routes.py::test_get_rotation_overview_returns_200 \
       tests/test_rotation_overview_routes.py::test_get_rotation_overview_empty_state \
       tests/test_rotation_overview_routes.py::test_get_rotation_overview_semester_param \
       -v
```
Expected: FAIL — route does not exist yet.

- [ ] **Step 3: Add GET route to `app.py`**

Insert after `vorbereitung_stammdaten` (around line 473):

```python
@app.route("/vorbereitung/rotation")
def vorbereitung_rotation():
    from collections import OrderedDict
    from models import Semester, Block, PracticalDay, Analysis, GroupRotation

    # Determine target semester
    semester_id = request.args.get("semester_id", type=int)
    if semester_id:
        semester = db.get_or_404(Semester, semester_id)
    else:
        semester = Semester.query.filter_by(is_active=True).first()
        if semester is None:
            flash("Kein aktives Semester gefunden.", "warning")
            return redirect(url_for("home"))

    # Load normal practical days grouped by block (blocks ordered by ordinal)
    days = (
        PracticalDay.query
        .filter_by(semester_id=semester.id, day_type="normal")
        .order_by(PracticalDay.date)
        .all()
    )
    # Group by block, preserving Block.ordinal order
    block_map = OrderedDict()
    for day in days:
        block = day.block
        if block.id not in block_map:
            block_map[block.id] = {"block": block, "days": []}
        block_map[block.id]["days"].append(day)
    # Sort blocks by ordinal
    blocks = sorted(block_map.values(), key=lambda b: b["block"].ordinal)

    # Build rotations dict: {day_id: {group_code: GroupRotation|None}}
    rotations = {}
    for entry in blocks:
        for day in entry["days"]:
            gr_map = {gr.group_code: gr for gr in day.group_rotations}
            rotations[day.id] = gr_map

    analyses = Analysis.query.order_by(Analysis.ordinal).all()
    semesters = Semester.query.order_by(Semester.id.desc()).all()

    return render_template(
        "admin/rotation_overview.html",
        blocks=blocks,
        rotations=rotations,
        analyses=analyses,
        semesters=semesters,
        active_semester=semester,
    )
```

- [ ] **Step 4: Create minimal template `templates/admin/rotation_overview.html`**

```html
{% extends "base.html" %}
{% block title %}Rotationszuweisung{% endblock %}

{% block content %}
<div class="container-fluid py-3">

  {# Page header #}
  <div class="d-flex align-items-center gap-3 mb-3">
    <h1 class="h4 mb-0">Rotationszuweisung</h1>
    {% if semesters|length > 1 %}
    <form method="get" action="{{ url_for('vorbereitung_rotation') }}" class="d-flex align-items-center gap-2">
      <select name="semester_id" class="form-select form-select-sm" style="width:auto" onchange="this.form.submit()">
        {% for sem in semesters %}
        <option value="{{ sem.id }}" {% if sem.id == active_semester.id %}selected{% endif %}>
          {{ sem.name }}
        </option>
        {% endfor %}
      </select>
    </form>
    {% else %}
    <span class="text-muted small">{{ active_semester.name }}</span>
    {% endif %}
  </div>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
      {{ message }}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>
    {% endfor %}
  {% endwith %}

  {% if not blocks %}
  <div class="alert alert-info">
    Noch keine Praktikumstage angelegt. Bitte zuerst den
    <a href="{{ url_for('admin_practical_days') }}">Praktikumskalender</a> konfigurieren.
  </div>
  {% else %}

  {# BLOCK_DATA for JS auto-fill #}
  <script>
  const BLOCK_DATA = {
    {% for entry in blocks %}
    "{{ entry.block.id }}": {
      "active_group_count": {{ active_semester.active_group_count }},
      "days": [
        {% for day in entry.days %}
        {"day_id": {{ day.id }}, "block_day_number": {{ day.block_day_number }}}{% if not loop.last %},{% endif %}
        {% endfor %}
      ],
      "analyses": [{{ entry.block.analyses | map(attribute='id') | join(', ') }}]
    }{% if not loop.last %},{% endif %}
    {% endfor %}
  };
  const GROUP_CODES = ["A","B","C","D"];
  </script>

  <form method="post" action="{{ url_for('vorbereitung_rotation_save') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="semester_id" value="{{ active_semester.id }}">

    {% for entry in blocks %}
    {% set block = entry.block %}
    {% set block_days = entry.days %}
    <div class="card mb-4">
      <div class="card-header d-flex justify-content-between align-items-center">
        <strong>{{ block.name }}</strong>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="autoFill('{{ block.id }}')">
          Auto-fill {{ block.name }}
        </button>
      </div>
      <div class="card-body p-0">
        <table class="table table-bordered table-sm mb-0">
          <thead class="table-light">
            <tr>
              <th>Tag</th>
              {% for g in ["A","B","C","D"] %}
              {% if loop.index <= active_semester.active_group_count %}
              <th>Gruppe {{ g }}</th>
              {% endif %}
              {% endfor %}
            </tr>
          </thead>
          <tbody>
            {% for day in block_days %}
            <tr>
              <td class="text-nowrap">
                <div>Tag {{ day.block_day_number }}</div>
                <div class="text-muted small">{{ day.date[8:10] }}.{{ day.date[5:7] }}.</div>
              </td>
              {% for g in ["A","B","C","D"] %}
              {% if loop.index <= active_semester.active_group_count %}
              {% set gr = rotations[day.id].get(g) %}
              <td>
                <div class="position-relative">
                  {% if gr and gr.is_override %}
                  <span class="position-absolute top-0 end-0 mt-1 me-1"
                        style="width:8px;height:8px;border-radius:50%;background:#fd7e14;display:inline-block;"
                        title="Manuell überschrieben"></span>
                  {% endif %}
                  <select name="rotation[{{ day.id }}][{{ g }}]"
                          class="form-select form-select-sm"
                          id="sel-{{ day.id }}-{{ g }}">
                    <option value="">—</option>
                    {% for a in analyses %}
                    <option value="{{ a.id }}"
                      {% if gr and gr.analysis_id == a.id %}selected{% endif %}>
                      {{ a.code }} — {{ a.name }}
                    </option>
                    {% endfor %}
                  </select>
                </div>
              </td>
              {% endif %}
              {% endfor %}
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% endfor %}

    <div class="d-flex justify-content-end mb-4">
      <button type="submit" class="btn btn-primary">Speichern</button>
    </div>
  </form>

  <script>
  function autoFill(blockId) {
    const data = BLOCK_DATA[blockId];
    if (!data) return;
    const groups = GROUP_CODES.slice(0, data.active_group_count);
    data.days.forEach(function(day) {
      groups.forEach(function(g, i) {
        const sel = document.getElementById("sel-" + day.day_id + "-" + g);
        if (!sel || data.analyses.length === 0) return;
        const idx = (i + day.block_day_number - 1) % data.analyses.length;
        sel.value = data.analyses[idx];
      });
    });
  }
  </script>

  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Run GET tests — expect PASS**

```bash
pytest tests/test_rotation_overview_routes.py::test_get_rotation_overview_returns_200 \
       tests/test_rotation_overview_routes.py::test_get_rotation_overview_empty_state \
       tests/test_rotation_overview_routes.py::test_get_rotation_overview_semester_param \
       -v
```
Expected: all 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin/rotation_overview.html tests/test_rotation_overview_routes.py
git commit -m "feat: add GET /vorbereitung/rotation overview page"
```

---

## Task 2: POST route

**Files:**
- Modify: `app.py` (add `vorbereitung_rotation_save` after the GET route)
- Modify: `tests/test_rotation_overview_routes.py` (add POST tests)

- [ ] **Step 1: Write failing POST tests**

Append to `tests/test_rotation_overview_routes.py`:

```python
# ---------------------------------------------------------------------------
# POST tests
# ---------------------------------------------------------------------------

def test_post_rotation_save_creates_group_rotations(client, rot_fx):
    """POST valid data creates GroupRotation rows and redirects."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a1.id,
    }, follow_redirects=False)
    assert resp.status_code == 302
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr is not None
    assert gr.analysis_id == a1.id


def test_post_rotation_save_upserts_existing(client, rot_fx, db):
    """POST over an existing GroupRotation updates it, no duplicate rows."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    a2 = rot_fx["a2"]
    sem = rot_fx["sem"]
    # Pre-create
    existing = GroupRotation(practical_day_id=d1.id, group_code="A",
                             analysis_id=a1.id, is_override=False)
    db.session.add(existing)
    db.session.commit()
    # Overwrite with a2
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a2.id,
    })
    rows = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").all()
    assert len(rows) == 1
    assert rows[0].analysis_id == a2.id


def test_post_rotation_save_sets_override_flag(client, rot_fx):
    """Submitted value differs from suggest_rotation() → is_override = True."""
    d1 = rot_fx["day1"]
    a2 = rot_fx["a2"]  # day1 block_day_number=1, group A → suggest = a1 (ordinal 1); submit a2
    sem = rot_fx["sem"]
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a2.id,
    })
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr.is_override is True


def test_post_rotation_save_clears_override_flag(client, rot_fx):
    """Submitted value matches suggest_rotation() → is_override = False."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]  # day1 block_day_number=1, group A → suggest = a1; submit a1
    sem = rot_fx["sem"]
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a1.id,
    })
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr.is_override is False


def test_post_rotation_save_blank_deletes_rotation(client, rot_fx, db):
    """Blank analysis_id for a cell with an existing row → row deleted."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    existing = GroupRotation(practical_day_id=d1.id, group_code="A",
                             analysis_id=a1.id, is_override=False)
    db.session.add(existing)
    db.session.commit()
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": "",
    })
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr is None


def test_post_rotation_save_blank_noop(client, rot_fx):
    """Blank analysis_id for a cell with no existing row → no error, no row created."""
    d1 = rot_fx["day1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": "",
    })
    assert resp.status_code == 302
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr is None


def test_post_rotation_save_no_analyses_on_block(client, rot_fx, db):
    """Block with no analyses: suggest_rotation() returns {}, all submitted values set is_override=True."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    a2 = rot_fx["a2"]
    sem = rot_fx["sem"]
    # Temporarily detach analyses from block by pointing them to a nonexistent block_id
    # is not feasible; instead just verify by submitting any value when block has real analyses
    # but suggest_rotation returns {} when block_day_number is None (use nk day instead)
    # Actually: block.analyses is empty only if no analyses exist; simplest test is to
    # submit to a Nachkochtag day which is excluded → use a fresh block with no analyses.
    # Create a block with no analyses so suggest_rotation() returns {}
    block2 = Block(code="EMPTY_BLK", name="Empty Block", ordinal=99)
    db.session.add(block2)
    db.session.flush()
    day_empty = PracticalDay(semester_id=sem.id, block_id=block2.id,
                             date="2099-11-10", day_type="normal", block_day_number=1)
    db.session.add(day_empty)
    db.session.commit()

    # Block has no analyses → suggest_rotation() returns {} → is_override=True for any submission
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{day_empty.id}][A]": a1.id,
    })
    gr = GroupRotation.query.filter_by(practical_day_id=day_empty.id, group_code="A").first()
    assert gr is not None
    assert gr.is_override is True

    # Cleanup
    db.session.rollback()
    GroupRotation.query.filter_by(practical_day_id=day_empty.id).delete()
    PracticalDay.query.filter_by(id=day_empty.id).delete()
    Block.query.filter_by(code="EMPTY_BLK").delete()
    db.session.commit()


def test_post_rotation_save_ignores_nachkochtag(client, rot_fx):
    """POST with a Nachkochtag day_id → 400."""
    nk = rot_fx["nk"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{nk.id}][A]": a1.id,
    })
    assert resp.status_code == 400


def test_post_rotation_save_rejects_invalid_day_id(client, rot_fx):
    """POST with a day_id not in the semester → 400."""
    sem = rot_fx["sem"]
    a1 = rot_fx["a1"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        "rotation[99999][A]": a1.id,
    })
    assert resp.status_code == 400


def test_post_rotation_save_skips_invalid_analysis_id(client, rot_fx):
    """Unknown analysis_id → cell skipped, other cells still saved."""
    d1 = rot_fx["day1"]
    d2 = rot_fx["day2"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": 99999,   # invalid
        f"rotation[{d2.id}][A]": a1.id,   # valid
    }, follow_redirects=False)
    assert resp.status_code == 302
    # Invalid cell skipped
    assert GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first() is None
    # Valid cell saved
    assert GroupRotation.query.filter_by(practical_day_id=d2.id, group_code="A").first() is not None
```

- [ ] **Step 2: Run POST tests to confirm they fail**

```bash
pytest tests/test_rotation_overview_routes.py -k "post" -v
```
Expected: FAIL — POST route does not exist yet.

- [ ] **Step 3: Add POST route to `app.py`**

Insert after the GET route:

```python
@app.route("/vorbereitung/rotation/save", methods=["POST"])
def vorbereitung_rotation_save():
    from praktikum import suggest_rotation, GROUP_CODES
    from models import Semester, PracticalDay, Analysis, GroupRotation

    # 1. Validate semester
    try:
        semester_id = int(request.form["semester_id"])
    except (KeyError, ValueError):
        abort(400)
    semester = db.get_or_404(Semester, semester_id)

    # 2. Collect valid normal day IDs for this semester
    valid_days = {
        d.id: d
        for d in PracticalDay.query.filter_by(
            semester_id=semester.id, day_type="normal"
        ).all()
    }

    # 3. Collect valid analysis IDs
    valid_analyses = {a.id for a in Analysis.query.all()}
    active_groups = GROUP_CODES[:semester.active_group_count]

    skipped = []
    # 4. Parse rotation[day_id][group] fields
    for key, value in request.form.items():
        if not key.startswith("rotation["):
            continue
        # Parse key: rotation[<day_id>][<group>]
        try:
            inner = key[len("rotation["):]  # e.g. "12][A]"
            day_id_str, rest = inner.split("][", 1)
            group = rest.rstrip("]")
            day_id = int(day_id_str)
        except (ValueError, IndexError):
            abort(400)

        if day_id not in valid_days:
            abort(400)
        if group not in active_groups:
            continue

        day = valid_days[day_id]

        if not value:
            # Blank → delete if exists
            GroupRotation.query.filter_by(
                practical_day_id=day_id, group_code=group
            ).delete()
            continue

        try:
            analysis_id = int(value)
        except ValueError:
            abort(400)

        if analysis_id not in valid_analyses:
            skipped.append(value)
            continue

        # Determine is_override
        suggested_map = suggest_rotation(day.block, day.block_day_number,
                                         semester.active_group_count)
        suggested = suggested_map.get(group)
        is_override = (suggested is None) or (analysis_id != suggested.id)

        # Upsert
        gr = GroupRotation.query.filter_by(
            practical_day_id=day_id, group_code=group
        ).first()
        if gr is None:
            gr = GroupRotation(practical_day_id=day_id, group_code=group,
                               analysis_id=analysis_id, is_override=is_override)
            db.session.add(gr)
        else:
            gr.analysis_id = analysis_id
            gr.is_override = is_override

    db.session.commit()

    if skipped:
        flash(f"Einige ungültige Analysen wurden übersprungen: {', '.join(skipped)}", "warning")
    flash("Rotationen gespeichert.", "success")
    return redirect(url_for("vorbereitung_rotation", semester_id=semester_id))
```

- [ ] **Step 4: Run all rotation tests — expect PASS**

```bash
pytest tests/test_rotation_overview_routes.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_rotation_overview_routes.py
git commit -m "feat: add POST /vorbereitung/rotation/save route"
```

---

## Task 3: Nav entry

**Files:**
- Modify: `templates/base.html` (line ~55, after Kolloquien entry in Semesterplanung)

- [ ] **Step 1: Add nav link to `templates/base.html`**

After line 55 (the Kolloquien `<li>` in the Semesterplanung section):

```html
              <li><a class="dropdown-item" href="{{ url_for('vorbereitung_rotation') }}">
                <i class="bi bi-arrow-repeat" aria-hidden="true"></i> Rotationszuweisung</a></li>
```

- [ ] **Step 2: Verify nav renders correctly**

```bash
pytest tests/test_rotation_overview_routes.py -v
```
Expected: all 13 PASS (no regressions from template change).

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add Rotationszuweisung nav entry in Semesterplanung"
```

---

## Task 4: Full test suite check + final commit

- [ ] **Step 1: Run full test suite**

```bash
pytest --tb=short -q
```
Expected: all existing tests PASS plus the 13 new ones.

- [ ] **Step 2: Manual smoke test**

1. Start Flask: `flask run`
2. Open `http://localhost:5000/vorbereitung/rotation`
3. Verify block cards appear with dropdowns pre-filled from existing rotations
4. Click "Auto-fill" on a block — verify dropdowns populate
5. Change one cell manually, save — verify orange dot appears on that cell
6. Check nav dropdown under Vorbereitung → Semesterplanung → Rotationszuweisung link is present

- [ ] **Step 3: Push and open PR**

```bash
git push origin main
```

---

## Reference

- Spec: `docs/superpowers/specs/2026-03-22-rotation-overview-design.md`
- Existing test patterns: `tests/test_tagesansicht_routes.py` (fixture teardown pattern, `yield` + manual delete)
- `suggest_rotation()`: `praktikum.py:15` — returns `{group_code: Analysis}` or `{}`; formula `analyses[(i + block_day_number - 1) % len(analyses)]`
- `GROUP_CODES`: `praktikum.py` — `["A", "B", "C", "D"]`
- `WTF_CSRF_ENABLED = False` in `TEST_CONFIG` (conftest.py) — no CSRF token needed in tests
