# Reported Component — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `reported_molar_mass_gmol` and `reported_stoichiometry` to `Analysis` so that Versuch III.1 (and future analyses) can report element content (% P) instead of substance content, with g_wahr and V_erw calculated correctly.

**Architecture:** Two nullable Float columns on the `analysis` table. When `reported_molar_mass_gmol` is set, `MassBasedEvaluator` uses `n × M_reported / M_substance` as the correction factor in `_g_wahr` and `n × M_reported` as the effective molar mass in `_v_expected_explicit`. Existing analyses (fields = None) are completely unaffected.

**Note on spec scope "drei Stellen":** The spec lists `_g_wahr`, n→m-Konversion, and `_v_expected_explicit` as three guard locations. In `MassBasedEvaluator` there is no standalone n→m code path: the student announces their own calculated `% P`, which is compared directly against `a_min`/`a_max` (both already in `% P` via `_g_wahr`). The n→m conversion described in the spec is conceptually identical to the `mw_effective` change inside `_v_expected_explicit` — they are the same location. This plan therefore covers all two actual code sites (`_g_wahr` + `_v_expected_explicit`) and correctly satisfies all three spec requirements.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, Alembic (flask-migrate), pytest, Jinja2

**Spec:** `docs/superpowers/specs/2026-03-20-reported-component-design.md`

---

### Task 1: Add fields to Analysis model and generate migration

**Files:**
- Modify: `models.py:189-190` (after `m_einwaage_max_mg`)
- Create: `migrations/versions/<hash>_add_reported_component_to_analysis.py` (auto-generated)

- [ ] **Step 1: Add two fields to the Analysis model**

In `models.py`, after the line `m_einwaage_max_mg = db.Column(db.Float, nullable=True)` (line 190), add:

```python
reported_molar_mass_gmol = db.Column(db.Float, nullable=True)
reported_stoichiometry = db.Column(db.Float, nullable=True)
```

- [ ] **Step 2: Generate the migration**

```bash
flask db migrate -m "add_reported_component_to_analysis"
```

Expected: a new file created in `migrations/versions/` containing `op.add_column` calls for both columns.

- [ ] **Step 3: Apply the migration**

```bash
flask db upgrade
```

Expected: exits without error.

- [ ] **Step 4: Commit**

```bash
git add models.py migrations/versions/
git commit -m "feat: add reported_molar_mass_gmol and reported_stoichiometry to Analysis"
```

---

### Task 2: Calculation — _g_wahr with reported component (TDD)

**Files:**
- Modify: `tests/test_hydrate_factor.py` (update `_make_sample` + add new tests)
- Modify: `calculation_modes.py:132-143`

#### Step 1 — Update the existing `_make_sample` helper

`test_hydrate_factor.py` creates `analysis = MagicMock()` without setting `reported_molar_mass_gmol`. After the implementation, `MagicMock()` would return a truthy object for that attribute and break existing tests. Fix this first by expanding the helper signature.

- [ ] **Step 1a: Update `_make_sample` in `test_hydrate_factor.py`**

Replace the existing `_make_sample` function (lines 7–29) with:

```python
def _make_sample(m_s, m_ges, p_effective, molar_mass, anhydrous_molar_mass=None,
                 reported_molar_mass=None, reported_stoich=None):
    """Build minimal mock sample chain for g_wahr tests."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass
    substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass

    analysis = MagicMock()
    analysis.substance = substance
    analysis.e_ab_g = None
    analysis.method = None
    analysis.reported_molar_mass_gmol = reported_molar_mass
    analysis.reported_stoichiometry = reported_stoich

    batch = MagicMock()
    batch.p_effective = p_effective
    batch.analysis = analysis

    sample = MagicMock()
    sample.m_s_actual_g = m_s
    sample.m_ges_actual_g = m_ges
    sample.batch = batch
    return sample
```

- [ ] **Step 1b: Verify existing tests still pass (no implementation changes yet)**

```bash
pytest tests/test_hydrate_factor.py -v
```

Expected: all 5 existing tests PASS.

- [ ] **Step 2: Write the four new failing tests**

Append to `tests/test_hydrate_factor.py`:

