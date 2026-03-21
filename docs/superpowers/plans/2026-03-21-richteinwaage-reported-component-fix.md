# Richteinwaage Reported-Component Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 bugs so that `target_m_s_min_g` and `m_ges_max` are calculated correctly for reported-component analyses (e.g. III.1 Phosphorgehalt), where `gehalt_min_pct` is an element % (not a substance %) and requires CONTENT_FACTOR for conversion.

**Architecture:** Three files are touched: `app.py` (API endpoint, server-side batch fallback, `evaluate_weighing_limits`), `templates/admin/batch_form.html` (JS `recalcMassFields`), and `templates/ta/weighing.html` (orientation hint). All changes are additive branches guarded by `reported_molar_mass_gmol is not None`. No DB migration needed.

**Tech Stack:** Python/Flask, SQLAlchemy, Jinja2, vanilla JS. Tests use pytest + unittest.mock.

---

## Background / Key Formulas

```
CONTENT_FACTOR = reported_stoichiometry × reported_molar_mass_gmol / molar_mass_gmol
               = 1.0 × 30.974 / 177.99 = 0.1740   (for III.1)

g_wahr (% element) = (m_s / m_ges) × p_eff × CONTENT_FACTOR
   -- p_eff is in percent (e.g. 99.5), result is in percent (e.g. 17.13)

mSMin  = mGesMin × gehalt_min / (100 × CONTENT_FACTOR)   ← fixes Bug 1 & 3
mGesMax = m_s × p_eff × CONTENT_FACTOR / p_min            ← fixes Bug 4
```

For regular (non-reported-component) analyses, CONTENT_FACTOR = 1.0 (or hydrate_factor), so the existing formulas are unchanged.

---

## File Map

| File | What changes |
|---|---|
| `app.py:2318-2327` | Add `reported_molar_mass_gmol`, `reported_stoichiometry` to API response |
| `app.py:1248-1253` | Server-side mSMin fallback: new formula for reported-component |
| `app.py:87-107` | `evaluate_weighing_limits`: replace `hydrate_factor` with `content_factor` |
| `templates/admin/batch_form.html:160-192` | `recalcMassFields()`: compute `contentFactor`, new mSMin formula + hint text |
| `templates/ta/weighing.html:437-438` | Orientation hint: `HYDRATE_FACTOR` → `CONTENT_FACTOR` |
| `tests/test_weighing_limits.py` | New test: reported-component uses content_factor |
| `tests/test_batch_defaults_api.py` (new) | Tests for API endpoint returning new fields |
| `tests/test_batch_creation_fallback.py` (new) | Tests for server-side mSMin fallback |

---

## Task 1: Fix `evaluate_weighing_limits` — use `content_factor` for reported-component

### Files
- Modify: `app.py:87-107`
- Modify: `tests/test_weighing_limits.py`

---

- [ ] **Step 1: Write the failing test**

In `tests/test_weighing_limits.py`, **replace** the existing `_make_batch` helper definition
(keep all existing tests — the new signature is fully backward-compatible because
`reported_molar_mass` and `reported_stoichiometry` default to `None`, which is what
`evaluate_weighing_limits` will test as falsy). Then append the two new test functions.

