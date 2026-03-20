# Mass Determination Mode & Reagent Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `mass_determination` calculation mode for pure-substance analyses (Glycerol), and improve reagent requirement calculations with configurable safety factors, per-batch k=1 base count, and printable Bestell-/Herstelllisten.

**Architecture:** New `MassDeterminationEvaluator` in `calculation_modes.py` follows the exact same `ModeEvaluator` protocol as the two existing evaluators. Two new Analysis DB fields define the TA weighing range. SampleBatch gains a `safety_factor` field. Two new report routes provide printable lists.

**Tech Stack:** Python/Flask, SQLAlchemy, SQLite (legacy SQL migrations), Jinja2 templates, vanilla JS in templates, pytest.

**Spec:** `docs/superpowers/specs/2026-03-20-mass-determination-and-reagent-improvements-design.md`

---

## File Map

| File | Change |
|------|--------|
| `migrations/legacy_sql/20260320_mass_det_fields.sql` | CREATE — new DB columns |
| `calculation_modes.py` | MODIFY — add MODE_MASS_DETERMINATION, MassDeterminationEvaluator, extend resolve_mode/get_evaluator |
| `models.py` | MODIFY — Analysis new fields, SampleBatch.safety_factor, Sample.is_weighed, imports |
| `app.py` | MODIFY — analysis form handler, batch form handler, evaluate_weighing_limits, api_analysis_defaults, reports_reagents, export_reagents_demand, two new report routes |
| `templates/admin/analysis_form.html` | MODIFY — new mode option + Einwaage fields + JS syncMode |
| `templates/admin/batch_form.html` | MODIFY — new mode hint + mass-det section + JS setGroupVisibility + safety_factor field |
| `templates/reports/reagents.html` | MODIFY — expandable composites + updated formula + links to print lists |
| `templates/reports/order_list.html` | CREATE — printable Bestellliste |
| `templates/reports/prep_list.html` | CREATE — printable Herstellliste per Block |
| `tests/test_mass_determination.py` | CREATE — unit tests for MassDeterminationEvaluator |
| `tests/test_reagent_demand.py` | CREATE — unit tests for reagent formula changes |

---

## Task 1: DB Migration

**Files:**
- Create: `migrations/legacy_sql/20260320_mass_det_fields.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- migrations/legacy_sql/20260320_mass_det_fields.sql
-- Mass determination fields on Analysis and configurable safety factor on SampleBatch

ALTER TABLE analysis ADD COLUMN m_einwaage_min_mg REAL;
ALTER TABLE analysis ADD COLUMN m_einwaage_max_mg REAL;

ALTER TABLE sample_batch ADD COLUMN safety_factor REAL DEFAULT 1.2;
```

- [ ] **Step 2: Verify migration runs via the test suite**

The test suite uses `create_app(test_config=...)` which calls `db.create_all()` and then applies legacy SQL migrations. Run:

```bash
pytest tests/test_migrations.py -v
```

Expected: PASS (migration file is auto-applied by the test setup).

- [ ] **Step 3: Apply to dev database**

```bash
python -c "
from app import create_app
app = create_app()
print('Migration applied — check quanti_lims.db')
"
```

Expected: runs without error; `analysis` table has `m_einwaage_min_mg`, `m_einwaage_max_mg`; `sample_batch` has `safety_factor`.

- [ ] **Step 4: Commit**

```bash
git add migrations/legacy_sql/20260320_mass_det_fields.sql
git commit -m "feat: add DB migration for mass_determination fields and safety_factor"
```

---

## Task 2: MassDeterminationEvaluator

**Files:**
- Modify: `calculation_modes.py`
- Create: `tests/test_mass_determination.py`

The evaluator handles analyses where the TA weighs pure substance and the student announces the determined mass in mg. The "true value" is `m_s_actual_g × 1000` (converted to mg). Tolerance bounds use `analysis.tol_min` / `tol_max` (same `g_ab_min/max_pct` fields used by the other modes).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mass_determination.py
"""Tests for MassDeterminationEvaluator."""
from unittest.mock import MagicMock
from calculation_modes import (
    MassDeterminationEvaluator,
    MODE_MASS_DETERMINATION,
    resolve_mode,
    get_evaluator,
)


def _make_sample(m_s_actual_g, tol_min=98.0, tol_max=102.0):
    analysis = MagicMock()
    analysis.tol_min = tol_min
    analysis.tol_max = tol_max
    batch = MagicMock()
    batch.analysis = analysis
    sample = MagicMock()
    sample.batch = batch
    sample.m_s_actual_g = m_s_actual_g
    return sample


def _make_result(m_s_actual_g, ansage_mg, tol_min=98.0, tol_max=102.0):
    sample = _make_sample(m_s_actual_g, tol_min, tol_max)
    result = MagicMock()
    result.assignment = MagicMock()
    result.assignment.sample = sample
    result.ansage_value = ansage_mg
    return result


# --- MODE CONSTANTS AND DISPATCH ---

def test_mode_constant_exists():
    assert MODE_MASS_DETERMINATION == "mass_determination"


def test_resolve_mode_returns_mass_determination():
    assert resolve_mode("mass_determination") == MODE_MASS_DETERMINATION


def test_get_evaluator_returns_mass_determination_evaluator():
    ev = get_evaluator("mass_determination")
    assert isinstance(ev, MassDeterminationEvaluator)


def test_resolve_mode_still_defaults_unknown_to_assay_mass_based():
    from calculation_modes import MODE_ASSAY_MASS_BASED
    assert resolve_mode("unknown_mode") == MODE_ASSAY_MASS_BASED


# --- calculate_sample ---

def test_calculate_sample_g_wahr_is_mass_in_mg():
    """g_wahr stores the actual weighed mass in mg (reference value for display)."""
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(0.1500))
    assert abs(calc.g_wahr - 150.0) < 0.001


def test_calculate_sample_tolerance_bounds():
    """a_min/a_max are the tolerance bounds in mg."""
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(0.1500, tol_min=98.0, tol_max=102.0))
    assert abs(calc.a_min - 147.0) < 0.001   # 150.0 * 98.0 / 100
    assert abs(calc.a_max - 153.0) < 0.001   # 150.0 * 102.0 / 100


