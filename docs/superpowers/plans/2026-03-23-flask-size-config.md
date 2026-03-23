# Flask Size Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let TAs confirm or override the flask size per composite reagent per block, and propagate flask-corrected amounts to prep list components, order list, and reagent overview.

**Architecture:** New `PrepFlaskConfig` table stores `(reagent_id, block_id, flask_size_ml)`. `build_expansion` in `reagent_expansion.py` is extended with provenance tracking and a flask-correction post-processing step. Three routes (`reports_prep_list`, `reports_order_list`, `reports_reagents`) pass flask configs from DB and receive corrected amounts. A new POST route saves overrides.

**Tech Stack:** Flask, SQLAlchemy, Alembic, Jinja2, Bootstrap 5, pytest + unittest.mock

---

## Spec

`docs/superpowers/specs/2026-03-23-flask-size-config-design.md`

---

## Files

| File | Action | Responsibility |
|---|---|---|
| `models.py` | Modify | Add `PrepFlaskConfig` model |
| `migrations/versions/d4e5f6a7b8c9_add_prep_flask_config.py` | Create | Alembic migration |
| `reagent_expansion.py` | Modify | `FLASK_SIZES_ML`, `_suggest_flask_size_ml`, extend `expand_reagent` + `build_expansion` |
| `app.py` | Modify | Extend `reports_prep_list`, add `prep_flask_config_set` route, extend `reports_order_list` + `reports_reagents` |
| `templates/reports/prep_list.html` | Modify | Flask selector UI + corrected component amounts |
| `templates/reports/reagents.html` | Modify | `effective_total` in component display + completeness warning |
| `tests/test_reagent_expansion.py` | Modify | Tests for `_suggest_flask_size_ml`, `build_expansion` with flask configs |

---

## Task 1: PrepFlaskConfig model + migration

**Files:**
- Modify: `models.py` (after `ReagentComponent`, ~line 322)
- Create: `migrations/versions/d4e5f6a7b8c9_add_prep_flask_config.py`

- [ ] **Step 1: Add PrepFlaskConfig to models.py**

After the `ReagentComponent` class (before `MethodReagent`), add:

```python
class PrepFlaskConfig(db.Model):
    __tablename__ = "prep_flask_config"
    id = db.Column(db.Integer, primary_key=True)
    reagent_id = db.Column(db.Integer, db.ForeignKey("reagent.id"), nullable=False)
    # block_id: NULL = Vorabherstellungen; no FK (sentinel 0 not used here, NULL in DB)
    block_id = db.Column(db.Integer, nullable=True)
    flask_size_ml = db.Column(db.Float, nullable=False)

    reagent = db.relationship("Reagent")
```

- [ ] **Step 2: Create the Alembic migration**

Create `migrations/versions/d4e5f6a7b8c9_add_prep_flask_config.py`:

```python
"""add prep_flask_config table

Revision ID: d4e5f6a7b8c9
Revises: 9c64dbf20d9e
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = '9c64dbf20d9e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'prep_flask_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reagent_id', sa.Integer(), sa.ForeignKey('reagent.id'), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=True),
        sa.Column('flask_size_ml', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('prep_flask_config')
```

- [ ] **Step 3: Run migration**

```bash
flask db upgrade
```

Expected: no errors, `prep_flask_config` table created.

- [ ] **Step 4: Verify model imports in app.py**

In `app.py`, find the import that pulls in model classes (search for `from models import` or `PrepFlaskConfig`). Add `PrepFlaskConfig` to the import if it's not auto-imported via `db.Model` registration. In this codebase, models are imported via `from models import ...` at the top or via `create_app`. Verify `PrepFlaskConfig` is accessible in routes — search `app.py` for `from models import` and add `PrepFlaskConfig` to the list if needed.

- [ ] **Step 5: Commit**

```bash
git add models.py migrations/versions/d4e5f6a7b8c9_add_prep_flask_config.py
git commit -m "feat: add PrepFlaskConfig model and migration"
```

---

## Task 2: _suggest_flask_size_ml helper + build_expansion signature

**Files:**
- Modify: `reagent_expansion.py`
- Modify: `tests/test_reagent_expansion.py`

- [ ] **Step 1: Write failing tests for _suggest_flask_size_ml**

Append to `tests/test_reagent_expansion.py`:

```python
class TestSuggestFlaskSizeMl:
    def test_exact_match(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(500.0) == 500.0

    def test_rounds_up_to_next_size(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(501.0) == 1000.0

    def test_small_value(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(30.0) == 50.0

    def test_over_max_returns_2000(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(2001.0) == 2000.0

    def test_zero_returns_50(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(0.0) == 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reagent_expansion.py::TestSuggestFlaskSizeMl -v
```

Expected: FAIL — `ImportError: cannot import name '_suggest_flask_size_ml'`

- [ ] **Step 3: Add FLASK_SIZES_ML and _suggest_flask_size_ml to reagent_expansion.py**

After the `_VOL_TO_ML` line (line 8), add:

```python
FLASK_SIZES_ML = [50, 100, 250, 500, 1000, 2000]


def _suggest_flask_size_ml(total_ml: float) -> float:
    """Return numeric mL value of the smallest standard flask >= total_ml.

    Returns 2000.0 if total_ml exceeds the largest size (caller uses
    count = ceil(total_ml / 2000) to determine how many flasks are needed).
    """
    for s in FLASK_SIZES_ML:
        if s >= total_ml:
            return float(s)
    return 2000.0
```

- [ ] **Step 4: Extend build_expansion signature**

Change line 188:
```python
def build_expansion(batches) -> dict:
```
to:
```python
def build_expansion(batches, flask_configs=None) -> dict:
    # flask_configs: dict[(reagent_id, block_id_or_None) -> flask_size_ml] | None
    # When None (default), no flask correction is applied (backward-compatible).
```

No other behavior changes in this task.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_reagent_expansion.py -v
```

Expected: all existing tests + 5 new `TestSuggestFlaskSizeMl` tests pass.

- [ ] **Step 6: Commit**

```bash
git add reagent_expansion.py tests/test_reagent_expansion.py
git commit -m "feat: add _suggest_flask_size_ml helper and flask_configs param to build_expansion"
```

---

## Task 3: Herstellliste — flask size selector + corrected component amounts

**Files:**
- Modify: `app.py` (~lines 2354–2413 for `reports_prep_list`; add new route near line 2413)
- Modify: `templates/reports/prep_list.html`

- [ ] **Step 1: Extend reports_prep_list in app.py**

Replace the body of `reports_prep_list` (lines 2355–2413) with:

```python
    @app.route("/reports/reagents/prep-list")
    def reports_prep_list():
        from math import ceil
        sem = active_semester()
        if not sem:
            return render_template("reports/prep_list.html", semester=None, blocks=[], generated=None)
        from reagent_expansion import build_expansion, FLASK_SIZES_ML, _suggest_flask_size_ml
        from datetime import date as _date
        from collections import defaultdict

        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        flask_configs = {(c.reagent_id, c.block_id): c.flask_size_ml
                         for c in PrepFlaskConfig.query.all()}
        result = build_expansion(batches, flask_configs)
        prep_items = result["prep_items"]
        sorted_prep_ids = result["sorted_prep_ids"]

        block_reagents: dict = defaultdict(list)
        for rg_id in sorted_prep_ids:
            if rg_id not in prep_items:
                continue
            for block_key, item in prep_items[rg_id].items():
                reagent = item["reagent"]
                theoretical = item["total"]
                db_block_id = block_key[0] if block_key is not None else None
                flask_size = flask_configs.get((rg_id, db_block_id))
                if flask_size is None:
                    flask_size = _suggest_flask_size_ml(theoretical)
                count = ceil(theoretical / flask_size) if flask_size > 0 else 1
                effective_total = flask_size * count

                # Quick-select button sizes: all S where 1 <= ceil(theoretical/S) <= 5
                button_sizes = [s for s in FLASK_SIZES_ML
                                if 1 <= ceil(theoretical / s) <= 5]
                if not button_sizes:
                    button_sizes = [s for s in FLASK_SIZES_ML
                                    if ceil(theoretical / s) <= 10]

                components = []
                for comp in reagent.components:
                    if comp.child and comp.per_parent_volume_ml and comp.per_parent_volume_ml > 0:
                        comp_total = round(effective_total / comp.per_parent_volume_ml * comp.quantity, 2)
                        components.append({
                            "name": comp.child.name,
                            "amount": comp_total,
                            "unit": canonical_unit_label(comp.quantity_unit),
                        })
                block_reagents[block_key].append({
                    "name": item["name"],
                    "reagent_id": rg_id,
                    "total": round(theoretical, 1),
                    "unit": item["unit"],
                    "effective_total": round(effective_total, 1),
                    "flask_size": int(flask_size) if flask_size == int(flask_size) else flask_size,
                    "flask_count": count,
                    "button_sizes": button_sizes,
                    "components": components,
                    "prep_notes": reagent.notes or "",
                })

        blocks = []
        if None in block_reagents:
            blocks.append({
                "id": None,
                "name": "Vorabherstellungen",
                "reagents": block_reagents[None],
            })
        for block_key, reagents in sorted(
            ((k, v) for k, v in block_reagents.items() if k is not None),
            key=lambda x: x[0][0],
        ):
            blocks.append({"id": block_key[0], "name": block_key[1], "reagents": reagents})

        return render_template(
            "reports/prep_list.html",
            semester=sem,
            blocks=blocks,
            generated=_date.today().isoformat(),
        )