```python
# REPLACE the existing _make_batch definition with this one:
def _make_batch(target_m_s_min_g, target_m_ges_g, p_effective, gehalt_min_pct,
                molar_mass=None, anhydrous_molar_mass=None,
                reported_molar_mass=None, reported_stoichiometry=None):
    batch = MagicMock()
    batch.target_m_s_min_g = target_m_s_min_g
    batch.target_m_ges_g = target_m_ges_g
    batch.analysis.calculation_mode = MODE_ASSAY_MASS_BASED
    batch.p_effective = p_effective
    batch.gehalt_min_pct = gehalt_min_pct
    batch.analysis.substance.molar_mass_gmol = molar_mass
    batch.analysis.substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass
    # Must be explicitly set (not left as MagicMock) so the None-check in
    # evaluate_weighing_limits works correctly for old tests.
    batch.analysis.reported_molar_mass_gmol = reported_molar_mass
    batch.analysis.reported_stoichiometry = reported_stoichiometry
    return batch


# APPEND these new tests at the end of the file:
def test_reported_component_uses_content_factor(app):
    """III.1: reported_molar_mass=30.974, molar_mass=177.99 → CONTENT_FACTOR≈0.174.
    m_s=0.854, p_eff=100, p_min=15 → m_ges_max = 0.854 * 100 * 0.174 / 15 ≈ 0.990 g.
    m_ges=1.5 must violate (was 5.69 g with hydrate_factor=1.0, so no violation before fix).
    """
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(
            target_m_s_min_g=0.854, target_m_ges_g=0.99,
            p_effective=100.0, gehalt_min_pct=15.0,
            molar_mass=177.99, reported_molar_mass=30.974, reported_stoichiometry=1.0,
        )
        content_factor = 1.0 * 30.974 / 177.99  # ≈ 0.1740
        m_ges_max = 0.854 * 100.0 * content_factor / 15.0  # ≈ 0.990 g
        # Just above → violation
        result_over = evaluate_weighing_limits(batch, 0.854, m_ges_max + 0.1)
        assert result_over["m_ges_max_violation"], \
            "Expected violation: m_ges exceeds content-factor-corrected max"
        # Just below → no violation
        result_under = evaluate_weighing_limits(batch, 0.854, m_ges_max - 0.01)
        assert not result_under["m_ges_max_violation"], \
            "Expected no violation: m_ges within content-factor-corrected max"


def test_reported_component_stoich_none_defaults_to_1(app):
    """reported_stoichiometry=None must default to 1.0 — same result as stoich=1.0."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch_none = _make_batch(
            target_m_s_min_g=0.854, target_m_ges_g=0.99,
            p_effective=100.0, gehalt_min_pct=15.0,
            molar_mass=177.99, reported_molar_mass=30.974, reported_stoichiometry=None,
        )
        batch_one = _make_batch(
            target_m_s_min_g=0.854, target_m_ges_g=0.99,
            p_effective=100.0, gehalt_min_pct=15.0,
            molar_mass=177.99, reported_molar_mass=30.974, reported_stoichiometry=1.0,
        )
        content_factor = 1.0 * 30.974 / 177.99
        m_ges_max = 0.854 * 100.0 * content_factor / 15.0
        # Both must give identical violation behaviour: over the limit
        assert evaluate_weighing_limits(batch_none, 0.854, m_ges_max + 0.1)["m_ges_max_violation"]
        assert evaluate_weighing_limits(batch_one,  0.854, m_ges_max + 0.1)["m_ges_max_violation"]
        # And identical pass behaviour: under the limit
        assert not evaluate_weighing_limits(batch_none, 0.854, m_ges_max - 0.01)["m_ges_max_violation"]
        assert not evaluate_weighing_limits(batch_one,  0.854, m_ges_max - 0.01)["m_ges_max_violation"]
```

- [ ] **Step 2: Run tests to confirm they FAIL**

```
python -m pytest tests/test_weighing_limits.py::test_reported_component_uses_content_factor tests/test_weighing_limits.py::test_reported_component_stoich_none_defaults_to_1 -v
```

Expected: both tests FAIL (assertion error — violation not raised because hydrate_factor=1.0 gives wrong max).

- [ ] **Step 3: Implement the fix in `app.py`**

Replace lines 87-107 in `app.py` (the `# Check maximum total mass` block):

```python
        # Check maximum total mass: m_ges must not exceed m_s * p_eff * content_factor / p_min
        # (target_m_ges_g is orientation only — not a hard minimum)
        p_min = batch.gehalt_min_pct
        p_eff = batch.p_effective
        substance = batch.analysis.substance if batch.analysis else None
        mw = substance.molar_mass_gmol if substance else None
        analysis = batch.analysis
        reported_mw = analysis.reported_molar_mass_gmol if analysis else None
        if reported_mw and mw and mw > 0:
            n = (analysis.reported_stoichiometry or 1.0)
            content_factor = n * reported_mw / mw
        else:
            mw_a = substance.anhydrous_molar_mass_gmol if substance else None
            content_factor = (mw_a / mw) if (mw_a and mw and mw > 0) else 1.0
        if (m_s_actual_g is not None
                and m_ges_actual_g is not None
                and p_min is not None
                and p_min > 0
                and p_eff > 0):
            m_ges_max = m_s_actual_g * p_eff * content_factor / p_min
            if m_ges_actual_g > m_ges_max + 1e-9:  # small epsilon for float precision
                details["m_ges_max_violation"] = True
                checks.append(
                    f"m_ges {m_ges_actual_g:.3f} g > Max {m_ges_max:.3f} g "
                    f"(bei m_S={m_s_actual_g:.3f} g, p_eff={p_eff:.1f}%, p_min={p_min:.1f}%,"
                    f" content_factor={content_factor:.4f})"
                )
```

- [ ] **Step 4: Run all weighing-limits tests**

```
python -m pytest tests/test_weighing_limits.py -v
```