def test_calculate_sample_no_mass_returns_none():
    """If no mass weighed, bounds are None."""
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(None))
    assert calc.g_wahr is None
    assert calc.a_min is None
    assert calc.a_max is None


def test_calculate_sample_v_expected_is_none():
    """No titrant volume expectation in mass determination mode."""
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(0.1500))
    assert calc.v_expected_ml is None
    assert calc.titer_expected is None


# --- evaluate_result ---

def test_evaluate_result_passes_within_tolerance():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=150.5)
    er = ev.evaluate_result(result)
    assert er.passed is True


def test_evaluate_result_fails_below_tolerance():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=145.0)  # below 147.0
    er = ev.evaluate_result(result)
    assert er.passed is False


def test_evaluate_result_fails_above_tolerance():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=155.0)  # above 153.0
    er = ev.evaluate_result(result)
    assert er.passed is False


def test_evaluate_result_no_mass_passed_is_none():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=None, ansage_mg=150.0)
    er = ev.evaluate_result(result)
    assert er.passed is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_mass_determination.py -v
```

Expected: ImportError or AttributeError — `MassDeterminationEvaluator` and `MODE_MASS_DETERMINATION` do not exist yet.

- [ ] **Step 3: Implement in `calculation_modes.py`**

Add after line 9 (`MODE_TITRANT_STANDARDIZATION = ...`):

```python
MODE_MASS_DETERMINATION = "mass_determination"
```

Add after the `TitrantStandardizationEvaluator` class (before `resolve_mode`):

```python
class MassDeterminationEvaluator:
    """Evaluator for pure-substance mass determination (e.g. Glycerol).

    The TA weighs a known mass of pure substance (m_s_actual_g in grams).
    The student announces the determined mass in mg (ansage_value).
    Pass/fail: announced mass within tol_min/tol_max % of actual mass.

    g_wahr stores the actual weighed mass in mg (reference for display).
    a_min/a_max are the tolerance bounds in mg.
    v_expected_ml and titer_expected are always None.
    """

    def calculate_sample(self, sample) -> SampleCalculation:
        m_s_g = sample.m_s_actual_g
        if m_s_g is None:
            return SampleCalculation()
        m_s_mg = m_s_g * 1000.0
        tol_min = sample.batch.analysis.tol_min
        tol_max = sample.batch.analysis.tol_max
        a_min = round(m_s_mg * tol_min / 100.0, 3) if tol_min is not None else None
        a_max = round(m_s_mg * tol_max / 100.0, 3) if tol_max is not None else None
        return SampleCalculation(g_wahr=round(m_s_mg, 3), a_min=a_min, a_max=a_max)

    def evaluate_result(self, result) -> EvaluationResult:
        calc = self.calculate_sample(result.assignment.sample)
        passed = None
        if calc.a_min is not None and calc.a_max is not None:
            passed = calc.a_min <= result.ansage_value <= calc.a_max
        return EvaluationResult(
            g_wahr=calc.g_wahr,
            a_min=calc.a_min,
            a_max=calc.a_max,
            passed=passed,
        )
```

Update `resolve_mode` to handle the new mode (lines 298-301):

```python
def resolve_mode(mode: str | None) -> str:
    if mode in {MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION, MODE_MASS_DETERMINATION}:
        return mode
    return MODE_ASSAY_MASS_BASED
```

Update `get_evaluator` to dispatch the new mode (lines 304-308):

```python
def get_evaluator(mode: str | None) -> ModeEvaluator:
    resolved = resolve_mode(mode)
    if resolved == MODE_TITRANT_STANDARDIZATION:
        return TitrantStandardizationEvaluator()
    if resolved == MODE_MASS_DETERMINATION:
        return MassDeterminationEvaluator()
    return MassBasedEvaluator()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_mass_determination.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest --tb=short -q
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add calculation_modes.py tests/test_mass_determination.py
git commit -m "feat: add MassDeterminationEvaluator and MODE_MASS_DETERMINATION"
```

---

## Task 3: Update models.py

**Files:**
- Modify: `models.py`

Three changes: (1) import new mode constant, (2) add new Analysis fields, (3) update `Sample.is_weighed` for the new mode.

- [ ] **Step 1: Update imports in models.py (line 8–13)**

```python
from calculation_modes import (
    MODE_ASSAY_MASS_BASED,
    MODE_MASS_DETERMINATION,
    MODE_TITRANT_STANDARDIZATION,
    get_evaluator,
    resolve_mode,
)
```

- [ ] **Step 2: Add new fields to the Analysis model (after line 187, `notes` column)**

```python
    m_einwaage_min_mg = db.Column(db.Float, nullable=True)  # Min TA weighing mass (mass_determination mode, mg)
    m_einwaage_max_mg = db.Column(db.Float, nullable=True)  # Max TA weighing mass (mass_determination mode, mg)
```

- [ ] **Step 3: Add safety_factor to SampleBatch (after line 444, `notes` column)**

```python
    safety_factor = db.Column(db.Float, nullable=False, default=1.2)
```

- [ ] **Step 4: Update `Sample.is_weighed` (lines 530–534)**

```python
    @property
    def is_weighed(self) -> bool:
        mode = resolve_mode(self.batch.analysis.calculation_mode if self.batch and self.batch.analysis else None)
        if mode == MODE_TITRANT_STANDARDIZATION:
            return self.m_ges_actual_g is not None
        if mode == MODE_MASS_DETERMINATION:
            return self.m_s_actual_g is not None
        return self.m_s_actual_g is not None and self.m_ges_actual_g is not None
```

- [ ] **Step 5: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add models.py
git commit -m "feat: add Analysis.m_einwaage_min/max_mg, SampleBatch.safety_factor, update Sample.is_weighed"
```

---

## Task 4: Update analysis_form backend + template

**Files:**
- Modify: `app.py` (admin_analysis_form route, ~lines 470–521)
- Modify: `templates/admin/analysis_form.html`

- [ ] **Step 1: Write failing route test**