```python
def test_g_wahr_reported_molar_mass_replaces_hydrate_correction():
    """reported_molar_mass_gmol takes priority; hydrate correction is skipped.

    300 mg Na2HPO4·2H2O (MW=177.99), anhydrous MW=141.96, p=100%.
    Reported: P (MW=30.974, stoich=1.0).
    Expected g_wahr = 100% * (1.0 * 30.974) / 177.99 = 17.40%
    (NOT the hydrate-corrected 79.76%)
    """
    sample = _make_sample(0.3, 0.3, 100.0, 177.99, anhydrous_molar_mass=141.96,
                          reported_molar_mass=30.974, reported_stoich=1.0)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 100.0 * (1.0 * 30.974) / 177.99
    assert abs(result - expected) < 0.001


def test_g_wahr_reported_stoichiometry_none_defaults_to_1():
    """reported_stoichiometry=None is treated as 1.0."""
    sample = _make_sample(0.3, 0.3, 100.0, 177.99, anhydrous_molar_mass=None,
                          reported_molar_mass=30.974, reported_stoich=None)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 100.0 * (1.0 * 30.974) / 177.99
    assert abs(result - expected) < 0.001


def test_g_wahr_reported_stoichiometry_2():
    """Stoichiometry factor 2 is applied correctly."""
    # raw = (1.0/2.0)*100 = 50%, correction = (2.0 * 50.0) / 200.0 = 0.5
    # result = 50.0 * 0.5 = 25.0%
    sample = _make_sample(1.0, 2.0, 100.0, 200.0, anhydrous_molar_mass=None,
                          reported_molar_mass=50.0, reported_stoich=2.0)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 50.0 * (2.0 * 50.0) / 200.0
    assert abs(result - expected) < 0.001


def test_g_wahr_reported_molar_mass_with_purity():
    """Purity is applied before the reported-component correction."""
    sample = _make_sample(0.3, 0.3, 99.0, 177.99, anhydrous_molar_mass=None,
                          reported_molar_mass=30.974, reported_stoich=1.0)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 99.0 * (1.0 * 30.974) / 177.99
    assert abs(result - expected) < 0.001
```

- [ ] **Step 3: Run new tests — verify they FAIL**

```bash
pytest tests/test_hydrate_factor.py -v -k "reported"
```

Expected: 4 FAILED (AttributeError or wrong value — implementation not yet written).

- [ ] **Step 4: Implement the guard in `_g_wahr`**

In `calculation_modes.py`, replace `_g_wahr` (lines 132–143) with:

```python
def _g_wahr(self, sample) -> float | None:
    if sample.m_s_actual_g is None or sample.m_ges_actual_g is None or sample.m_ges_actual_g <= 0:
        return None
    raw = (sample.m_s_actual_g / sample.m_ges_actual_g) * sample.batch.p_effective
    analysis = sample.batch.analysis
    substance = analysis.substance
    if analysis.reported_molar_mass_gmol is not None:
        # Reported-component path: convert substance content to element/component content
        if (substance is not None
                and substance.molar_mass_gmol is not None
                and substance.molar_mass_gmol > 0):
            n = analysis.reported_stoichiometry or 1.0
            raw = raw * (n * analysis.reported_molar_mass_gmol) / substance.molar_mass_gmol
    elif (substance is not None
            and substance.anhydrous_molar_mass_gmol is not None
            and substance.molar_mass_gmol is not None
            and substance.molar_mass_gmol > 0):
        # Hydrate correction path (unchanged)
        raw = raw * (substance.anhydrous_molar_mass_gmol / substance.molar_mass_gmol)
    return raw
```

- [ ] **Step 5: Run all tests in test_hydrate_factor.py — verify all PASS**

```bash
pytest tests/test_hydrate_factor.py -v
```

Expected: 9 tests PASS.