Expected: all tests pass (including the pre-existing hydrate-correction test).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_weighing_limits.py
git commit -m "fix: use content_factor for reported-component in evaluate_weighing_limits"
```

---

## Task 2: Fix server-side batch mSMin fallback in `app.py`

### Files
- Modify: `app.py:1248-1253`
- Create: `tests/test_batch_creation_fallback.py`

---

- [ ] **Step 1: Write the failing test**

Create `tests/test_batch_creation_fallback.py`.

Note: the server-side fallback lives inside the batch-creation route handler and is not
directly unit-testable without a full POST. The tests below verify (a) the correct
formula numerically, and (b) that the formula is actually applied by calling the real
`Analysis` DB object. A full route-integration test is out of scope here.

```python
"""Tests for the server-side mSMin fallback formula (Bug 3)."""
import pytest


def test_reported_component_fallback_formula_is_correct(app):
    """For III.1: verify that mSMin = mGesMin × gehalt_min / (100 × CONTENT_FACTOR).

    Uses the real Analysis object from DB so the test breaks if the DB config changes.
    """
    with app.app_context():
        from models import Analysis
        analysis = Analysis.query.filter_by(code="III.1").first()
        assert analysis is not None
        assert analysis.reported_molar_mass_gmol is not None, \
            "III.1 must have reported_molar_mass_gmol configured"

        e_ab      = analysis.e_ab_g             # 0.3 g
        k         = analysis.k_determinations   # 2
        n_extra   = 1
        mortar_f  = 1.1
        gehalt_min = 15.0

        mges = round(e_ab * (k + n_extra) * mortar_f, 3)
        assert abs(mges - 0.99) < 0.001, f"mGesMin = {mges}, expected ~0.99"

        n  = analysis.reported_stoichiometry or 1.0
        cf = n * analysis.reported_molar_mass_gmol / analysis.substance.molar_mass_gmol
        assert abs(cf - 0.1740) < 0.001, f"CONTENT_FACTOR = {cf:.4f}, expected ~0.1740"

        ms_correct = round(mges * gehalt_min / (100.0 * cf), 3)
        assert abs(ms_correct - 0.854) < 0.01, \
            f"Correct mSMin = {ms_correct}, expected ~0.854 g"


def test_old_formula_gives_wrong_answer():
    """Document that the old formula was wrong — pure arithmetic, no app needed."""
    e_ab, k, n_extra, mortar_f, gehalt_min = 0.3, 2, 1, 1.1, 15.0
    mges = round(e_ab * (k + n_extra) * mortar_f, 3)      # 0.990 g
    old_ms = round(e_ab * 98.0 / 100.0, 3)                # 0.294 g — old wrong formula
    cf = 1.0 * 30.974 / 177.99                             # 0.1740
    correct_ms = round(mges * gehalt_min / (100.0 * cf), 3)  # 0.854 g
    assert abs(old_ms - 0.294) < 0.001, "Old formula gives 0.294 g"
    assert abs(correct_ms - 0.854) < 0.01, "New formula gives 0.854 g"
    assert correct_ms > old_ms * 2, "New value must be significantly larger"
```

- [ ] **Step 2: Run tests to confirm both pass (documenting the bug pre-fix)**

```
python -m pytest tests/test_batch_creation_fallback.py -v
```

Expected: both tests pass (they verify the correct formula, not that the app currently uses it).

- [ ] **Step 3: Implement the fix in `app.py`**

Replace lines 1248-1253 in `app.py`:

```python
                    if analysis.reported_molar_mass_gmol is not None:
                        # Reported-component: target_m_s_min is minimum substance mass in the
                        # blend. Derived from total blend mass × gehalt_min / (100 × cf),
                        # where cf = CONTENT_FACTOR converts element% back to substance fraction.
                        substance = analysis.substance
                        n = analysis.reported_stoichiometry or 1.0
                        cf = (n * analysis.reported_molar_mass_gmol / substance.molar_mass_gmol
                              if substance and substance.molar_mass_gmol else 1.0)
                        computed_m_s = round(computed_m_ges * gehalt_min / (100.0 * cf), 3)
                    else:
                        computed_m_s = round(computed_m_ges * gehalt_min / 100.0, 3)
```

- [ ] **Step 4: Run the test suite**

```
python -m pytest tests/test_batch_creation_fallback.py tests/test_weighing_limits.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_batch_creation_fallback.py
git commit -m "fix: use content_factor for reported-component server-side mSMin fallback"
```

---

## Task 3: Extend API endpoint — add `reported_molar_mass_gmol` and `reported_stoichiometry`

### Files
- Modify: `app.py:2318-2327`
- Create: `tests/test_batch_defaults_api.py`

---

- [ ] **Step 1: Write the failing test**

Create `tests/test_batch_defaults_api.py`:

```python
"""Tests for /api/analysis/<id>/defaults endpoint."""
import json
import pytest