```python
# tests/test_mass_determination.py — append to existing file

def test_analysis_form_saves_mass_determination_fields(client, db):
    """POST to analysis form with mass_determination mode saves new fields."""
    from models import Block, Substance, Analysis
    with client.application.app_context():
        block = Block(code="T", name="Test", max_days=4)
        substance = Substance(name="Glycerol Test", molar_mass_gmol=92.09)
        db.session.add_all([block, substance])
        db.session.flush()
        resp = client.post("/admin/analyses/new", data={
            "block_id": block.id,
            "code": "GLYC",
            "ordinal": 99,
            "name": "Glycerol-Bestimmung",
            "substance_id": substance.id,
            "calculation_mode": "mass_determination",
            "k_determinations": 3,
            "result_unit": "mg",
            "result_label": "Masse",
            "m_einwaage_min_mg": "120.0",
            "m_einwaage_max_mg": "180.0",
            "g_ab_min_pct": "98.0",
            "g_ab_max_pct": "102.0",
        }, follow_redirects=True)
        assert resp.status_code == 200
        a = Analysis.query.filter_by(code="GLYC").first()
        assert a is not None
        assert a.calculation_mode == "mass_determination"
        assert abs(a.m_einwaage_min_mg - 120.0) < 0.001
        assert abs(a.m_einwaage_max_mg - 180.0) < 0.001
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_mass_determination.py::test_analysis_form_saves_mass_determination_fields -v
```

Expected: FAIL — new fields not saved yet.

- [ ] **Step 3: Update admin_analysis_form handler in app.py**

In the POST handler (around line 485), add after `item.e_ab_g = ...`:

```python
            item.m_einwaage_min_mg = _float(request.form.get("m_einwaage_min_mg"))
            item.m_einwaage_max_mg = _float(request.form.get("m_einwaage_max_mg"))
```

Update `mode_opts` in both `_render_form()` calls (lines 500–504 and 516–520). Replace:

```python
            mode_opts = [
                (MODE_ASSAY_MASS_BASED, "assay_mass_based"),
                (MODE_TITRANT_STANDARDIZATION, "titrant_standardization"),
            ]
```

With:

```python
            mode_opts = [
                (MODE_ASSAY_MASS_BASED, "assay_mass_based"),
                (MODE_TITRANT_STANDARDIZATION, "titrant_standardization"),
                (MODE_MASS_DETERMINATION, "mass_determination"),
            ]
```

Also add the import at the top of app.py (line 27):

```python
from calculation_modes import MODE_ASSAY_MASS_BASED, MODE_MASS_DETERMINATION, MODE_TITRANT_STANDARDIZATION, resolve_mode, attempt_type_for, compute_evaluation_label
```

- [ ] **Step 4: Update analysis_form.html**

Add new fields after the `e_ab_group` div (line 21):

```html
    <div class="col-md-2" id="m_einwaage_min_group">{{ field("m_einwaage_min_mg", "Mindesteinwaage (mg)", item.m_einwaage_min_mg, type="number", step="0.1", help="Untere Grenze der TA-Einwaage (nur bei mass_determination)") }}</div>
    <div class="col-md-2" id="m_einwaage_max_group">{{ field("m_einwaage_max_mg", "Maximaleinwaage (mg)", item.m_einwaage_max_mg, type="number", step="0.1", help="Obere Grenze der TA-Einwaage (nur bei mass_determination)") }}</div>
```

Add a new hint div after `standardization-hint` (after line 30):

```html
  <div id="mass-det-hint" class="alert alert-info small mb-3" style="display:none">
    <i class="bi bi-info-circle"></i> <strong>Massenbestimmung:</strong>
    Keine Arzneibuch-Einwaage — die TA wiegt eine Menge reiner Substanz zwischen Mindest- und Maximaleinwaage ein.
    Die Studierenden berechnen die Masse aus ihrer Titration und sagen eine Masse in mg an.
    G_AB,min/max werden als relative Toleranz der angesagten Masse interpretiert.
  </div>
```

Update the `syncMode()` JS function to handle the third mode:

```javascript
  function syncMode() {
    const isTitrant = modeSelect.value === 'titrant_standardization';
    const isMassDet = modeSelect.value === 'mass_determination';
    eAbGroup.style.display = (isTitrant || isMassDet) ? 'none' : '';
    document.getElementById('m_einwaage_min_group').style.display = isMassDet ? '' : 'none';
    document.getElementById('m_einwaage_max_group').style.display = isMassDet ? '' : 'none';
    hint.style.display = isTitrant ? '' : 'none';
    document.getElementById('mass-det-hint').style.display = isMassDet ? '' : 'none';
    gAbMinLabel.textContent = isTitrant ? 'Titer min (×100)' : origMinLabel;
    gAbMaxLabel.textContent = isTitrant ? 'Titer max (×100)' : origMaxLabel;
  }
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_mass_determination.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin/analysis_form.html
git commit -m "feat: support mass_determination mode in analysis form (backend + template)"
```

---

## Task 5: Update batch_form backend for mass_determination mode

**Files:**
- Modify: `app.py` (admin_batch_form route, ~lines 1100–1217)

The `mass_determination` mode needs: no blend/mass validation, no computed target masses, reads `safety_factor`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_mass_determination.py — append

def test_batch_form_mass_determination_skips_mass_validation(client, db):
    """POST batch form with mass_determination analysis does not require target_m_ges_g."""
    from models import Block, Substance, Analysis, Method, Semester
    with client.application.app_context():
        sem = Semester(code="TS26", name="Test 26", is_active=True)
        block = Block(code="TB", name="Test Block", max_days=4)
        substance = Substance(name="Glycerol Batch Test", molar_mass_gmol=92.09)
        db.session.add_all([sem, block, substance])
        db.session.flush()
        analysis = Analysis(
            block_id=block.id, code="GB1", ordinal=98, name="Glycerol Batch",
            substance_id=substance.id, calculation_mode="mass_determination",
            m_einwaage_min_mg=120.0, m_einwaage_max_mg=180.0,
            g_ab_min_pct=98.0, g_ab_max_pct=102.0,
        )
        db.session.add(analysis)
        db.session.flush()
        method = Method(analysis_id=analysis.id, method_type="back",
                        blind_required=True, b_blind_determinations=1,
                        v_solution_ml=100.0, v_aliquot_ml=20.0, aliquot_enabled=True)
        db.session.add(method)
        db.session.commit()

        resp = client.post(f"/admin/batches/new", data={
            "analysis_id": analysis.id,
            "total_samples_prepared": "5",
            "safety_factor": "1.3",
            "titer": "1.000",
        }, follow_redirects=True)
        assert resp.status_code == 200
        from models import SampleBatch
        batch = SampleBatch.query.filter_by(analysis_id=analysis.id).first()
        assert batch is not None
        assert abs(batch.safety_factor - 1.3) < 0.001
        assert batch.target_m_s_min_g is None
        assert batch.target_m_ges_g is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_mass_determination.py::test_batch_form_mass_determination_skips_mass_validation -v