```

- [ ] **Step 2: Add the set-flask POST route**

Insert immediately after `reports_prep_list` (before `admin_system` at line ~2415):

```python
    @app.route("/prep-flask-config/<int:reagent_id>/<int:block_id>", methods=["POST"])
    def prep_flask_config_set(reagent_id, block_id):
        from flask import request, redirect, url_for, flash
        db_block_id = None if block_id == 0 else block_id
        try:
            flask_size = float(request.form["flask_size"])
        except (KeyError, ValueError):
            flash("Ungültige Kolbengröße.", "danger")
            return redirect(url_for("reports_prep_list"))
        if flask_size <= 0:
            flash("Kolbengröße muss größer als 0 sein.", "danger")
            return redirect(url_for("reports_prep_list"))
        cfg = PrepFlaskConfig.query.filter_by(
            reagent_id=reagent_id, block_id=db_block_id
        ).first()
        if cfg:
            cfg.flask_size_ml = flask_size
        else:
            db.session.add(PrepFlaskConfig(
                reagent_id=reagent_id,
                block_id=db_block_id,
                flask_size_ml=flask_size,
            ))
        db.session.commit()
        return redirect(url_for("reports_prep_list"))
```

- [ ] **Step 3: Update templates/reports/prep_list.html**

Replace the reagent card content (lines 31–55) with:

```html
    {% for rg in block.reagents %}
    <div class="col">
      <div class="border rounded p-3 h-100">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <strong>{{ rg.name }}</strong>
          <span class="badge bg-secondary ms-2">{{ rg.total }} {{ rg.unit }} Bedarf</span>
        </div>

        {# Flask size selector #}
        <div class="mb-2">
          <div class="fw-bold mb-1">
            {{ rg.flask_count }} × {{ rg.flask_size }} mL
            <span class="text-muted small fw-normal">(Bedarf: {{ rg.total }} {{ rg.unit }})</span>
          </div>
          <form method="POST"
                action="/prep-flask-config/{{ rg.reagent_id }}/{{ block.id if block.id is not none else 0 }}"
                class="d-flex flex-wrap gap-1 align-items-center">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            {% for s in rg.button_sizes %}
            <button type="submit" name="flask_size" value="{{ s }}"
                    class="btn btn-sm {% if s == rg.flask_size %}btn-primary{% else %}btn-outline-secondary{% endif %}">
              {{ s }} mL
            </button>
            {% endfor %}
          </form>
        </div>

        {% if rg.components %}
        <p class="text-muted small mb-1 text-uppercase fw-bold" style="font-size:0.65rem;letter-spacing:.05em">Zusammensetzung ({{ rg.flask_count }} × {{ rg.flask_size }} mL)</p>
        <table class="table table-sm table-borderless mb-2">
          {% for comp in rg.components %}
          <tr>
            <td class="py-0 fw-bold text-end pe-2" style="width:80px">{{ comp.amount }} {{ comp.unit }}</td>
            <td class="py-0">{{ comp.name }}</td>
          </tr>
          {% endfor %}
        </table>
        {% endif %}
        {% if rg.prep_notes %}
        <div class="alert alert-warning py-1 px-2 mb-0 small">
          <i class="bi bi-exclamation-triangle"></i> {{ rg.prep_notes }}
        </div>
        {% endif %}
      </div>
    </div>
    {% endfor %}
```

- [ ] **Step 4: Manually test in browser**

Start the app (`flask run`) and navigate to `/reports/reagents/prep-list`:
- Each composite reagent shows flask count × size and a row of quick-select buttons
- Clicking a button changes the flask size and reloads the page with updated component amounts
- Theoretical total shows in grey

- [ ] **Step 5: Commit**

```bash
git add app.py templates/reports/prep_list.html
git commit -m "feat: add flask size selector and corrected component amounts to prep list"
```

---

## Task 4: Bestellliste — provenance tracking + flask-corrected order amounts

**Files:**
- Modify: `reagent_expansion.py` (extend `expand_reagent`, `build_expansion`)
- Modify: `app.py` (`reports_order_list`)
- Modify: `tests/test_reagent_expansion.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_reagent_expansion.py`:

```python
class TestBuildExpansionFlaskCorrection:
    """Flask correction scales composite component contributions in order_acc."""

    def _make_batch(self, analysis_code, composite, amount_ml, block_id=None):
        """Helper: one batch with one method reagent using the given composite."""
        from unittest.mock import MagicMock
        mr = MagicMock()
        mr.reagent = composite
        mr.amount_per_determination = amount_ml
        mr.amount_per_blind = 0
        mr.amount_unit = "mL"
        mr.is_titrant = False
        mr.practical_amount_per_determination = None

        method = MagicMock()
        method.blind_required = False
        method.b_blind_determinations = 0
        method.reagent_usages = [mr]

        block = MagicMock() if block_id else None
        if block:
            block.id = block_id
            block.code = f"B{block_id}"
            block.name = f"Block {block_id}"

        analysis = MagicMock()
        analysis.method = method
        analysis.block = block
        analysis.k_determinations = 1
        analysis.code = analysis_code
        analysis.name = analysis_code

        sample = MagicMock()
        sample.is_buffer = False

        batch = MagicMock()
        batch.analysis = analysis
        batch.samples = [sample]
        batch.safety_factor = 1.0
        return batch

    def test_no_flask_configs_no_change(self):
        """Without flask_configs, order amounts are theoretical."""
        from reagent_expansion import build_expansion
        base = make_base_reagent(1, "HCl", "mL")
        # composite: 10 mL HCl per 100 mL parent
        composite = make_composite(2, "Buffer", [(base, 10.0, "mL", 100.0)])
        batch = self._make_batch("I.1", composite, 83.0, block_id=1)
        result = build_expansion([batch], flask_configs=None)
        items = {i["name"]: i for i in result["order_items"]}
        # theoretical: 83 mL composite * (10/100) = 8.3 mL HCl
        assert abs(items["HCl"]["total"] - 8.3) < 0.01

    def test_flask_correction_scales_component(self):
        """Flask config rounds composite up to flask size; components scale proportionally."""
        from reagent_expansion import build_expansion
        base = make_base_reagent(1, "HCl", "mL")
        composite = make_composite(2, "Buffer", [(base, 10.0, "mL", 100.0)])
        batch = self._make_batch("I.1", composite, 83.0, block_id=1)
        # flask_size=100 mL, count=ceil(83/100)=1, effective=100 mL
        flask_configs = {(2, 1): 100.0}
        result = build_expansion([batch], flask_configs=flask_configs)
        items = {i["name"]: i for i in result["order_items"]}
        # corrected: 100 mL * (10/100) = 10 mL HCl
        assert abs(items["HCl"]["total"] - 10.0) < 0.01

    def test_direct_base_reagent_unaffected(self):
        """Flask correction does not affect directly-used base reagents."""
        from reagent_expansion import build_expansion
        base_direct = make_base_reagent(1, "HCl", "mL")
        base_via = make_base_reagent(3, "NaOH", "mL")
        composite = make_composite(2, "Buffer", [(base_via, 5.0, "mL", 100.0)])

        mr_direct = MagicMock()
        mr_direct.reagent = base_direct
        mr_direct.amount_per_determination = 50.0
        mr_direct.amount_per_blind = 0
        mr_direct.amount_unit = "mL"
        mr_direct.is_titrant = False
        mr_direct.practical_amount_per_determination = None

        mr_comp = MagicMock()
        mr_comp.reagent = composite
        mr_comp.amount_per_determination = 83.0
        mr_comp.amount_per_blind = 0
        mr_comp.amount_unit = "mL"
        mr_comp.is_titrant = False
        mr_comp.practical_amount_per_determination = None

        method = MagicMock()
        method.blind_required = False
        method.b_blind_determinations = 0
        method.reagent_usages = [mr_direct, mr_comp]

        block = MagicMock()
        block.id = 1
        block.code = "B1"
        block.name = "Block 1"

        analysis = MagicMock()
        analysis.method = method
        analysis.block = block
        analysis.k_determinations = 1
        analysis.code = "I.1"
        analysis.name = "I.1"

        sample = MagicMock()
        sample.is_buffer = False

        batch = MagicMock()
        batch.analysis = analysis
        batch.samples = [sample]
        batch.safety_factor = 1.0

        flask_configs = {(2, 1): 100.0}  # only composite has flask config
        result = build_expansion([batch], flask_configs=flask_configs)
        items = {i["name"]: i for i in result["order_items"]}
        # HCl used directly: 50 mL, unchanged
        assert abs(items["HCl"]["total"] - 50.0) < 0.01
        # NaOH via composite: 83 * (5/100) = 4.15 theoretical, corrected to 100 * (5/100) = 5.0
        assert abs(items["NaOH"]["total"] - 5.0) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reagent_expansion.py::TestBuildExpansionFlaskCorrection -v
```

Expected: `test_no_flask_configs_no_change` passes (no behavior change yet); `test_flask_correction_scales_component` and `test_direct_base_reagent_unaffected` FAIL (correction not implemented yet).

- [ ] **Step 3: Extend expand_reagent with provenance tracking**

In `reagent_expansion.py`, replace the `expand_reagent` signature (lines 108–120) with:

```python
def expand_reagent(
    reagent,
    amount: float,
    unit: str,
    order_acc: dict,
    prep_acc: dict,
    dep_graph: dict,
    warnings: list,
    visiting: frozenset | None = None,
    caller_name: str | None = None,
    block_info: tuple | None = None,
    analysis_info: str | None = None,
    composite_contrib_acc: dict | None = None,
    top_composite_id: int | None = None,
) -> None:
```

In the non-composite branch (after `order_acc[key]["sources"][src_key] += amount`), add:

```python
        if composite_contrib_acc is not None and top_composite_id is not None:
            ckey = (reagent.id, unit, top_composite_id, block_info)
            composite_contrib_acc[ckey] = composite_contrib_acc.get(ckey, 0.0) + amount
```

In the composite branch recursive call (lines 180–185), add the new params:

```python
        expand_reagent(
            comp.child, comp_amount, comp_unit,
            order_acc, prep_acc, dep_graph, warnings,
            new_visiting, caller_name=reagent.name, block_info=block_info,
            analysis_info=analysis_info,
            composite_contrib_acc=composite_contrib_acc,
            top_composite_id=top_composite_id if top_composite_id is not None else reagent.id,
        )
```

- [ ] **Step 4: Add post-processing to build_expansion**

In `build_expansion`, add `composite_contrib_acc: dict = {}` after `warnings: list = []` (line 200):

```python
    composite_contrib_acc: dict = {}
```

Pass it to `expand_reagent` in the call at line 226:

```python
            expand_reagent(reagent, amount, unit, order_acc, prep_acc, dep_graph, warnings,
                           block_info=block_info, analysis_info=analysis_info,
                           composite_contrib_acc=composite_contrib_acc if flask_configs else None)
```

Add the post-processing block after the batch loop, before `order_items = sorted(...)` (line 229):

```python
    # Flask correction: scale base-reagent contributions via composites
    # (runs inside build_expansion, sharing local prep_acc and order_acc)
    if flask_configs and composite_contrib_acc:
        from math import ceil
        for (base_id, unit, composite_id, blk_info) in composite_contrib_acc:
            db_block_id = blk_info[0] if blk_info is not None else None
            flask_size = flask_configs.get((composite_id, db_block_id))
            if flask_size is None:
                continue
            block_data = (prep_acc.get(composite_id) or {}).get(blk_info)
            if block_data is None:
                continue
            theoretical = block_data["total"]
            if theoretical <= 0:
                continue
            count = ceil(theoretical / flask_size)
            effective = flask_size * count
            scale = effective / theoretical  # always >= 1.0
            contrib = composite_contrib_acc[(base_id, unit, composite_id, blk_info)]
            order_acc[(base_id, unit)]["total"] += contrib * (scale - 1.0)

```

- [ ] **Step 5: Update reports_order_list to pass flask_configs**

In `app.py`, replace `reports_order_list` body (lines 2334–2352):

```python
    @app.route("/reports/reagents/order-list")
    def reports_order_list():
        sem = active_semester()
        if not sem:
            return render_template(
                "reports/order_list.html", semester=None, items=[], generated=None, warnings=[]
            )
        from reagent_expansion import build_expansion
        from datetime import date as _date

        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        flask_configs = {(c.reagent_id, c.block_id): c.flask_size_ml
                         for c in PrepFlaskConfig.query.all()}
        result = build_expansion(batches, flask_configs)
        return render_template(
            "reports/order_list.html",
            semester=sem,
            items=result["order_items"],
            warnings=result["warnings"],
            generated=_date.today().isoformat(),
        )
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_reagent_expansion.py -v
```

Expected: all tests pass including `TestBuildExpansionFlaskCorrection`.

- [ ] **Step 7: Commit**

```bash
git add reagent_expansion.py app.py tests/test_reagent_expansion.py
git commit -m "feat: add provenance tracking and flask correction to order list"
```

---

## Task 5: Reagenzübersicht — effective_total + completeness warning

**Files:**
- Modify: `app.py` (`reports_reagents`, lines 2294–2332)
- Modify: `templates/reports/reagents.html`

- [ ] **Step 1: Extend reports_reagents to compute effective_total per demand entry**

Replace `reports_reagents` (lines 2294–2332):

```python
    @app.route("/reports/reagents")
    def reports_reagents():
        from math import ceil
        sem = active_semester()
        if not sem:
            return render_template("reports/reagents.html", semester=None, demand=[],
                                   missing_flask_items=[], has_non_volume_units=False)
        demand = []
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        for batch in batches:
            analysis = batch.analysis
            method = analysis.method
            if not method:
                continue
            k = analysis.k_determinations or 1
            b = method.b_blind_determinations if method.blind_required else 0
            n = sum(1 for s in batch.samples if not s.is_buffer)
            safety = getattr(batch, 'safety_factor', 1.2) or 1.2
            block = getattr(analysis, "block", None)
            block_info = (block.id, f"{block.code} – {block.name}") if block else None
            for mr in method.reagent_usages:
                formula_kind = "volumetric" if mr.amount_unit_type == AMOUNT_UNIT_VOLUME else "generic"
                total = n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
                demand.append({
                    "analysis": analysis.code,
                    "analysis_name": analysis.name,
                    "reagent": mr.reagent.name,
                    "reagent_obj": mr.reagent,
                    "unit": canonical_unit_label(mr.amount_unit),
                    "per_det": mr.amount_per_determination,
                    "per_blind": mr.amount_per_blind,
                    "formula_kind": formula_kind,
                    "k": k,
                    "b": b,
                    "n": n,
                    "safety": safety,
                    "total": round(total, 4),
                    "is_titrant": mr.is_titrant,
                    "is_composite": mr.reagent.is_composite,
                    "components": mr.reagent.components if mr.reagent.is_composite else [],
                    "block_info": block_info,
                })

        # Flask correction: compute effective_total per demand entry for composites
        flask_configs = {(c.reagent_id, c.block_id): c.flask_size_ml
                         for c in PrepFlaskConfig.query.all()}
        if flask_configs:
            from reagent_expansion import build_expansion, _suggest_flask_size_ml
            expansion = build_expansion(batches, flask_configs)
            prep_items = expansion["prep_items"]
            for d in demand:
                if not d["is_composite"]:
                    d["effective_total"] = d["total"]
                    continue
                rg_id = d["reagent_obj"].id
                blk_info = d["block_info"]
                block_data = (prep_items.get(rg_id) or {}).get(blk_info)
                if block_data and block_data["total"] > 0:
                    theoretical_block = block_data["total"]
                    db_block_id = blk_info[0] if blk_info is not None else None
                    flask_size = flask_configs.get((rg_id, db_block_id))
                    if flask_size:
                        count = ceil(theoretical_block / flask_size)
                        effective_block = flask_size * count
                        scale = effective_block / theoretical_block
                    else:
                        scale = 1.0
                    d["effective_total"] = round(d["total"] * scale, 4)
                else:
                    d["effective_total"] = d["total"]
        else:
            for d in demand:
                d["effective_total"] = d["total"]

        # Completeness warning: which composites lack PrepFlaskConfig in this semester
        # Reuse expansion["prep_items"] if already computed; otherwise call build_expansion once.
        from reagent_expansion import build_expansion as _be
        if flask_configs:
            prep_items_check = expansion["prep_items"]
        else:
            prep_items_check = _be(batches)["prep_items"]
        missing_flask_items = []
        for rg_id, blocks in prep_items_check.items():
            for blk_info, item in blocks.items():
                db_block_id = blk_info[0] if blk_info is not None else None
                if (rg_id, db_block_id) not in flask_configs:
                    block_label = blk_info[1] if blk_info else "Vorabherstellung"
                    missing_flask_items.append({
                        "reagent_name": item["reagent"].name,
                        "block_label": block_label,
                    })
        missing_flask_items.sort(key=lambda x: (x["reagent_name"], x["block_label"]))

        has_non_volume_units = any(get_amount_unit_type(d["unit"]) != AMOUNT_UNIT_VOLUME for d in demand)
        return render_template(
            "reports/reagents.html",
            semester=sem,
            demand=demand,
            has_non_volume_units=has_non_volume_units,
            missing_flask_items=missing_flask_items,
        )
```

- [ ] **Step 2: Update templates/reports/reagents.html**

After the `{% else %}` block (line 18) and before the formula `<p>` (line 20), add the completeness warning:

```html
{% if missing_flask_items %}
<div class="alert alert-warning">
  <strong>{{ missing_flask_items|length }} Herstellreagenzien ohne bestätigte Kolbengröße:</strong>
  <ul class="mb-0 mt-1">
    {% for item in missing_flask_items %}
    <li>{{ item.reagent_name }} — {{ item.block_label }} →
      <a href="{{ url_for('reports_prep_list') }}">konfigurieren</a></li>
    {% endfor %}
  </ul>
</div>
{% endif %}
```

In the composite component section (line 65–69), replace the formula label and `comp_total` calculation:

Replace:
```html
    <small class="text-muted d-block mb-1">Zusammensetzung (skaliert auf {{ d.total }} {{ d.unit|unit }} Gesamtbedarf):</small>
    <table class="table table-sm table-borderless mb-0 ms-2">
    {% for comp in d.components %}
    {% if comp.per_parent_volume_ml and comp.per_parent_volume_ml > 0 %}
    {% set comp_total = (d.total / comp.per_parent_volume_ml * comp.quantity)|round(1) %}
```

With:
```html
    <small class="text-muted d-block mb-1">Zusammensetzung (skaliert auf {{ d.effective_total }} {{ d.unit|unit }} effektiver Gesamtbedarf):</small>
    <table class="table table-sm table-borderless mb-0 ms-2">
    {% for comp in d.components %}
    {% if comp.per_parent_volume_ml and comp.per_parent_volume_ml > 0 %}
    {% set comp_total = (d.effective_total / comp.per_parent_volume_ml * comp.quantity)|round(1) %}
```

- [ ] **Step 3: Manually test in browser**

Navigate to `/reports/reagents`:
- Without any flask configs: alert shows all composite reagents as unconfigured; components use theoretical amounts
- After setting flask sizes on prep list: alert disappears for configured ones; component amounts scale up proportionally

- [ ] **Step 4: Commit**

```bash
git add app.py templates/reports/reagents.html
git commit -m "feat: add flask-corrected component display and completeness warning to reagents overview"
```

---

## Final verification

- [ ] Run full test suite:

```bash
pytest tests/test_reagent_expansion.py -v
```

Expected: all tests pass (0 failures).

- [ ] Check that existing routes still work:
  - `/reports/reagents` — loads without error
  - `/reports/reagents/prep-list` — shows flask selectors
  - `/reports/reagents/order-list` — loads without error
  - POST to `/prep-flask-config/1/1` with `flask_size=500` — saves and redirects

- [ ] Use `superpowers:finishing-a-development-branch` to merge or create PR.