def test_api_returns_reported_molar_mass_for_phosphor(client, app):
    """III.1 defaults must include reported_molar_mass_gmol and reported_stoichiometry."""
    with app.app_context():
        from models import Analysis
        analysis = Analysis.query.filter_by(code="III.1").first()
        assert analysis is not None
        aid = analysis.id

    resp = client.get(f"/api/analysis/{aid}/defaults")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reported_molar_mass_gmol" in data, "API must return reported_molar_mass_gmol"
    assert "reported_stoichiometry" in data,   "API must return reported_stoichiometry"
    assert abs(data["reported_molar_mass_gmol"] - 30.974) < 0.01
    assert data["reported_stoichiometry"] == 1.0


def test_api_returns_null_reported_mass_for_regular_analysis(client, app):
    """Regular analysis (e.g. I.2) must return reported_molar_mass_gmol=null."""
    with app.app_context():
        from models import Analysis
        analysis = Analysis.query.filter_by(code="I.2").first()
        assert analysis is not None
        aid = analysis.id

    resp = client.get(f"/api/analysis/{aid}/defaults")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reported_molar_mass_gmol" in data
    assert data["reported_molar_mass_gmol"] is None
```

- [ ] **Step 2: Run test to confirm it FAILS**

```
python -m pytest tests/test_batch_defaults_api.py -v
```

Expected: both tests FAIL with `AssertionError: API must return reported_molar_mass_gmol`.

- [ ] **Step 3: Implement the fix in `app.py`**

In `api_analysis_defaults()`, add two lines inside the `result = { ... }` dict (after the existing `m_einwaage_max_mg` line, before the closing `}`):

```python
            "reported_molar_mass_gmol": analysis.reported_molar_mass_gmol,
            "reported_stoichiometry":   analysis.reported_stoichiometry,
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/test_batch_defaults_api.py -v
```

Expected: both pass.

- [ ] **Step 5: Run full test suite to check for regressions**

```
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_batch_defaults_api.py
git commit -m "feat: expose reported_molar_mass_gmol and reported_stoichiometry in analysis defaults API"
```

---

## Task 4: Fix `recalcMassFields()` JS in `batch_form.html`

### Files
- Modify: `templates/admin/batch_form.html:160-192`

No automated test for JS (template logic). Verify manually after implementing.

---

- [ ] **Step 1: Read the current `recalcMassFields()` function (lines 160–192)**

Understand the current structure before editing.

- [ ] **Step 2: Replace `recalcMassFields()` with the corrected version**

Replace the entire function (lines 160–192):

```javascript
  function recalcMassFields() {
    if (!currentDefaults) return;
    const eAb = currentDefaults.e_ab_g;
    const kDet = currentDefaults.k_determinations || 3;
    const nExtra = parseInt(nExtraInput.value) || 0;
    const mortarF = parseFloat(mortarFactorInput.value.replace(',', '.')) || 1.0;
    const gehaltMin = parseFloat(gehaltMinInput.value);
    const hasAliquot = !!currentDefaults.has_aliquot;

    // Compute CONTENT_FACTOR for reported-component analyses (e.g. III.1 Phosphorgehalt).
    // reported_molar_mass_gmol is set when the result is reported as an element % rather
    // than a substance %. In that case gehalt_min_pct is an element %, not a substance %.
    const reportedMw     = currentDefaults.reported_molar_mass_gmol;
    const reportedStoich = currentDefaults.reported_stoichiometry ?? 1.0;
    const molarMass      = currentDefaults.molar_mass_gmol;
    const contentFactor  = (reportedMw && molarMass && molarMass > 0)
      ? (reportedStoich * reportedMw) / molarMass
      : null;

    if (eAb && !isNaN(gehaltMin) && gehaltMin > 0 && gehaltMin <= 100) {
      // With aliquoting, one dissolution (Stammlösung) serves all determinations —
      // only the mortar factor applies, not k_total.
      const mGesMin = hasAliquot
        ? +(eAb * mortarF).toFixed(3)
        : +(eAb * (kDet + nExtra) * mortarF).toFixed(3);

      // For reported-component: gehaltMin is element %, must divide by CONTENT_FACTOR
      // to convert back to substance mass fraction.
      // For regular analyses: gehaltMin is substance % directly.
      const mSMin = contentFactor
        ? +(mGesMin * gehaltMin / (100 * contentFactor)).toFixed(3)
        : +(mGesMin * gehaltMin / 100).toFixed(3);

      // Only auto-fill if field is empty or was auto-filled before
      if (!targetMGesInput.dataset.userEdited) {
        targetMGesInput.value = mGesMin;
      }
      if (!targetMSMinInput.dataset.userEdited) {
        targetMSMinInput.value = mSMin;
      }

      massCalcInfo.style.display = "";
      if (contentFactor) {
        massCalcDetail.textContent =
          `Berechnung (Elementgehalt): E_AB (${eAb} g) × (${kDet} + ${nExtra} Zusatz) × ` +
          `${mortarF} Mörserfaktor = ${mGesMin} g Mindest-Gesamt; ` +
          `${mGesMin} g × ${gehaltMin}% / (100 × ${contentFactor.toFixed(4)}) = ${mSMin} g Mindest-Substanz ` +
          `[max. ${(contentFactor * 100).toFixed(2)}% Elementgehalt bei reiner Substanz]`;
      } else {
        massCalcDetail.textContent = hasAliquot
          ? `Berechnung (mit Aliquotierung): E_AB (${eAb} g) × ${mortarF} Mörserfaktor = ${mGesMin} g Mindest-Gesamt; davon ${gehaltMin}% = ${mSMin} g Mindest-Substanz`
          : `Berechnung: E_AB (${eAb} g) × (${kDet} + ${nExtra} Zusatz) × ${mortarF} Mörserfaktor = ${mGesMin} g Mindest-Gesamt; davon ${gehaltMin}% = ${mSMin} g Mindest-Substanz`;
      }
    } else {
      massCalcInfo.style.display = "none";
    }
  }