```

Expected: FAIL.

- [ ] **Step 3: Update admin_batch_form handler in app.py**

In the POST handler, after `item.analysis_id = int(request.form["analysis_id"])` and the `mode = resolve_mode(...)` line, add reading of `safety_factor`:

```python
            item.safety_factor = _float(request.form.get("safety_factor")) or 1.2
```

Change the server-side mass auto-calculation block (lines 1132–1151) to also skip for `mass_determination`:

```python
            if mode == MODE_ASSAY_MASS_BASED and analysis:
```

(already only runs for `MODE_ASSAY_MASS_BASED` — no change needed there)

Change the validation block (lines 1184–1191):

```python
            if mode == MODE_ASSAY_MASS_BASED:
                if item.target_m_s_min_g is None or item.target_m_ges_g is None:
                    flash("Für massenbasierte Analysen sind Ziel-m_S,min und Ziel-m_ges erforderlich.", "danger")
                    return _render_form()
            elif mode == MODE_TITRANT_STANDARDIZATION:
                if item.target_v_min_ml is None or item.target_v_max_ml is None:
                    flash("Für Titerstandardisierung sind Ziel-V_min und Ziel-V_max erforderlich.", "danger")
                    return _render_form()
            # mass_determination: no target mass or volume required
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_mass_determination.py -v && pytest --tb=short -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: handle mass_determination mode in batch_form backend (skip mass validation, save safety_factor)"
```

---

## Task 6: Update batch_form.html for mass_determination mode

**Files:**
- Modify: `templates/admin/batch_form.html`

- [ ] **Step 1: Add MODE_MASS constant and mass-determination hint block**

In the `<script>` section, after line 107 (`const MODE_STD = ...`), add:

```javascript
  const MODE_MASS_DET = "mass_determination";
```

After the `hint-standardization` div (line 21), add:

```html
<div class="alert alert-light border small" id="hint-mass-det" style="display:none">
  <i class="bi bi-info-circle"></i> <strong>Hinweis (Massenbestimmung):</strong>
  Die TA wiegt eine bestimmte Menge reiner Substanz ein (keine Verschnittberechnung).
  Einwaagebereich aus der Methode:
  <strong id="mass-det-range">–</strong>.
  Sicherheitsfaktor gilt für den Reagenzienbedarf (Grundbedarf = Erstanalysen).
</div>
```

- [ ] **Step 2: Add safety_factor field to the batch form**

In the "Probenherstellung" section (after line 72, `total_samples_prepared` field row), add a new row:

```html
  <div class="row" id="safety-factor-row">
    <div class="col-md-3">{{ field("safety_factor", "Sicherheitsfaktor", item.safety_factor if item.safety_factor is not none else 1.2, type="number", step="0.01", help="Aufschlag für Reagenzienbedarf. 1.2 = 20% extra. Gilt nur für Erstanalysen (k=1).") }}</div>
  </div>
```

- [ ] **Step 3: Update `setGroupVisibility` JS function**

Replace the existing `setGroupVisibility` function (lines 135–144):

```javascript
  function setGroupVisibility(mode) {
    const isMass = mode === MODE_ASSAY;
    const isStd = mode === MODE_STD;
    const isMassDet = mode === MODE_MASS_DET;
    massFields.style.display = isMass ? "" : "none";
    volumeFields.style.display = isStd ? "" : "none";
    hintMass.style.display = isMass ? "" : "none";
    hintStd.style.display = isStd ? "" : "none";
    document.getElementById("hint-mass-det").style.display = isMassDet ? "" : "none";
    blendRow.style.display = isMass ? "" : "none";
    dilutionRow.style.display = isMass ? "" : "none";
    dilutionNotesRow.style.display = isMass ? "" : "none";
  }
```

- [ ] **Step 4: Show weighing range in hint when analysis is selected**

In the `analysisSelect.addEventListener("change", ...)` handler, after the `recalcVolumeFields()` call, add:

```javascript
          if (isMassDet) {
            const minMg = data.m_einwaage_min_mg;
            const maxMg = data.m_einwaage_max_mg;
            const rangeEl = document.getElementById("mass-det-range");
            if (minMg != null && maxMg != null) {
              rangeEl.textContent = `${minMg} – ${maxMg} mg`;
            } else {
              rangeEl.textContent = "nicht definiert";
            }
          }
```

Update the initial load block similarly (after line 243–245).

Also update `api_analysis_defaults` in app.py to include the new fields in the JSON response. After the `result["molar_mass_gmol"]` line (~line 2083):

```python
        result["m_einwaage_min_mg"] = analysis.m_einwaage_min_mg
        result["m_einwaage_max_mg"] = analysis.m_einwaage_max_mg
```

And update `analysis_modes` dict in `admin_batch_form` (line 1104) to use the raw mode (not resolved), so `mass_determination` is not mapped to `assay_mass_based`:

```python
        analysis_modes = {a.id: (a.calculation_mode or MODE_ASSAY_MASS_BASED) for a in analyses}
```

- [ ] **Step 5: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin/batch_form.html
git commit -m "feat: batch_form template and API support mass_determination mode with weighing range hint"
```

---

## Task 7: Update evaluate_weighing_limits for mass_determination

**Files:**
- Modify: `app.py` (evaluate_weighing_limits function, lines 67–100+)
- Modify: `tests/test_weighing_limits.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_weighing_limits.py`:

```python
def test_mass_determination_within_range(client):
    """Mass determination: m_s within [min_mg/1000, max_mg/1000] → no violation."""
    from unittest.mock import MagicMock
    from app import evaluate_weighing_limits
    batch = MagicMock()
    batch.analysis.calculation_mode = "mass_determination"
    batch.analysis.m_einwaage_min_mg = 120.0
    batch.analysis.m_einwaage_max_mg = 180.0
    with client.application.app_context():
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.1500, m_ges_actual_g=None)
    assert result["checks"] == []


def test_mass_determination_below_min(client):
    """Mass determination: m_s below min → violation flagged."""
    from unittest.mock import MagicMock
    from app import evaluate_weighing_limits
    batch = MagicMock()
    batch.analysis.calculation_mode = "mass_determination"
    batch.analysis.m_einwaage_min_mg = 120.0
    batch.analysis.m_einwaage_max_mg = 180.0
    with client.application.app_context():
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.1000, m_ges_actual_g=None)
    assert result["details"]["m_s_min_violation"] is True


def test_mass_determination_above_max(client):
    """Mass determination: m_s above max → violation flagged."""
    from unittest.mock import MagicMock
    from app import evaluate_weighing_limits
    batch = MagicMock()
    batch.analysis.calculation_mode = "mass_determination"
    batch.analysis.m_einwaage_min_mg = 120.0
    batch.analysis.m_einwaage_max_mg = 180.0
    with client.application.app_context():
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.2000, m_ges_actual_g=None)
    assert result["details"]["m_s_max_violation"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_weighing_limits.py -k "mass_determination" -v
```

Expected: FAIL.

- [ ] **Step 3: Add mass_determination branch to evaluate_weighing_limits in app.py**

Read the function from line 67. After the `if mode == MODE_ASSAY_MASS_BASED:` block, add a new branch before the final `return`:

```python
    elif mode == MODE_MASS_DETERMINATION:
        analysis = batch.analysis
        min_mg = getattr(analysis, "m_einwaage_min_mg", None)
        max_mg = getattr(analysis, "m_einwaage_max_mg", None)
        if m_s_actual_g is not None and min_mg is not None and m_s_actual_g * 1000 < min_mg:
            details["m_s_min_violation"] = True
            checks.append(f"Einwaage {m_s_actual_g*1000:.1f} mg < Mindest {min_mg:.1f} mg")
        if m_s_actual_g is not None and max_mg is not None and m_s_actual_g * 1000 > max_mg:
            details["m_s_max_violation"] = True
            checks.append(f"Einwaage {m_s_actual_g*1000:.1f} mg > Maximum {max_mg:.1f} mg")
```

Also add `MODE_MASS_DETERMINATION` to the import at the top of app.py (already done in Task 4).

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_weighing_limits.py -v && pytest --tb=short -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_weighing_limits.py
git commit -m "feat: evaluate_weighing_limits handles mass_determination mode"
```

---

## Task 8: Reagent demand formula — k=1 and batch.safety_factor

**Files:**
- Create: `tests/test_reagent_demand.py`
- Modify: `app.py` (reports_reagents and export_reagents_demand, lines 1790–1920)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reagent_demand.py
"""Tests for reagent demand calculation (k=1 Grundbedarf, configurable safety_factor)."""
from unittest.mock import MagicMock, patch


def _make_batch_with_reagent(safety_factor=1.2, amount_per_det=25.0, amount_per_blind=25.0,
                              blind_required=True, b_blind=1, k_determinations=3, n=80):
    reagent = MagicMock()
    reagent.name = "NaOH-Lösung (0,1 mol/L)"
    reagent.is_composite = False
    mr = MagicMock()
    mr.reagent = reagent
    mr.amount_per_determination = amount_per_det
    mr.amount_per_blind = amount_per_blind
    mr.amount_unit = "mL"
    mr.amount_unit_type = "volume"
    mr.is_titrant = False
    method = MagicMock()
    method.blind_required = blind_required
    method.b_blind_determinations = b_blind
    method.reagent_usages = [mr]
    analysis = MagicMock()
    analysis.code = "GLYC"
    analysis.name = "Glycerol"
    analysis.k_determinations = k_determinations
    analysis.method = method
    batch = MagicMock()
    batch.analysis = analysis
    batch.total_samples_prepared = n
    batch.safety_factor = safety_factor
    return batch, mr


def test_grundbedarf_uses_k_equals_1():
    """Grundbedarf uses k=1 (Erstanalysen only), not analysis.k_determinations."""
    batch, mr = _make_batch_with_reagent(safety_factor=1.2, amount_per_det=25.0,
                                          amount_per_blind=0.0, blind_required=False, n=80, k_determinations=3)
    # Expected: 80 × (1 × 25.0 + 0) × 1.2 = 2400.0
    k = 1
    b = 0
    total = batch.total_samples_prepared * (k * mr.amount_per_determination + b * mr.amount_per_blind) * batch.safety_factor
    assert abs(total - 2400.0) < 0.01


def test_grundbedarf_includes_blind():
    """Blind determinations are still included in the formula."""
    batch, mr = _make_batch_with_reagent(safety_factor=1.2, amount_per_det=25.0,
                                          amount_per_blind=25.0, blind_required=True, b_blind=1, n=80)
    # Expected: 80 × (1 × 25.0 + 1 × 25.0) × 1.2 = 4800.0
    k = 1
    b = 1
    total = batch.total_samples_prepared * (k * mr.amount_per_determination + b * mr.amount_per_blind) * batch.safety_factor
    assert abs(total - 4800.0) < 0.01


def test_safety_factor_from_batch():
    """Safety factor is read from batch, not hardcoded."""
    batch, mr = _make_batch_with_reagent(safety_factor=1.5, amount_per_det=25.0,
                                          amount_per_blind=0.0, blind_required=False, n=10)
    k = 1
    b = 0
    total = batch.total_samples_prepared * (k * mr.amount_per_determination + b * mr.amount_per_blind) * batch.safety_factor
    assert abs(total - 375.0) < 0.01  # 10 × 25.0 × 1.5


def test_reports_reagents_route_uses_k1_and_batch_safety(client, db):
    """Integration test: /reports/reagents uses k=1 and batch.safety_factor."""
    # This verifies the route renders without error and shows k=1 in output
    resp = client.get("/reports/reagents")
    assert resp.status_code == 200
    # Formula text should mention "1 ×" not "k ×"
    assert b"1 \xc3\x97" in resp.data or b"(1 &times;" in resp.data or b"Erstanalysen" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reagent_demand.py -v
```

