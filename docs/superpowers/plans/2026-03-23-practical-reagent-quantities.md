# Practical Reagent Quantities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add burette-size configuration for titrant reagents and automatic flask-size suggestions for composite reagents, with inline cross-check on the order list and a completeness overview.

**Architecture:** Four sequential tasks: (1) DB field + migration, (2) admin UI for burette size, (3) order list practical totals, (4) prep list flask suggestions + completeness alert. Each task is independently deployable.

**Tech Stack:** Flask, SQLAlchemy, Alembic (SQLite batch_alter), Jinja2, Bootstrap 5, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-practical-reagent-quantities-design.md`

---

## File Map

| File | Change |
|------|--------|
| `models.py` | Add `practical_amount_per_determination` to `MethodReagent` |
| `migrations/versions/e5f6a7b8c9d0_add_practical_amount_to_method_reagent.py` | Create — add nullable Float column |
| `app.py:1158-1195` | Extend `admin_method_reagent_add` to save `practical_amount_per_determination` |
| `app.py:1208` | Add new route `POST /admin/method-reagents/<id>/set-practical` after `admin_method_reagent_delete` |
| `app.py:2295-2334` | Extend `reports_reagents` to query unconfigured titrants |
| `app.py:2355-2415` | Extend `reports_prep_list` to add flask suggestions |
| `templates/admin/method_reagents.html` | New column + inline form + JS show/hide |
| `reagent_expansion.py:188-249` | Extend `build_expansion` to compute `practical_total` for titrants |
| `templates/reports/order_list.html` | Show practical total inline in Menge cell |
| `templates/reports/prep_list.html` | Show flask suggestion alongside total badge |
| `templates/reports/reagents.html` | Add completeness alert |
| `tests/test_reagent_expansion.py` | Add tests for practical_total in `build_expansion` |

---

## Task 1: Add `practical_amount_per_determination` to MethodReagent

**Files:**
- Modify: `models.py` (MethodReagent class, around line 324)
- Create: `migrations/versions/e5f6a7b8c9d0_add_practical_amount_to_method_reagent.py`

**Context:** `MethodReagent` is defined in `models.py` around line 324. The migration pattern uses `batch_alter_table` for SQLite compatibility. Current HEAD revision is `9c64dbf20d9e`.

- [ ] **Step 1: Add the field to the model**

In `models.py`, inside `class MethodReagent`, add after `is_titrant`:

```python
practical_amount_per_determination = db.Column(db.Float, nullable=True)
```

The full updated field block (lines 324-338) becomes:
```python
class MethodReagent(db.Model):
    __tablename__ = "method_reagent"
    id = db.Column(db.Integer, primary_key=True)
    method_id = db.Column(db.Integer, db.ForeignKey("method.id"), nullable=False)
    reagent_id = db.Column(db.Integer, db.ForeignKey("reagent.id"), nullable=False)
    amount_per_determination = db.Column(db.Float, nullable=False)
    amount_per_blind = db.Column(db.Float, nullable=False, default=0)
    amount_unit = db.Column(UNIT_ENUM, nullable=False, default="mL")
    is_titrant = db.Column(db.Boolean, nullable=False, default=False)
    practical_amount_per_determination = db.Column(db.Float, nullable=True)
    step_description = db.Column(db.Text)
    notes = db.Column(db.Text)