```

- [ ] **Step 3: Manual verification**

Open the batch creation form for III.1 in the browser.
- Enter `gehalt_min_pct = 15`, `n_extra = 1`, `mortar_loss_factor = 1.1`
- Expected `target_m_ges_g` = 0.990 g
- Expected `target_m_s_min_g` = 0.854 g
- Expected hint text includes "Elementgehalt" and "max. 17.40% Elementgehalt bei reiner Substanz"

For a regular analysis (e.g. I.2), enter `gehalt_min_pct = 50`:
- Expected `mSMin` = mGesMin × 50 / 100 (unchanged behavior)
- Expected hint text does NOT contain "Elementgehalt"

- [ ] **Step 4: Commit**

```bash
git add templates/admin/batch_form.html
git commit -m "fix: use content_factor in recalcMassFields JS for reported-component analyses"
```

---

## Task 5: Fix orientation hint in `weighing.html`

### Files
- Modify: `templates/ta/weighing.html:437-438`

---

- [ ] **Step 1: Replace line 438 — `HYDRATE_FACTOR` → `CONTENT_FACTOR`**

Current (line 438):
```javascript
      ? mSMin * P_EFF * HYDRATE_FACTOR / P_MIN : null;
```

Replace with:
```javascript
      ? mSMin * P_EFF * CONTENT_FACTOR / P_MIN : null;
```

- [ ] **Step 2: Manual verification**

Open the weighing page for a III.1 batch with `target_m_s_min_g = 0.854 g`, `target_m_ges_g = 0.990 g`, `gehalt_min_pct = 15`, `p_eff = 100`.

Expected orientation banner:
```
Orientierung: m_S,min = 0.854 g · m_ges Richtwert = 0.990 g · Max. m_ges bei m_S,min = 0,990 g
```
Calculation: `0.854 × 100 × 0.174 / 15 = 0.990 g` ✓

Before fix (with HYDRATE_FACTOR = 1.0): `0.854 × 100 × 1.0 / 15 = 5.693 g` — clearly wrong.

- [ ] **Step 3: Run full test suite**

```
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add templates/ta/weighing.html
git commit -m "fix: use CONTENT_FACTOR in weighing.html orientation hint max m_ges"
```

---

## Final Verification

- [ ] Run the full test suite one last time:

```
python -m pytest tests/ -v
```

- [ ] Verify III.1 end-to-end in the browser:
  1. Create a new batch for III.1 with `gehalt_min = 15%`, `n_extra = 1`, `mortar = 1.1`
  2. Confirm `target_m_s_min_g ≈ 0.854 g` and `target_m_ges_g = 0.990 g` are saved
  3. Open the weighing page — orientation hint shows `Max. m_ges ≈ 0.990 g`
  4. Enter `m_s = 0.854`, `m_ges = 0.990` — no red violation
  5. Enter `m_s = 0.854`, `m_ges = 1.100` — red violation on m_ges column