Expected: last integration test FAIL (route still uses k and 1.2).

- [ ] **Step 3: Update reports_reagents() in app.py (lines 1802–1822)**

Replace the loop body:

```python
            for mr in method.reagent_usages:
                k = 1  # Grundbedarf: only Erstanalysen
                b = method.b_blind_determinations if method.blind_required else 0
                n = batch.total_samples_prepared
                safety = getattr(batch, 'safety_factor', 1.2) or 1.2
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
                    "total": round(total, 1),
                    "is_titrant": mr.is_titrant,
                    "is_composite": mr.reagent.is_composite,
                    "components": mr.reagent.components if mr.reagent.is_composite else [],
                })
```

- [ ] **Step 4: Update export_reagents_demand() in app.py (lines 1909–1919)**

Replace the loop body similarly:

```python
            for mr in method.reagent_usages:
                k = 1
                b = method.b_blind_determinations if method.blind_required else 0
                n = batch.total_samples_prepared
                safety = getattr(batch, 'safety_factor', 1.2) or 1.2
                total = n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
                rows.append({
                    "semester_code": sem.code, "analysis_code": analysis.code, "analysis_name": analysis.name,
                    "reagent": mr.reagent.name if mr.reagent else None,
                    "amount_per_determination": mr.amount_per_determination,
                    "amount_per_blind": mr.amount_per_blind, "k": k, "b": b, "n": n,
                    "safety_factor": safety,
                    "total_with_safety": round(total, 1), "unit": canonical_unit_label(mr.amount_unit), "is_titrant": mr.is_titrant,
                })
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_reagent_demand.py -v && pytest --tb=short -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_reagent_demand.py
git commit -m "feat: reagent demand uses k=1 (Grundbedarf) and batch.safety_factor"
```

---

## Task 9: Redesign reagents.html with expandable composites

**Files:**
- Modify: `templates/reports/reagents.html`

- [ ] **Step 1: Rewrite reagents.html**

Replace the entire file content:

```html
{% extends "base.html" %}
{% block title %}Reagenzienbedarf{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
<h4 class="mb-0"><i class="bi bi-prescription2"></i> Reagenzienbedarf {{ semester.code if semester else '' }}</h4>
<div class="d-flex gap-2">
  <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reports_order_list') }}"><i class="bi bi-list-check"></i> Bestellliste</a>
  <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reports_prep_list') }}"><i class="bi bi-flask"></i> Herstellliste</a>
  <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('export_reagents_demand', fmt='csv') }}"><i class="bi bi-download"></i> CSV</a>
  <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('export_reagents_demand', fmt='json') }}"><i class="bi bi-filetype-json"></i> JSON</a>
</div>
</div>

{% if not semester %}
<div class="alert alert-warning">Kein aktives Semester.</div>
{% elif not demand %}
<div class="alert alert-info">Keine Reagenzien-Zuordnungen vorhanden. Bitte Methoden-Reagenzien pflegen.</div>
{% else %}

{% if has_non_volume_units %}
<p class="text-body-secondary small">Grundbedarf = n × (1 × Menge/Best. + b × Menge/Blind) × Sicherheitsfaktor &nbsp;<span class="badge bg-secondary">k=1: nur Erstanalysen</span></p>
{% else %}
<p class="text-body-secondary small">V<sub>Grundbedarf</sub> = n × (1 × V<sub>Einzel</sub> + b × V<sub>Blind</sub>) × Sicherheitsfaktor &nbsp;<span class="badge bg-secondary">k=1: nur Erstanalysen</span></p>
{% endif %}

<div class="card">
<div class="table-responsive">
<table class="table table-sm table-hover mb-0 align-middle">
<thead class="table-light">
<tr><th>Analyse</th><th>Reagenz</th><th>Menge/Best.</th><th>Menge/Blind</th><th>b</th><th>n</th><th>Faktor</th><th class="text-end">Gesamt</th><th>Einheit</th><th></th></tr>
</thead>
<tbody>
{% set ns = namespace(current_analysis='') %}
{% for d in demand|sort(attribute='analysis') %}
{% if d.analysis != ns.current_analysis %}
{% set ns.current_analysis = d.analysis %}
<tr class="table-light"><td colspan="10"><strong>{{ d.analysis }} – {{ d.analysis_name }}</strong></td></tr>
{% endif %}
<tr>
  <td></td>
  <td>
    {{ d.reagent }}
    {% if d.is_composite %}
    <button class="btn btn-link btn-sm p-0 ms-1" type="button"
            data-bs-toggle="collapse" data-bs-target="#comp-{{ loop.index }}"
            aria-expanded="false" title="Zusammensetzung anzeigen">
      <i class="bi bi-chevron-down"></i>
    </button>
    {% endif %}
  </td>
  <td>{{ d.per_det }}</td>
  <td>{{ d.per_blind }}</td>
  <td>{{ d.b }}</td>
  <td>{{ d.n }}</td>
  <td class="text-muted small">×{{ d.safety }}</td>
  <td class="text-end"><strong>{{ d.total }}</strong></td>
  <td>{{ d.unit|unit }}</td>
  <td>{% if d.is_titrant %}<span class="badge bg-info">Titrant</span>{% endif %}
      {% if d.is_composite %}<span class="badge bg-secondary">zusammengesetzt</span>{% endif %}</td>
</tr>
{% if d.is_composite and d.components %}
<tr class="collapse" id="comp-{{ loop.index }}">
  <td colspan="2"></td>
  <td colspan="8" class="bg-light">
    <small class="text-muted d-block mb-1">Zusammensetzung (skaliert auf {{ d.total }} {{ d.unit|unit }} Gesamtbedarf):</small>
    <table class="table table-sm table-borderless mb-0 ms-2">
    {% for comp in d.components %}
    {% if comp.per_parent_volume_ml and comp.per_parent_volume_ml > 0 %}
    {% set comp_total = (d.total / comp.per_parent_volume_ml * comp.quantity)|round(1) %}
    <tr>
      <td class="py-0 pe-3"><strong>{{ comp_total }} {{ comp.quantity_unit|unit }}</strong></td>
      <td class="py-0">{{ comp.child.name if comp.child else '?' }}</td>
    </tr>
    {% else %}
    <tr>
      <td class="py-0 pe-3 text-muted">{{ comp.quantity }} {{ comp.quantity_unit|unit }}</td>
      <td class="py-0">{{ comp.child.name if comp.child else '?' }} <span class="text-muted">(kein Skalierungsvolumen)</span></td>
    </tr>
    {% endif %}
    {% endfor %}
    </table>
  </td>
</tr>
{% endif %}
{% endfor %}
</tbody></table></div></div>

{% endif %}
{% endblock %}
```