```

- [ ] **Step 2: Create the migration file**

Create `migrations/versions/e5f6a7b8c9d0_add_practical_amount_to_method_reagent.py`:

```python
"""add practical_amount_per_determination to method_reagent

Revision ID: e5f6a7b8c9d0
Revises: 9c64dbf20d9e
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = '9c64dbf20d9e'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method_reagent')}
    if 'practical_amount_per_determination' not in existing_cols:
        with op.batch_alter_table('method_reagent', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('practical_amount_per_determination', sa.Float(), nullable=True)
            )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method_reagent')}
    if 'practical_amount_per_determination' in existing_cols:
        with op.batch_alter_table('method_reagent', schema=None) as batch_op:
            batch_op.drop_column('practical_amount_per_determination')
```

- [ ] **Step 3: Apply the migration**

```bash
cd C:\Users\Miche\Documents\GitHub\quanti-lims
flask db upgrade
```

Expected: no error; "Running upgrade 9c64dbf20d9e -> e5f6a7b8c9d0"

- [ ] **Step 4: Verify column exists**

```bash
python -c "
from app import app
from models import MethodReagent
with app.app_context():
    mr = MethodReagent.query.first()
    if mr:
        print(hasattr(mr, 'practical_amount_per_determination'))
        print(mr.practical_amount_per_determination)
    else:
        print('no MethodReagent rows yet; column added successfully')
"
```

Expected: `True` then `None` (or the "no rows" message if table is empty)

- [ ] **Step 5: Commit**

```bash
git add models.py migrations/versions/e5f6a7b8c9d0_add_practical_amount_to_method_reagent.py
git commit -m "feat: add practical_amount_per_determination to MethodReagent"
```

---

## Task 2: Admin UI — burette size configuration

**Files:**
- Modify: `app.py` (around lines 1158–1208)
- Modify: `templates/admin/method_reagents.html`

**Context:**
- `admin_method_reagent_add` is at `app.py:1158`. It creates a `MethodReagent` and saves it.
- `admin_method_reagent_delete` ends at `app.py:1207`. New route goes right after it (before line 1209 "SEMESTER MANAGEMENT").
- The template at `templates/admin/method_reagents.html` has a table (columns: Reagenz, Menge/Best., Menge/Blind, Einheit, Titrant?, Schritt, action) and an add form below.
- `canonical_unit_label` is already used in `app.py` to format unit labels. Import if needed.

- [ ] **Step 1: Note on testing for this task**

The admin route in this task (`set-practical`, `admin_method_reagent_add`) is covered by manual testing only — the validation logic (float > 0) is straightforward and the route has no unit-testable helper. Verify behavior in Step 6 (manual). No automated test is written here.

- [ ] **Step 2: Extend `admin_method_reagent_add` to save `practical_amount_per_determination`**

In `app.py`, inside `admin_method_reagent_add` (lines 1158–1195), after setting `is_titrant=is_titrant_requested` in the `MethodReagent(...)` constructor, add saving of `practical_amount_per_determination`.

Find this block (around line 1166):
```python
    mr = MethodReagent(
        method_id=method_id,
        reagent_id=int(request.form["reagent_id"]),
        amount_per_determination=float(request.form["amount_per_determination"]),
        amount_per_blind=float(request.form.get("amount_per_blind", 0)),
        amount_unit=normalize_unit(request.form.get("amount_unit") or "mL"),
        is_titrant=is_titrant_requested,
        step_description=request.form.get("step_description") or None,
    )
```

Replace with:
```python
    _practical_raw = request.form.get("practical_amount_per_determination", "").strip()
    _practical_val = None
    if is_titrant_requested and _practical_raw:
        try:
            _practical_val = float(_practical_raw)
            if _practical_val <= 0:
                _practical_val = None
        except ValueError:
            _practical_val = None

    mr = MethodReagent(
        method_id=method_id,
        reagent_id=int(request.form["reagent_id"]),
        amount_per_determination=float(request.form["amount_per_determination"]),
        amount_per_blind=float(request.form.get("amount_per_blind", 0)),
        amount_unit=normalize_unit(request.form.get("amount_unit") or "mL"),
        is_titrant=is_titrant_requested,
        practical_amount_per_determination=_practical_val,
        step_description=request.form.get("step_description") or None,
    )
```

- [ ] **Step 3: Add `set-practical` route**

In `app.py`, after `admin_method_reagent_delete` (after line 1207, before the "SEMESTER MANAGEMENT" comment at line 1209), insert:

```python
    @app.route("/admin/method-reagents/<int:id>/set-practical", methods=["POST"])
    def admin_method_reagent_set_practical(id):
        mr = MethodReagent.query.get_or_404(id)
        if not mr.is_titrant:
            flash("Bürettengröße ist nur für Titranten relevant.", "warning")
            return redirect(url_for("admin_method_reagents", method_id=mr.method_id))
        raw = request.form.get("practical_amount", "").strip()
        try:
            val = float(raw)
            if val <= 0:
                raise ValueError
        except ValueError:
            flash("Ungültige Bürettengröße.", "danger")
            return redirect(url_for("admin_method_reagents", method_id=mr.method_id))
        mr.practical_amount_per_determination = val
        db.session.commit()
        flash("Bürettengröße gespeichert.", "success")
        return redirect(url_for("admin_method_reagents", method_id=mr.method_id))

```

- [ ] **Step 4: Update `method_reagents.html` table**

Replace the existing `<thead>` row:
```html
<thead class="table-light"><tr><th>Reagenz</th><th>Menge/Best.</th><th>Menge/Blind</th><th>Einheit</th><th>Titrant?</th><th>Schritt</th><th></th></tr></thead>
```
With:
```html
<thead class="table-light"><tr><th>Reagenz</th><th>Menge/Best.</th><th>Menge/Blind</th><th>Einheit</th><th>Titrant?</th><th>Bürettengröße</th><th>Schritt</th><th></th></tr></thead>
```

Replace the existing table body row (the `{% for mr in method.reagent_usages %}` block) — find the closing `</tr>` and add the new cell before the action `<td>`. The current row is:

```html
{% for mr in method.reagent_usages %}
<tr>
  <td>{{ mr.reagent.name }}</td>
  <td>{{ mr.amount_per_determination }}</td>
  <td>{{ mr.amount_per_blind }}</td>
  <td>{{ mr.amount_unit|unit }}</td>
  <td>{% if mr.is_titrant %}<i class="bi bi-check-circle-fill text-success"></i>{% else %}–{% endif %}</td>
  <td class="text-body-secondary small">{{ mr.step_description or '–' }}</td>
  <td>
    <form method="POST" action="{{ url_for('admin_method_reagent_delete', id=mr.id) }}" class="d-inline" onsubmit="return confirm('Entfernen?')">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn btn-outline-danger btn-sm"><i class="bi bi-trash"></i></button>
    </form>
  </td>
</tr>
{% endfor %}
```

Replace with:
```html
{% for mr in method.reagent_usages %}
<tr>
  <td>{{ mr.reagent.name }}</td>
  <td>{{ mr.amount_per_determination }}</td>
  <td>{{ mr.amount_per_blind }}</td>
  <td>{{ mr.amount_unit|unit }}</td>
  <td>{% if mr.is_titrant %}<i class="bi bi-check-circle-fill text-success"></i>{% else %}–{% endif %}</td>
  <td>
    {% if mr.is_titrant %}
      {% if mr.practical_amount_per_determination is not none %}
        <form method="POST" action="{{ url_for('admin_method_reagent_set_practical', id=mr.id) }}" class="d-flex gap-1 align-items-center">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="number" name="practical_amount" value="{{ mr.practical_amount_per_determination }}" step="0.1" min="0.1" class="form-control form-control-sm" style="width:80px">
          <span class="text-muted small">{{ mr.amount_unit|unit }}</span>
          <button type="submit" class="btn btn-outline-secondary btn-sm"><i class="bi bi-check-lg"></i></button>
        </form>
      {% else %}
        <form method="POST" action="{{ url_for('admin_method_reagent_set_practical', id=mr.id) }}" class="d-flex gap-1 align-items-center">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="number" name="practical_amount" placeholder="z.B. 50" step="0.1" min="0.1" class="form-control form-control-sm border-warning" style="width:80px">
          <span class="text-muted small">{{ mr.amount_unit|unit }}</span>
          <button type="submit" class="btn btn-outline-warning btn-sm"><i class="bi bi-plus-lg"></i></button>
        </form>
      {% endif %}
    {% else %}
      <span class="text-muted">–</span>
    {% endif %}
  </td>
  <td class="text-body-secondary small">{{ mr.step_description or '–' }}</td>
  <td>
    <form method="POST" action="{{ url_for('admin_method_reagent_delete', id=mr.id) }}" class="d-inline" onsubmit="return confirm('Entfernen?')">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn btn-outline-danger btn-sm"><i class="bi bi-trash"></i></button>
    </form>
  </td>
</tr>
{% endfor %}
```

- [ ] **Step 5: Extend the add form with `practical_amount_per_determination` field + JS**

In `method_reagents.html`, find the add form's `is_titrant` checkbox row:
```html
    {% if can_mark_titrant %}
    <div class="col-md-2">{{ checkbox("is_titrant", "Titrant") }}</div>
    {% else %}
    <div class="col-md-2"></div>
    {% endif %}
```

After this `</div>` block (still inside the form, before the submit button col), add a new row for the burette size field. Insert after the closing `</div>` of the first row but before the submit button col. The cleanest insertion point is after the first `row g-2` closes and before the step_description row:

Find:
```html
  <div class="row">
    <div class="col-md-6">{{ field("step_description", "Schrittbeschreibung") }}</div>
  </div>
```

Replace with:
```html
  <div class="row mt-2" id="burette-size-row" style="display:none">
    <div class="col-md-3">
      <label class="form-label">Bürettengröße (mL)</label>
      <div class="d-flex gap-1 align-items-center">
        <input type="number" name="practical_amount_per_determination" id="practical_amount_field"
               step="0.1" min="0.1" class="form-control form-control-sm" style="width:90px" placeholder="z.B. 50">
        <button type="button" class="btn btn-outline-secondary btn-sm" onclick="document.getElementById('practical_amount_field').value='10'">10</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" onclick="document.getElementById('practical_amount_field').value='25'">25</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" onclick="document.getElementById('practical_amount_field').value='50'">50</button>
      </div>
      <div class="form-text">Bürettenfüllvolumen pro Bestimmung</div>
    </div>
  </div>
  <div class="row">
    <div class="col-md-6">{{ field("step_description", "Schrittbeschreibung") }}</div>
  </div>
```

Then add the JS (in `{% block scripts %}` at the end of the template, or inline before `{% endblock %}`). If there is no `{% block scripts %}` yet, add it:

```html
{% block scripts %}
<script>
(function() {
  var titrantBox = document.getElementById('is_titrant');
  var buretteRow = document.getElementById('burette-size-row');
  if (titrantBox && buretteRow) {
    function syncBuretteRow() {
      buretteRow.style.display = titrantBox.checked ? '' : 'none';
    }
    titrantBox.addEventListener('change', syncBuretteRow);
    syncBuretteRow();
  }
})();
</script>
{% endblock %}
```

Note: The `checkbox` macro renders an `<input type="checkbox" id="is_titrant" name="is_titrant">`. Verify the rendered `id` attribute matches `'is_titrant'` by inspecting the macro in `macros.html` — if it differs, adjust the JS accordingly.

- [ ] **Step 6: Verify manually**

Start the app and navigate to any `/admin/methods/<id>/reagents` page:
1. Existing titrant entry should show an inline input in the new "Bürettengröße" column (orange border if not set)
2. Submitting the inline form should reload the page with the value saved
3. Checking "Titrant?" in the add form should reveal the burette size field with preset buttons
4. Adding a new titrant reagent with a burette size should save both `is_titrant=True` and `practical_amount_per_determination`

- [ ] **Step 7: Commit**

```bash
git add app.py templates/admin/method_reagents.html
git commit -m "feat: add burette size configuration for titrant reagents"
```

---

## Task 3: Order list — practical totals

**Files:**
- Modify: `reagent_expansion.py` (function `build_expansion`, lines 188–249)
- Modify: `templates/reports/order_list.html`
- Modify: `tests/test_reagent_expansion.py`

**Context:**
- `build_expansion` iterates over `method.reagent_usages` (each `mr`). Each `mr` now has `practical_amount_per_determination` (nullable).
- `_VOL_TO_ML = {"µL": 0.001, "mL": 1.0, "L": 1000.0}` is already defined at the top of `reagent_expansion.py`.
- `order_acc` key is `(reagent.id, unit)`. After `expand_reagent`, the entry exists in `order_acc`. We can annotate it with practical data.
- Titrants are base reagents (not composites), so `expand_reagent` always terminates immediately for them (the leaf case). The key will be `(reagent.id, base_unit)` where `base_unit = reagent.base_unit` after `convert_to_base_unit`.

- [ ] **Step 1: Write failing tests**

In `tests/test_reagent_expansion.py`, add a new test class at the bottom:

```python
class TestBuildExpansionPractical:
    def _make_batch(self, mr_list):
        """Helper: build a mock batch with given MethodReagent mocks."""
        batch = MagicMock()
        batch.analysis.method.blind_required = False
        batch.analysis.method.b_blind_determinations = 0
        batch.analysis.method.reagent_usages = mr_list
        batch.analysis.k_determinations = 1
        batch.analysis.code = "T1"
        batch.analysis.name = "Test"
        batch.analysis.block = None
        batch.safety_factor = 1.0
        # 2 non-buffer samples
        s1, s2 = MagicMock(), MagicMock()
        s1.is_buffer = False
        s2.is_buffer = False
        batch.samples = [s1, s2]
        return batch

    def test_titrant_with_practical_amount_adds_practical_total(self):
        from reagent_expansion import build_expansion
        reagent = make_base_reagent(1, "HCl", base_unit="mL")
        mr = MagicMock()
        mr.reagent = reagent
        mr.amount_per_determination = 14.0
        mr.amount_per_blind = 0.0
        mr.amount_unit = "mL"
        mr.is_titrant = True
        mr.practical_amount_per_determination = 50.0

        batch = self._make_batch([mr])
        result = build_expansion([batch])

        items = result["order_items"]
        assert len(items) == 1
        item = items[0]
        # theoretical: n=2, k=1, b=0, safety=1.0 → 2 * 14 = 28
        assert item["total"] == 28.0
        # practical: n=2, practical=50, k+b=1 → 2 * 50 * 1 = 100
        assert item.get("practical_total") == 100.0
        assert item.get("is_titrant") is True

    def test_non_titrant_has_no_practical_total(self):
        from reagent_expansion import build_expansion
        reagent = make_base_reagent(2, "NaOH", base_unit="mL")
        mr = MagicMock()
        mr.reagent = reagent
        mr.amount_per_determination = 10.0
        mr.amount_per_blind = 0.0
        mr.amount_unit = "mL"
        mr.is_titrant = False
        mr.practical_amount_per_determination = None

        batch = self._make_batch([mr])
        result = build_expansion([batch])
        item = result["order_items"][0]
        assert item.get("practical_total") is None
        assert item.get("is_titrant") is not True

    def test_titrant_without_practical_amount_has_no_practical_total(self):
        from reagent_expansion import build_expansion
        reagent = make_base_reagent(3, "EDTA", base_unit="mL")
        mr = MagicMock()
        mr.reagent = reagent
        mr.amount_per_determination = 20.0
        mr.amount_per_blind = 0.0
        mr.amount_unit = "mL"
        mr.is_titrant = True
        mr.practical_amount_per_determination = None

        batch = self._make_batch([mr])
        result = build_expansion([batch])
        item = result["order_items"][0]
        assert item.get("practical_total") is None
        # but is_titrant should still be flagged
        assert item.get("is_titrant") is True

    def test_titrant_practical_includes_blind_fills(self):
        from reagent_expansion import build_expansion
        reagent = make_base_reagent(4, "KMnO4", base_unit="mL")
        mr = MagicMock()
        mr.reagent = reagent
        mr.amount_per_determination = 10.0
        mr.amount_per_blind = 5.0
        mr.amount_unit = "mL"
        mr.is_titrant = True
        mr.practical_amount_per_determination = 25.0

        batch = self._make_batch([mr])
        batch.analysis.method.blind_required = True
        batch.analysis.method.b_blind_determinations = 1
        result = build_expansion([batch])
        item = result["order_items"][0]
        # practical: n=2, practical=25, k=1, b=1, k+b=2 → 2 * 25 * 2 = 100
        assert item["practical_total"] == 100.0
```

Run: `pytest tests/test_reagent_expansion.py::TestBuildExpansionPractical -v`
Expected: 4 FAILURES (practical_total key not yet in output)

- [ ] **Step 2: Extend `build_expansion` to compute practical totals**

In `reagent_expansion.py`, in `build_expansion` (lines 188–249), find the inner `for mr in method.reagent_usages:` loop. Currently:

```python
        for mr in method.reagent_usages:
            reagent = mr.reagent
            if not reagent:
                continue
            total_amount = (
                n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
            )
            amount, unit, warning = convert_to_base_unit(reagent, total_amount, mr.amount_unit)
            if warning:
                warnings.append(warning)
            expand_reagent(reagent, amount, unit, order_acc, prep_acc, dep_graph, warnings,
                           block_info=block_info, analysis_info=analysis_info)
```

Replace with:

```python
        for mr in method.reagent_usages:
            reagent = mr.reagent
            if not reagent:
                continue
            total_amount = (
                n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
            )
            amount, unit, warning = convert_to_base_unit(reagent, total_amount, mr.amount_unit)
            if warning:
                warnings.append(warning)
            expand_reagent(reagent, amount, unit, order_acc, prep_acc, dep_graph, warnings,
                           block_info=block_info, analysis_info=analysis_info)

            # Track practical totals for titrants (burette fill size overrides theoretical)
            if mr.is_titrant:
                pract_key = (reagent.id, unit)
                if pract_key in order_acc:
                    order_acc[pract_key]["is_titrant"] = True
                if mr.practical_amount_per_determination is not None:
                    practical_raw = n * mr.practical_amount_per_determination * (k + b) * safety
                    pract_converted, _punit, pract_warn = convert_to_base_unit(
                        reagent, practical_raw, mr.amount_unit
                    )
                    if pract_warn:
                        warnings.append(pract_warn)
                    pract_key2 = (reagent.id, _punit)
                    if pract_key2 in order_acc:
                        entry = order_acc[pract_key2]
                        entry["practical_total"] = round(
                            entry.get("practical_total", 0.0) + pract_converted, 4
                        )
                        entry.setdefault("burette_amount", mr.practical_amount_per_determination)
                        entry.setdefault("burette_unit", mr.amount_unit)
```

Also extend the `order_items` list comprehension (lines 229–241) to pass through the new fields:

Find:
```python
    order_items = sorted(
        [
            {
                "name": v["name"],
                "cas": v["cas"],
                "total": v["total"],
                "unit": v["unit"],
                "sources": _build_sources(v["sources"]),
            }
            for v in order_acc.values()
        ],
        key=lambda x: x["name"],
    )
```

Replace with:
```python
    order_items = sorted(
        [
            {
                "name": v["name"],
                "cas": v["cas"],
                "total": v["total"],
                "unit": v["unit"],
                "sources": _build_sources(v["sources"]),
                "is_titrant": v.get("is_titrant", False),
                "practical_total": v.get("practical_total"),
                "burette_amount": v.get("burette_amount"),
                "burette_unit": v.get("burette_unit"),
            }
            for v in order_acc.values()
        ],
        key=lambda x: x["name"],
    )
```

- [ ] **Step 3: Run tests — expect pass**

```bash
pytest tests/test_reagent_expansion.py -v
```

Expected: all tests PASS including the 4 new ones.

- [ ] **Step 4: Update `order_list.html` to show practical total inline**

In `templates/reports/order_list.html`, find the existing `<td class="text-end">` Menge cell:

```html
  <td class="text-end"><strong>{{ "%.4g"|format(item.total) }}</strong></td>
  <td>{{ item.unit }}</td>
```

Replace with:

```html
  <td class="text-end">
    {% if item.is_titrant and item.practical_total is not none %}
      <strong>{{ "%.4g"|format(item.practical_total) }}</strong>
      <br><small class="text-muted">{{ "%.4g"|format(item.total) }} theoret.</small>
    {% elif item.is_titrant %}
      <strong>{{ "%.4g"|format(item.total) }}</strong>
      <br><span class="badge bg-warning text-dark" style="font-size:0.65rem">Bürettengröße fehlt</span>
    {% else %}
      <strong>{{ "%.4g"|format(item.total) }}</strong>
    {% endif %}
  </td>
  <td>{{ item.unit }}</td>
```

- [ ] **Step 5: Verify order list manually**

Navigate to `/reports/reagents/order-list` in the running app. Titrant rows with a configured burette size should show two values; titrants without should show the yellow badge; non-titrants unchanged.

- [ ] **Step 6: Commit**

```bash
git add reagent_expansion.py templates/reports/order_list.html tests/test_reagent_expansion.py
git commit -m "feat: show practical vs theoretical totals for titrants on order list"
```

---

## Task 4: Prep list flask suggestion + completeness overview

**Files:**
- Modify: `app.py` (functions `reports_prep_list` at line 2355 and `reports_reagents` at line 2295)
- Modify: `templates/reports/prep_list.html`
- Modify: `templates/reports/reagents.html`

**Context:**
- `reports_prep_list` builds a `blocks` list. Each block has `reagents` — each reagent dict has `"total"` (float) and `"unit"` (string, e.g. `"mL"`).
- `_VOL_TO_ML` is in `reagent_expansion.py` and needs to be imported.
- `reports_reagents` already queries `SampleBatch` for the active semester. The completeness query is scoped to analyses in the active semester.
- `MethodReagent`, `Method`, `Analysis`, `SampleBatch` are already imported in `app.py`.

- [ ] **Step 1: Write a failing test for flask suggestion logic**

In `tests/test_reagent_expansion.py`, add:

```python
class TestFlaskSuggestion:
    def _suggest(self, total_ml):
        from math import ceil
        FLASK_SIZES_ML = [50, 100, 250, 500, 1000, 2000]
        suggested = next((s for s in FLASK_SIZES_ML if s >= total_ml), None)
        if suggested is None:
            batches = ceil(total_ml / 2000)
            return f"{batches}× 2000 mL"
        return f"{suggested} mL"

    def test_suggest_exact_match(self):
        assert self._suggest(1000) == "1000 mL"

    def test_suggest_rounds_up(self):
        assert self._suggest(847) == "1000 mL"

    def test_suggest_small(self):
        assert self._suggest(30) == "50 mL"

    def test_suggest_large_needs_multiple(self):
        assert self._suggest(2500) == "2× 2000 mL"

    def test_non_volume_unit_returns_none(self):
        # Non-volume units (e.g., "g") should yield no suggestion
        from reagent_expansion import _VOL_TO_ML
        assert _VOL_TO_ML.get("g") is None  # "g" is not a volume unit
        # The app.py code path: if factor is None → suggested_flask = None
        factor = _VOL_TO_ML.get("g")
        assert factor is None
```

Run: `pytest tests/test_reagent_expansion.py::TestFlaskSuggestion -v`
Expected: PASS (logic is self-contained in the test — verifies the algorithm before we embed it in app.py)

- [ ] **Step 2: Extend `reports_prep_list` to add flask suggestions**

In `app.py` in `reports_prep_list` (line 2355), add the following. Find the existing import block at the top of the function:

```python
    from reagent_expansion import build_expansion
    from datetime import date as _date
    from collections import defaultdict
```

Replace with:

```python
    from reagent_expansion import build_expansion, _VOL_TO_ML
    from datetime import date as _date
    from collections import defaultdict
    from math import ceil
    _FLASK_SIZES_ML = [50, 100, 250, 500, 1000, 2000]
```

Then find the line where each reagent dict is appended (inside `block_reagents[block_key].append({...})`):

```python
            block_reagents[block_key].append({
                "name": item["name"],
                "total": round(total, 1),
                "unit": item["unit"],
                "components": components,
                "prep_notes": reagent.notes or "",
            })
```

Replace with:

```python
            _rg_total = round(total, 1)
            _rg_unit = item["unit"]
            _vol_factor = _VOL_TO_ML.get(_rg_unit)
            if _vol_factor is not None:
                _total_ml = _rg_total * _vol_factor
                _suggested = next((s for s in _FLASK_SIZES_ML if s >= _total_ml), None)
                _suggested_flask = (
                    f"{_suggested} mL" if _suggested is not None
                    else f"{ceil(_total_ml / 2000)}× 2000 mL"
                )
            else:
                _suggested_flask = None
            block_reagents[block_key].append({
                "name": item["name"],
                "total": _rg_total,
                "unit": _rg_unit,
                "components": components,
                "prep_notes": reagent.notes or "",
                "suggested_flask": _suggested_flask,
            })
```

- [ ] **Step 3: Update `prep_list.html` to show flask suggestion**

In `templates/reports/prep_list.html`, find the badge showing the total:

```html
          <span class="badge bg-primary ms-2">{{ rg.total }} {{ rg.unit }}</span>
```

Replace with:

```html
          <span class="badge bg-primary ms-2">{{ rg.total }} {{ rg.unit }}</span>
          {% if rg.suggested_flask %}
          <span class="badge bg-light text-muted border ms-1" style="font-size:0.7rem">→ {{ rg.suggested_flask }}</span>
          {% endif %}
```

- [ ] **Step 4: Extend `reports_reagents` to compute completeness query**

In `app.py` in `reports_reagents` (line 2295), first update the early return for no semester to pass the new variable:

```python
    if not sem:
        return render_template("reports/reagents.html", semester=None, demand=[], missing_burette_items=[])
```

Then after this block (before the `demand = []` line), add the completeness query. Find:

```python
    demand = []
    batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
```

Replace with:

```python
    # Completeness: titrants without burette size, scoped to active semester
    _active_analysis_ids = (
        db.session.query(SampleBatch.analysis_id)
        .filter(SampleBatch.semester_id == sem.id)
        .distinct()
        .subquery()
    )
    missing_burette = (
        db.session.query(MethodReagent, Method, Analysis)
        .join(Method, MethodReagent.method_id == Method.id)
        .join(Analysis, Method.analysis_id == Analysis.id)
        .filter(
            MethodReagent.is_titrant == True,
            MethodReagent.practical_amount_per_determination.is_(None),
            Analysis.id.in_(_active_analysis_ids),
        )
        .order_by(Analysis.code)
        .all()
    )
    missing_burette_items = [
        {
            "analysis_code": a.code,
            "analysis_name": a.name,
            "method_id": m.id,
            "method_type": m.method_type,
            "reagent_name": mr.reagent.name,
        }
        for mr, m, a in missing_burette
    ]

    demand = []
    batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
```

Also pass `missing_burette_items` to the template. Find the final `return render_template(...)` in `reports_reagents`:

```python
    return render_template("reports/reagents.html", semester=sem, demand=demand, has_non_volume_units=has_non_volume_units)
```

Replace with:

```python
    return render_template(
        "reports/reagents.html",
        semester=sem,
        demand=demand,
        has_non_volume_units=has_non_volume_units,
        missing_burette_items=missing_burette_items,
    )
```

Note: `Analysis` may not be imported at the top of `app.py`. Check with `grep -n "^from models import\|^import models" app.py` and add `Analysis` to the import if missing.

- [ ] **Step 5: Update `reagents.html` to show completeness alert**

In `templates/reports/reagents.html`, find the line after the semester/demand guards (after `{% else %}` but before the `<p class="text-body-secondary small">` formula explanation, around line 20):

```html
{% else %}

<p class="text-body-secondary small">
```

Insert the completeness alert between `{% else %}` and `<p>`:

```html
{% else %}

{% if missing_burette_items %}
<div class="alert alert-warning mb-3">
  <strong><i class="bi bi-exclamation-triangle"></i> {{ missing_burette_items|length }} Maßlösung{{ 'en' if missing_burette_items|length != 1 else '' }} ohne Bürettengröße:</strong>
  <ul class="mb-0 mt-1 small">
    {% for item in missing_burette_items %}
    <li>
      {{ item.analysis_code }} {{ item.analysis_name }} ({{ item.method_type }}) — {{ item.reagent_name }}
      <a href="{{ url_for('admin_method_reagents', method_id=item.method_id) }}" class="ms-1">konfigurieren →</a>
    </li>
    {% endfor %}
  </ul>
</div>
{% endif %}

<p class="text-body-secondary small">
```

- [ ] **Step 6: Verify manually**

1. Navigate to `/reports/reagents/prep-list` — composite reagents should show a grey "→ 1000 mL" style hint badge
2. Navigate to `/reports/reagents` — if any titrants are missing burette size, the warning alert should appear with links to the admin page

- [ ] **Step 7: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add app.py templates/reports/prep_list.html templates/reports/reagents.html tests/test_reagent_expansion.py
git commit -m "feat: add flask suggestions on prep list and burette completeness overview"
```