- [ ] **Step 6: Run full test suite — verify no regressions**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add calculation_modes.py tests/test_hydrate_factor.py
git commit -m "feat: support reported_molar_mass_gmol in _g_wahr"
```

---

### Task 3: Calculation — _v_expected_explicit with reported component (TDD)

**Files:**
- Create: `tests/test_reported_component.py`
- Modify: `calculation_modes.py:156-161`

- [ ] **Step 1: Create `tests/test_reported_component.py`**

```python
"""Tests for _v_expected_explicit with reported_molar_mass_gmol."""
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample(molar_mass_gmol, reported_molar_mass=None, reported_stoich=None,
                 method_type="complexometric", c_titrant=0.1, n_eq_titrant=1.0,
                 anhydrous_molar_mass=None):
    """Build a minimal mock sample for _v_expected_explicit tests."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass_gmol
    substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass

    method = MagicMock()
    method.method_type = method_type
    method.c_titrant_mol_l = c_titrant
    method.n_eq_titrant = n_eq_titrant
    method.c_vorlage_mol_l = None
    method.n_eq_vorlage = None
    method.v_vorlage_ml = None

    analysis = MagicMock()
    analysis.substance = substance
    analysis.method = method
    analysis.reported_molar_mass_gmol = reported_molar_mass
    analysis.reported_stoichiometry = reported_stoich

    batch = MagicMock()
    batch.analysis = analysis

    sample = MagicMock()
    sample.batch = batch
    return sample


def test_v_expected_uses_reported_molar_mass_as_mw_effective():
    """
    III.1: 300 mg Na2HPO4·2H2O (MW=177.99), g_wahr=17.40%
    n_Mg = (300 * 17.40/100) / (1.0 * 30.974) = 52.2 / 30.974 = 1.6853 mmol
    V_ZnSO4 = 1.6853 * 1.0 / 0.1 = 16.853 mL
    """
    sample = _make_sample(177.99, reported_molar_mass=30.974, reported_stoich=1.0)
    ev = MassBasedEvaluator()
    result = ev._v_expected_explicit(sample, g_wahr=17.40, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 16.853) < 0.01


def test_v_expected_reported_stoich_none_defaults_to_1():
    """reported_stoichiometry=None defaults to 1.0 in V_erw calculation."""
    sample = _make_sample(177.99, reported_molar_mass=30.974, reported_stoich=None)
    ev = MassBasedEvaluator()
    result = ev._v_expected_explicit(sample, g_wahr=17.40, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 16.853) < 0.01


def test_v_expected_without_reported_molar_mass_uses_substance_mw():
    """Without reported_molar_mass, falls back to substance.molar_mass_gmol (no hydrate)."""
    sample = _make_sample(177.99, reported_molar_mass=None)
    ev = MassBasedEvaluator()
    # g_wahr = 50.0% as if no correction
    # n_analyte = (300 * 50.0/100) / 177.99 = 150 / 177.99 = 0.8428 mmol
    # V = 0.8428 * 1.0 / 0.1 = 8.428 mL
    result = ev._v_expected_explicit(sample, g_wahr=50.0, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 8.428) < 0.01


def test_v_expected_reported_molar_mass_with_stoich_2():
    """Stoichiometry factor 2 halves the mw_effective, doubling n_analyte and V."""
    # mw_effective = 2.0 * 30.974 = 61.948
    # n = (300 * 17.40/100) / 61.948 = 52.2 / 61.948 = 0.8426 mmol
    # V = 0.8426 * 1.0 / 0.1 = 8.426 mL
    sample = _make_sample(177.99, reported_molar_mass=30.974, reported_stoich=2.0)
    ev = MassBasedEvaluator()
    result = ev._v_expected_explicit(sample, g_wahr=17.40, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 8.426) < 0.01
```

- [ ] **Step 2: Run tests — verify they FAIL**

```bash
pytest tests/test_reported_component.py -v
```

Expected: FAILED (wrong values because mw still uses substance/anhydrous MW).

- [ ] **Step 3: Implement the guard in `_v_expected_explicit`**

In `calculation_modes.py`, replace lines 156–161:

```python
        # When g_wahr is on anhydrous basis (hydrate correction applied), use anhydrous MW
        mw = (substance.anhydrous_molar_mass_gmol
              if substance.anhydrous_molar_mass_gmol and substance.anhydrous_molar_mass_gmol > 0
              else substance.molar_mass_gmol)
        e_ab_mg = e_ab_g * 1000.0
        n_analyte_mmol = (e_ab_mg * g_wahr / 100.0) / mw
```

With:

```python
        # Effective MW: reported-component path takes priority over hydrate correction
        analysis = sample.batch.analysis
        if analysis.reported_molar_mass_gmol is not None:
            n = analysis.reported_stoichiometry or 1.0
            mw = n * analysis.reported_molar_mass_gmol
        else:
            # When g_wahr is on anhydrous basis (hydrate correction applied), use anhydrous MW
            mw = (substance.anhydrous_molar_mass_gmol
                  if substance.anhydrous_molar_mass_gmol and substance.anhydrous_molar_mass_gmol > 0
                  else substance.molar_mass_gmol)
        e_ab_mg = e_ab_g * 1000.0
        n_analyte_mmol = (e_ab_mg * g_wahr / 100.0) / mw
```

- [ ] **Step 4: Run new tests — verify they PASS**

```bash
pytest tests/test_reported_component.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Run full test suite — verify no regressions**

```bash
pytest -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add calculation_modes.py tests/test_reported_component.py
git commit -m "feat: support reported_molar_mass_gmol in _v_expected_explicit"
```

---

### Task 4: Configure III.1 in init_db.py

**Files:**
- Modify: `init_db.py:114-136` (post-flush explicit parameters section)

The III.1 method currently has no explicit titration parameters. Add them and the new reported-component fields.

- [ ] **Step 1: Add III.1 explicit parameters**

In `init_db.py`, find the exact anchor string:
```python
    # II.1: Ascorbinsäure – direct titration with I2 0.05 mol/L (1 eq per mol)
    methods["II.1"].c_titrant_mol_l = 0.05
    methods["II.1"].n_eq_titrant = 1.0
```
Append immediately after that block (before the `# ── Reagenzien` comment):
```python

    # III.1: Phosphorgehalt – EDTA (Vorlage) 0.1 M excess, back-titrated with ZnSO4 0.1 M
    # method_type="complexometric" uses the direct branch: V = n_analyte * n_eq / c_titrant
    # stoichiometry 1 P ≙ 1 Mg2+ ≙ 1 ZnSO4 means n_eq_titrant=1.0 gives the correct result
    methods["III.1"].c_titrant_mol_l = 0.1
    methods["III.1"].n_eq_titrant = 1.0
    methods["III.1"].c_vorlage_mol_l = 0.1
    methods["III.1"].n_eq_vorlage = 1.0
    methods["III.1"].v_vorlage_ml = 25.0
```

- [ ] **Step 2: Set reported-component fields on the III.1 Analysis object**

In the same file, find the exact anchor string:
```python
    # ── Reagenzien (Beispiel-Katalog) ──────────────────────────────
```
Insert immediately before that line:
```python
    # III.1: report Phosphorgehalt (% P) instead of substance content
    analyses["III.1"].reported_molar_mass_gmol = 30.974   # M(P)
    analyses["III.1"].reported_stoichiometry = 1.0        # 1 P per Na2HPO4 formula unit

```

- [ ] **Step 3: Re-initialise the database**

```bash
flask init-db
```

Expected: no errors.

- [ ] **Step 4: Spot-check via Flask shell**

```bash
flask shell
```

```python
from models import Analysis
a = Analysis.query.filter_by(code="III.1").first()
print(a.reported_molar_mass_gmol)   # → 30.974
print(a.reported_stoichiometry)     # → 1.0
```

- [ ] **Step 5: Commit**

```bash
git add init_db.py
git commit -m "feat: configure III.1 with reported_molar_mass_gmol=30.974 (Phosphorgehalt)"
```

---

### Task 5: Admin UI — form handler and template

**Files:**
- Modify: `app.py:584` (POST handler, after `notes` assignment)
- Modify: `templates/admin/analysis_form.html:26` (add fields after existing row)

- [ ] **Step 1: Add fields to the POST handler in `app.py`**

After line 584 (`item.notes = request.form.get("notes") or None`), add:

```python
            item.reported_molar_mass_gmol = _float(request.form.get("reported_molar_mass_gmol"))
            item.reported_stoichiometry = _float(request.form.get("reported_stoichiometry"))
```

- [ ] **Step 2: Add fields to the HTML template**

In `templates/admin/analysis_form.html`, after the closing `</div>` of the second `<div class="row">` (line 26, after `g_ab_max_group`), add a new row:

```html
  <div class="row">
    <div class="col-md-3">{{ field("reported_molar_mass_gmol", "Berichtete Molmasse (g/mol)", item.reported_molar_mass_gmol, type="number", step="0.001", help="Leer = Substanzgehalt. Gesetzt = Elementgehalt (z.B. 30.974 für P)") }}</div>
    <div class="col-md-2">{{ field("reported_stoichiometry", "Stöchiometrie", item.reported_stoichiometry, type="number", step="0.001", help="Anzahl berichteter Einheiten pro Formeleinheit (Standard: 1)") }}</div>
  </div>
```

- [ ] **Step 3: Manual smoke test**

Start the dev server (`flask run`), navigate to the III.1 analysis form in the admin UI.
Verify:
- Both new fields appear and show the pre-filled values (30.974 and 1.0)
- Saving the form preserves the values

- [ ] **Step 4: Commit**

```bash
git add app.py templates/admin/analysis_form.html
git commit -m "feat: add reported_molar_mass_gmol fields to analysis admin form"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: End-to-end smoke test**

Open the Einwaagemaske for a III.1 batch. Verify:
- `g_wahr` shows approximately 17.40% (for 100% pure Na₂HPO₄·2H₂O, ~300 mg)
- `a_min` and `a_max` are 17.40% × 0.98 and × 1.02 respectively

- [ ] **Step 3: Commit (if any last fixes needed)**

```bash
git add -A
git commit -m "fix: <describe any last-minute fix>"
```