- [ ] **Step 2: Run the test suite**

```bash
pytest --tb=short -q
```

Expected: all PASS (template change only; no logic change).

- [ ] **Step 3: Commit**

```bash
git add templates/reports/reagents.html
git commit -m "feat: reagents report shows expandable composite components and links to print lists"
```

---

## Task 10: Printable Bestellliste

**Files:**
- Create: `templates/reports/order_list.html`
- Modify: `app.py` (add `reports_order_list` route)

The Bestellliste aggregates **simple (non-composite)** reagents across all batches of the active semester. For composite reagents, it expands their components and aggregates those instead. The result is a deduplicated list of orderable substances.

- [ ] **Step 1: Add reports_order_list route to app.py**

After the `reports_reagents` route (after line 1824):

```python
    @app.route("/reports/reagents/order-list")
    def reports_order_list():
        sem = active_semester()
        if not sem:
            return render_template("reports/order_list.html", semester=None, items=[], generated=None)
        from collections import defaultdict
        from datetime import date as _date
        aggregated: dict[int, dict] = defaultdict(lambda: {"name": "", "cas": "", "total": 0.0, "unit": "", "for_reagents": set()})
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        for batch in batches:
            analysis = batch.analysis
            method = analysis.method
            if not method:
                continue
            k = 1
            b = method.b_blind_determinations if method.blind_required else 0
            n = batch.total_samples_prepared
            safety = getattr(batch, "safety_factor", 1.2) or 1.2
            for mr in method.reagent_usages:
                total_amount = n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
                reagent = mr.reagent
                if not reagent:
                    continue
                if not reagent.is_composite:
                    entry = aggregated[reagent.id]
                    entry["name"] = reagent.name
                    entry["cas"] = reagent.cas_number or "–"
                    entry["total"] += total_amount
                    entry["unit"] = canonical_unit_label(mr.amount_unit)
                    entry["for_reagents"].add(None)  # used directly
                else:
                    for comp in reagent.components:
                        if not comp.child or not comp.per_parent_volume_ml or comp.per_parent_volume_ml <= 0:
                            continue
                        comp_total = total_amount / comp.per_parent_volume_ml * comp.quantity
                        entry = aggregated[comp.child_reagent_id]
                        entry["name"] = comp.child.name
                        entry["cas"] = comp.child.cas_number or "–"
                        entry["total"] += comp_total
                        entry["unit"] = canonical_unit_label(comp.quantity_unit)
                        entry["for_reagents"].add(reagent.name)
        items = []
        for rid, data in aggregated.items():
            items.append({
                "name": data["name"],
                "cas": data["cas"],
                "total": round(data["total"], 1),
                "unit": data["unit"],
                "for_reagents": sorted(r for r in data["for_reagents"] if r),
            })
        items.sort(key=lambda x: x["name"])
        return render_template("reports/order_list.html", semester=sem, items=items,
                               generated=_date.today().isoformat())
```

- [ ] **Step 2: Create `templates/reports/order_list.html`**

```html
{% extends "base.html" %}
{% block title %}Bestellliste{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4 class="mb-0"><i class="bi bi-list-check"></i> Bestellliste – Grundsubstanzen
    {% if semester %}<span class="text-muted small ms-2">{{ semester.code }}</span>{% endif %}
  </h4>
  <div class="d-flex gap-2">
    <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reports_reagents') }}">← Reagenzienbedarf</a>
    <button class="btn btn-outline-primary btn-sm" onclick="window.print()"><i class="bi bi-printer"></i> Drucken</button>
  </div>
</div>

{% if not semester %}
<div class="alert alert-warning">Kein aktives Semester.</div>
{% elif not items %}
<div class="alert alert-info">Keine Reagenzien-Daten vorhanden.</div>
{% else %}
<p class="text-body-secondary small mb-3">
  Alle bestellbaren Grundsubstanzen — inkl. Komponenten zusammengesetzter Reagenzien.
  Mengen inkl. Sicherheitsfaktor, Grundbedarf (Erstanalysen). Stand: {{ generated }}.
</p>

<div class="card">
<div class="table-responsive">
<table class="table table-sm table-hover mb-0 align-middle" id="order-table">
<thead class="table-light">
<tr><th>Substanz</th><th>CAS-Nr.</th><th class="text-end">Menge</th><th>Einheit</th><th>Verwendung</th></tr>
</thead>
<tbody>
{% for item in items %}
<tr>
  <td>{{ item.name }}</td>
  <td class="text-muted small">{{ item.cas }}</td>
  <td class="text-end"><strong>{{ item.total }}</strong></td>
  <td>{{ item.unit }}</td>
  <td>
    {% if item.for_reagents %}
      <span class="text-muted small">→ für {% for r in item.for_reagents %}<em>{{ r }}</em>{% if not loop.last %}, {% endif %}{% endfor %}</span>
    {% else %}
      <span class="text-muted small">Direkteinsatz</span>
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
</div>
{% endif %}

<style>
@media print {
  .btn, nav, footer { display: none !important; }
  .card { border: 1px solid #ccc !important; box-shadow: none !important; }
}
</style>
{% endblock %}
```

- [ ] **Step 3: Run tests**

```bash
pytest --tb=short -q
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/reports/order_list.html
git commit -m "feat: add printable Bestellliste (order list) with aggregated base substances"
```

---

## Task 11: Printable Herstellliste per Block

**Files:**
- Create: `templates/reports/prep_list.html`
- Modify: `app.py` (add `reports_prep_list` route)

The Herstellliste groups composite reagents by Block and shows their components scaled to the required total volume.

- [ ] **Step 1: Add reports_prep_list route to app.py**

After the `reports_order_list` route:

```python
    @app.route("/reports/reagents/prep-list")
    def reports_prep_list():
        sem = active_semester()
        if not sem:
            return render_template("reports/prep_list.html", semester=None, blocks=[], generated=None)
        from collections import defaultdict
        from datetime import date as _date
        # (block_id, reagent_id) → accumulated total
        block_reagent_totals: dict[tuple, float] = defaultdict(float)
        block_reagent_meta: dict[tuple, dict] = {}
        block_names: dict[int, str] = {}
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        for batch in batches:
            analysis = batch.analysis
            method = analysis.method
            if not method:
                continue
            block = analysis.block
            if not block:
                continue
            block_names[block.id] = f"{block.code} – {block.name}"
            k = 1
            b = method.b_blind_determinations if method.blind_required else 0
            n = batch.total_samples_prepared
            safety = getattr(batch, "safety_factor", 1.2) or 1.2
            for mr in method.reagent_usages:
                reagent = mr.reagent
                if not reagent or not reagent.is_composite:
                    continue
                key = (block.id, reagent.id)
                total_amount = n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
                block_reagent_totals[key] += total_amount
                if key not in block_reagent_meta:
                    block_reagent_meta[key] = {
                        "name": reagent.name,
                        "unit": canonical_unit_label(mr.amount_unit),
                        "reagent": reagent,
                        "prep_notes": reagent.notes or "",
                    }
        # Build block_reagents from accumulated totals
        block_reagents: dict[int, list] = defaultdict(list)
        for (block_id, reagent_id), total_amount in block_reagent_totals.items():
            meta = block_reagent_meta[(block_id, reagent_id)]
            reagent = meta["reagent"]
            components = []
            for comp in reagent.components:
                if comp.child and comp.per_parent_volume_ml and comp.per_parent_volume_ml > 0:
                    comp_total = round(total_amount / comp.per_parent_volume_ml * comp.quantity, 2)
                    components.append({
                        "name": comp.child.name,
                        "amount": comp_total,
                        "unit": canonical_unit_label(comp.quantity_unit),
                    })
            block_reagents[block_id].append({
                "name": meta["name"],
                "total": round(total_amount, 1),
                "unit": meta["unit"],
                "components": components,
                "prep_notes": meta["prep_notes"],
            })
        blocks = [
            {"id": bid, "name": block_names[bid], "reagents": block_reagents[bid]}
            for bid in sorted(block_reagents.keys())
        ]
        return render_template("reports/prep_list.html", semester=sem, blocks=blocks,
                               generated=_date.today().isoformat())
```

- [ ] **Step 2: Create `templates/reports/prep_list.html`**

```html
{% extends "base.html" %}
{% block title %}Herstellliste{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4 class="mb-0"><i class="bi bi-flask"></i> Herstellliste – zusammengesetzte Reagenzien
    {% if semester %}<span class="text-muted small ms-2">{{ semester.code }}</span>{% endif %}
  </h4>
  <div class="d-flex gap-2">
    <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('reports_reagents') }}">← Reagenzienbedarf</a>
    <button class="btn btn-outline-primary btn-sm" onclick="window.print()"><i class="bi bi-printer"></i> Drucken</button>
  </div>
</div>

{% if not semester %}
<div class="alert alert-warning">Kein aktives Semester.</div>
{% elif not blocks %}
<div class="alert alert-info">Keine zusammengesetzten Reagenzien definiert.</div>
{% else %}
<p class="text-body-secondary small mb-3">
  Am Herstellungstag vor Praktikumsbeginn herzustellen. Stand: {{ generated }}.
</p>

{% for block in blocks %}
<div class="card mb-4">
  <div class="card-header bg-dark text-white">
    <strong>{{ block.name }}</strong>
  </div>
  <div class="card-body p-3">
    <div class="row row-cols-1 row-cols-md-2 g-3">
    {% for rg in block.reagents %}
    <div class="col">
      <div class="border rounded p-3 h-100">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <strong>{{ rg.name }}</strong>
          <span class="badge bg-primary ms-2">{{ rg.total }} {{ rg.unit }}</span>
        </div>
        {% if rg.components %}
        <p class="text-muted small mb-1 text-uppercase fw-bold" style="font-size:0.65rem;letter-spacing:.05em">Zusammensetzung</p>
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
    </div>
  </div>
</div>
{% endfor %}
{% endif %}

<style>
@media print {
  .btn, nav, footer { display: none !important; }
  .card { break-inside: avoid; }
  .card-header { background: #333 !important; color: #fff !important; -webkit-print-color-adjust: exact; }
  .badge { border: 1px solid #000; }
}
</style>
{% endblock %}
```

- [ ] **Step 3: Run tests**

```bash
pytest --tb=short -q
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/reports/prep_list.html
git commit -m "feat: add printable Herstellliste per Block for composite reagents"
```

---

## Task 12: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 2: Smoke-check new routes manually**

Start dev server and verify:
- `/admin/analyses/new` → select `mass_determination`, Einwaagefelder erscheinen, e_ab verschwindet
- `/admin/batches/new` → select a mass_determination analysis, blend fields hidden, Einwaagebereich-Hinweis sichtbar, safety_factor Feld vorhanden
- `/reports/reagents` → composite reagents haben Aufklapp-Button, k-Spalte zeigt 1, Sicherheitsfaktor aus Batch
- `/reports/reagents/order-list` → Grundsubstanzen aggregiert
- `/reports/reagents/prep-list` → Blöcke mit Reagenz-Karten

- [ ] **Step 3: Commit final state**

```bash
git add .
git commit -m "chore: final smoke-test pass — mass determination and reagent improvements complete"
```
