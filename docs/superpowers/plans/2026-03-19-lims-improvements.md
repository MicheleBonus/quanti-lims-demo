# LIMS Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 critical calculation bugs, add colloquium tracking + auto group assignment, and improve UX across the Quanti-LIMS Flask application.

**Architecture:** Three sequential phases: (1) bug fixes + DB migration, (2) new features, (3) UX improvements. All migrations are idempotent. `quanti_lims_updated.db` becomes the new baseline. No breaking changes to existing data.

**Tech Stack:** Python 3.12, Flask 3, SQLAlchemy, Alembic, Jinja2, Bootstrap 5.3, Flatpickr (new), pytest with MagicMock + in-memory SQLite

**Spec:** `docs/superpowers/specs/2026-03-19-lims-improvements-design.md`

---

## File Map

**Modified:**
- `models.py` — add `Substance.anhydrous_molar_mass_gmol`, `Student.is_excluded`, `Semester.active_group_count`, `Block.max_days`, `Method.aliquot_enabled`, new `Colloquium` class; update `Method.has_aliquot`, `Method.aliquot_fraction`
- `calculation_modes.py` — apply hydrate factor in `MassBasedEvaluator._g_wahr`; gate aliquot on `aliquot_enabled`
- `app.py` — fix `evaluate_weighing_limits`; add auto-group routes; add colloquium routes; add `parse_de_date()`; update `_validate_aliquot`; add block edit route
- `templates/base.html` — add Flatpickr CDN; convert all `type="date"` to Flatpickr
- `templates/admin/substance_form.html` — add `anhydrous_molar_mass_gmol` field
- `templates/admin/method_form.html` — add `aliquot_enabled` checkbox; update labels
- `templates/admin/students.html` — add auto-assign + clear-groups buttons
- `templates/admin/batch_form.html` — fix Verschnitt placeholder
- `templates/admin/practical_day_form.html` — change day number to free integer input
- `templates/ta/weighing.html` — add orientation columns + live max JS

**Created:**
- `migrations/versions/<hash>_add_anhydrous_molar_mass.py`
- `migrations/versions/<hash>_add_colloquium_and_is_excluded.py`
- `migrations/versions/<hash>_add_block_max_days_semester_group_count.py`
- `migrations/versions/<hash>_add_aliquot_enabled.py`
- `templates/admin/auto_group_preview.html`
- `templates/colloquium/overview.html`
- `templates/colloquium/plan_form.html`
- `tests/test_hydrate_factor.py`
- `tests/test_weighing_limits.py`
- `tests/test_colloquium.py`
- `tests/test_auto_groups.py`

---

## Phase 1 — Critical Bugs + DB Migration

---

### Task 1: Swap baseline database

**Files:**
- Shell only (no code changes)

- [ ] **Step 1: Back up and rename the database**

```bash
cd C:/Users/Miche/Documents/GitHub/quanti-lims
cp quanti_lims.db quanti_lims_old_backup.db
cp quanti_lims_updated.db quanti_lims.db
```

- [ ] **Step 2: Verify app starts and migrations are current**

```bash
flask db upgrade
flask --app app shell -c "from models import db; print('Tables:', list(db.engine.table_names()))"
```

Expected: no migration errors, all existing tables listed.

- [ ] **Step 3: Run test suite to confirm baseline**

```bash
pytest tests/ -v --tb=short
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add quanti_lims.db
git commit -m "chore: replace db with quanti_lims_updated as new baseline"
```

---

### Task 2: Hydrate factor — migration + model + calculation

**Files:**
- Modify: `models.py:108-124` (Substance class)
- Modify: `calculation_modes.py:127-130` (`_g_wahr`)
- Create: `migrations/versions/<hash>_add_anhydrous_molar_mass.py`
- Create: `tests/test_hydrate_factor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hydrate_factor.py`:

```python
"""Tests for hydrate correction factor in MassBasedEvaluator."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample(m_s, m_ges, p_effective, molar_mass, anhydrous_molar_mass=None):
    """Build minimal mock sample chain for g_wahr tests."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass
    substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass

    analysis = MagicMock()
    analysis.substance = substance
    analysis.e_ab_g = None
    analysis.method = None

    lot = MagicMock()
    lot.p_effective = p_effective

    batch = MagicMock()
    batch.p_effective = p_effective
    batch.analysis = analysis

    sample = MagicMock()
    sample.m_s_actual_g = m_s
    sample.m_ges_actual_g = m_ges
    sample.batch = batch
    return sample


def test_g_wahr_no_hydrate_factor():
    """Without anhydrous_molar_mass, result is unchanged."""
    sample = _make_sample(2.0, 4.0, 100.0, 282.1, anhydrous_molar_mass=None)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    assert abs(result - 50.0) < 0.001


def test_g_wahr_with_hydrate_factor():
    """Li citrate tetrahydrate: factor = 210.1/282.1 ≈ 0.7448."""
    # Raw g_wahr = (2.0/4.0)*100 = 50.0 %
    # With factor: 50.0 * (210.1/282.1) = 37.24 %
    sample = _make_sample(2.0, 4.0, 100.0, 282.1, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 50.0 * (210.1 / 282.1)
    assert abs(result - expected) < 0.001


def test_g_wahr_hydrate_factor_with_purity():
    """Hydrate factor is applied after p_effective."""
    # Raw g_wahr = (2.0/4.0)*99.5 = 49.75 %
    # With factor 210.1/282.1: 49.75 * 0.7448 = 37.05 %
    sample = _make_sample(2.0, 4.0, 99.5, 282.1, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = (2.0 / 4.0) * 99.5 * (210.1 / 282.1)
    assert abs(result - expected) < 0.001


def test_g_wahr_zero_molar_mass_guard():
    """Guard against division by zero when molar_mass_gmol is 0."""
    sample = _make_sample(2.0, 4.0, 100.0, 0.0, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    # Should fall back to factor=1.0 (no hydrate correction)
    assert abs(result - 50.0) < 0.001


def test_g_wahr_none_molar_mass_guard():
    """Guard against None molar_mass_gmol."""
    sample = _make_sample(2.0, 4.0, 100.0, None, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    assert abs(result - 50.0) < 0.001
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_hydrate_factor.py -v
```

Expected: `test_g_wahr_with_hydrate_factor` and `test_g_wahr_hydrate_factor_with_purity` and guards FAIL (factor not yet applied).

- [ ] **Step 3: Add `anhydrous_molar_mass_gmol` to `Substance` model**

In `models.py`, add after `molar_mass_gmol` (line 113):

```python
anhydrous_molar_mass_gmol = db.Column(db.Float, nullable=True)  # For hydrate correction (e.g. Li citrate tetrahydrat)
```

- [ ] **Step 4: Update `MassBasedEvaluator._g_wahr` in `calculation_modes.py`**

Replace lines 127–130:

```python
def _g_wahr(self, sample) -> float | None:
    if sample.m_s_actual_g is None or sample.m_ges_actual_g is None or sample.m_ges_actual_g <= 0:
        return None
    raw = (sample.m_s_actual_g / sample.m_ges_actual_g) * sample.batch.p_effective
    # Apply hydrate correction if substance has an anhydrous molar mass defined
    substance = sample.batch.analysis.substance
    if (substance is not None
            and substance.anhydrous_molar_mass_gmol is not None
            and substance.molar_mass_gmol is not None
            and substance.molar_mass_gmol > 0):
        raw = raw * (substance.anhydrous_molar_mass_gmol / substance.molar_mass_gmol)
    return raw
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_hydrate_factor.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Run full test suite to check no regressions**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 7: Create Alembic migration**

```bash
flask db revision --autogenerate -m "add_anhydrous_molar_mass_to_substance"
```

Then edit the generated file in `migrations/versions/` to add idempotency guard (follow existing pattern):

```python
def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('substance')}
    if 'anhydrous_molar_mass_gmol' in existing_cols:
        return
    with op.batch_alter_table('substance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('anhydrous_molar_mass_gmol', sa.Float(), nullable=True))
```

- [ ] **Step 8: Apply migration**

```bash
flask db upgrade
```

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add models.py calculation_modes.py migrations/versions/ tests/test_hydrate_factor.py
git commit -m "feat: add hydrate correction factor to substance content calculation"
```

---

### Task 3: Hydrate factor — admin UI

**Files:**
- Modify: `templates/admin/substance_form.html`
- Modify: `app.py` (substance create/edit routes — search for `g_ab_max_pct`)

- [ ] **Step 1: Add field to substance form template**

In `templates/admin/substance_form.html`, after the `molar_mass_gmol` field, add:

```html
<div class="mb-3">
  <label for="anhydrous_molar_mass_gmol" class="form-label">Wasserfreie Molmasse (g/mol)</label>
  <input type="number" step="0.001" class="form-control" id="anhydrous_molar_mass_gmol"
         name="anhydrous_molar_mass_gmol"
         value="{{ substance.anhydrous_molar_mass_gmol if substance.anhydrous_molar_mass_gmol is not none else '' }}">
  <div class="form-text">Nur angeben wenn der Arzneibuch-Gehalt auf die wasserfreie Form bezogen wird
    (z.B. Lithiumcitrat-Tetrahydrat → 210,1 g/mol). Leer lassen bei direkter Bezugnahme.</div>
</div>
```

- [ ] **Step 2: Update substance create/edit routes in `app.py`**

In the substance POST handler (search for `g_ab_min_pct = request.form.get`), add:

```python
anhydrous_raw = request.form.get("anhydrous_molar_mass_gmol", "").strip()
substance.anhydrous_molar_mass_gmol = float(anhydrous_raw) if anhydrous_raw else None
```

- [ ] **Step 3: Manual smoke test**

Start app, go to Admin → Substanzen → edit Lithiumcitrat, enter `210.1` in new field, save. Reload — value persists.

- [ ] **Step 4: Commit**

```bash
git add templates/admin/substance_form.html app.py
git commit -m "feat: add anhydrous molar mass field to substance admin UI"
```

---

### Task 4: Weighing mask — server-side validation fix

**Files:**
- Modify: `app.py:65-110` (`evaluate_weighing_limits`)
- Create: `tests/test_weighing_limits.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_weighing_limits.py`:

```python
"""Tests for weighing limit validation — specifically the new max m_ges constraint."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import MODE_ASSAY_MASS_BASED


def _make_batch(target_m_s_min_g, target_m_ges_g, p_effective, gehalt_min_pct):
    batch = MagicMock()
    batch.target_m_s_min_g = target_m_s_min_g
    batch.target_m_ges_g = target_m_ges_g
    batch.analysis.calculation_mode = MODE_ASSAY_MASS_BASED
    # p_effective from lot
    batch.p_effective = p_effective
    # gehalt_min_pct stored on batch
    batch.gehalt_min_pct = gehalt_min_pct
    return batch


def test_valid_weighing_no_violation(app):
    """m_s = 2.5 g, m_ges = 4.0 g, p_eff=100, p_min=50 → max_ges = 5.0 → ok"""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.0, 4.0, 100.0, 50.0)
        result = evaluate_weighing_limits(batch, 2.5, 4.0)
        assert not result["out_of_range"]
        assert not result["m_ges_max_violation"]


def test_m_s_below_minimum(app):
    """m_s < m_s_min → violation."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.0, 100.0, 50.0)
        result = evaluate_weighing_limits(batch, 2.0, 4.0)
        assert result["out_of_range"]
        assert result["m_s_min_violation"]


def test_m_ges_exceeds_max(app):
    """m_s=2.2, m_ges=7.8, p_eff=100, p_min=50 → max_ges=4.4 → violation"""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, 50.0)
        result = evaluate_weighing_limits(batch, 2.2, 7.8)
        assert result["out_of_range"]
        assert result["m_ges_max_violation"]


def test_m_ges_exactly_at_max(app):
    """m_ges exactly equal to max → no violation."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, 50.0)
        # max = 2.2 * 100.0 / 50.0 = 4.4
        result = evaluate_weighing_limits(batch, 2.2, 4.4)
        assert not result["m_ges_max_violation"]


def test_no_gehalt_min_skips_max_check(app):
    """If gehalt_min_pct is None, skip the max m_ges check."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, None)
        result = evaluate_weighing_limits(batch, 2.2, 99.0)
        assert not result["m_ges_max_violation"]


def test_old_m_ges_minimum_check_removed(app):
    """m_ges below target_m_ges_g is no longer a violation (orientation only)."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 5.0, 100.0, 50.0)
        # m_ges=3.0 < target_m_ges_g=5.0, but m_ges < m_s*p_eff/p_min would be 4.4
        # 3.0 < 4.4, so NOT a max violation either
        result = evaluate_weighing_limits(batch, 2.2, 3.0)
        assert not result.get("m_ges_target_violation", False), \
            "Old minimum check must be removed"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_weighing_limits.py -v
```

Expected: `test_m_ges_exceeds_max`, `test_m_ges_exactly_at_max`, `test_no_gehalt_min_skips_max_check`, and `test_old_m_ges_minimum_check_removed` fail.

- [ ] **Step 3: Update `evaluate_weighing_limits` in `app.py`**

Replace the existing `evaluate_weighing_limits` function (lines 65–110):

```python
def evaluate_weighing_limits(batch: SampleBatch, m_s_actual_g: float | None, m_ges_actual_g: float | None) -> dict:
    """Evaluate whether actual weighing values are within configured limits."""
    mode = resolve_mode(batch.analysis.calculation_mode if batch.analysis else None)
    checks: list[str] = []
    details: dict[str, bool] = {
        "m_s_min_violation": False,
        "m_ges_max_violation": False,
        "volume_range_violation": False,
    }

    if mode == MODE_ASSAY_MASS_BASED:
        # Check minimum substance mass
        if (m_s_actual_g is not None
                and batch.target_m_s_min_g is not None
                and m_s_actual_g < batch.target_m_s_min_g):
            details["m_s_min_violation"] = True
            checks.append(f"m_S {m_s_actual_g:.3f} g < Mindest {batch.target_m_s_min_g:.3f} g")

        # Check maximum total mass: m_ges must not exceed m_s * p_eff / p_min
        # (target_m_ges_g is orientation only — not a hard minimum)
        p_min = batch.gehalt_min_pct
        p_eff = batch.p_effective
        if (m_s_actual_g is not None
                and m_ges_actual_g is not None
                and p_min is not None
                and p_min > 0
                and p_eff > 0):
            m_ges_max = m_s_actual_g * p_eff / p_min
            if m_ges_actual_g > m_ges_max + 1e-9:  # small epsilon for float precision
                details["m_ges_max_violation"] = True
                checks.append(
                    f"m_ges {m_ges_actual_g:.3f} g > Max {m_ges_max:.3f} g "
                    f"(bei m_S={m_s_actual_g:.3f} g, p_eff={p_eff:.1f}%, p_min={p_min:.1f}%)"
                )
    else:
        if (m_ges_actual_g is not None
                and batch.target_v_min_ml is not None
                and batch.target_v_max_ml is not None
                and not (batch.target_v_min_ml <= m_ges_actual_g <= batch.target_v_max_ml)):
            details["volume_range_violation"] = True
            checks.append(
                f"V {m_ges_actual_g:.3f} mL außerhalb Zielbereich "
                f"{batch.target_v_min_ml:.3f}–{batch.target_v_max_ml:.3f} mL"
            )

    return {
        "mode": mode,
        "out_of_range": bool(checks),
        "messages": checks,
        **details,
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_weighing_limits.py tests/test_hydrate_factor.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_weighing_limits.py
git commit -m "fix: replace m_ges minimum check with correct maximum content constraint"
```

---

### Task 5: Weighing mask — frontend live calculation

**Files:**
- Modify: `templates/ta/weighing.html`

- [ ] **Step 1: Read current weighing template to understand structure**

```bash
# Just read the file before editing
```

Read `templates/ta/weighing.html` fully before making changes.

- [ ] **Step 2: Add orientation columns and live max calculation JS**

The template renders a table with one row per sample. For each sample row:

**In the table header**, add a column „Max. m_ges" after the existing m_ges column.

**Pass batch data to the template** — in the weighing route in `app.py`, ensure the template receives `batch.gehalt_min_pct` and `batch.p_effective`. These should already be accessible via `batch` in the template.

**In each sample row**, add after the m_ges input:

```html
<td>
  <span id="max_mges_{{ sample.id }}" class="fw-bold text-secondary">—</span>
</td>
```

**Add JS block** at the bottom of the template (before `{% endblock %}`):

```html
<script>
(function() {
  const pEff = {{ batch.p_effective | tojson }};
  const pMin = {{ batch.gehalt_min_pct | tojson }};  // may be null
  const mSMin = {{ batch.target_m_s_min_g | tojson }};

  function calcMaxMges(mS) {
    if (!pMin || pMin <= 0 || !pEff || pEff <= 0 || !mS || mS <= 0) return null;
    return mS * pEff / pMin;
  }

  function updateRow(sampleId) {
    const msInput = document.getElementById('m_s_' + sampleId);
    const mgesInput = document.getElementById('m_ges_' + sampleId);
    const maxSpan = document.getElementById('max_mges_' + sampleId);
    if (!msInput || !maxSpan) return;

    const mS = parseFloat(msInput.value.replace(',', '.'));
    const mGes = parseFloat(mgesInput ? mgesInput.value.replace(',', '.') : 'NaN');
    const maxMges = calcMaxMges(mS);

    if (maxMges !== null && !isNaN(maxMges)) {
      maxSpan.textContent = maxMges.toFixed(3).replace('.', ',') + ' g';
      if (!isNaN(mGes) && mGes > maxMges + 0.0001) {
        maxSpan.classList.replace('text-secondary', 'text-danger');
        maxSpan.classList.add('fw-bold');
        mgesInput && mgesInput.classList.add('is-invalid');
      } else {
        maxSpan.classList.replace('text-danger', 'text-success');
        mgesInput && mgesInput.classList.remove('is-invalid');
      }
    } else {
      maxSpan.textContent = '—';
      maxSpan.className = 'fw-bold text-secondary';
    }
  }

  // Wire up all sample inputs
  document.querySelectorAll('[id^="m_s_"], [id^="m_ges_"]').forEach(function(input) {
    const parts = input.id.split('_');
    const sampleId = parts[parts.length - 1];
    input.addEventListener('input', function() { updateRow(sampleId); });
    input.addEventListener('change', function() { updateRow(sampleId); });
  });

  // Init on page load
  document.querySelectorAll('[id^="m_s_"]').forEach(function(input) {
    const parts = input.id.split('_');
    updateRow(parts[parts.length - 1]);
  });

  // Show orientation in table header or a helper text
  {% if mSMin and batch.target_m_ges_g %}
  const orientText = document.getElementById('weighing-orientation');
  if (orientText) {
    const maxAtMin = calcMaxMges({{ batch.target_m_s_min_g | tojson }});
    orientText.textContent =
      'Orientierung: m_S,min = {{ "%.3f"|format(batch.target_m_s_min_g) }} g · ' +
      'm_ges Richtwert = {{ "%.3f"|format(batch.target_m_ges_g) }} g · ' +
      'Max. m_ges bei m_S,min = ' + (maxAtMin ? maxAtMin.toFixed(3).replace('.', ',') + ' g' : '—');
  }
  {% endif %}
})();
</script>
```

**Add orientation banner** above the table:

```html
<div class="alert alert-info py-2 small" id="weighing-orientation"></div>
```

- [ ] **Step 3: Manual test**

Start app, navigate to weighing form for a batch with `gehalt_min_pct` set. Enter a substance mass, observe Max. m_ges column updating. Enter an m_ges that exceeds the max — input turns red.

- [ ] **Step 4: Commit**

```bash
git add templates/ta/weighing.html
git commit -m "feat: add live max m_ges calculation to weighing mask"
```

---

### Task 6: Flatpickr date format

**Files:**
- Modify: `templates/base.html`
- Modify: `app.py` (add `parse_de_date`, update date handling in POST routes)
- Modify: all templates with `type="date"` inputs

- [ ] **Step 1: Find all date inputs**

```bash
grep -rn 'type="date"' templates/
```

Note all file paths and line numbers.

- [ ] **Step 2: Add Flatpickr to `base.html`**

In the `<head>` section of `templates/base.html`, add after existing CSS links:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
```

Before `</body>`, add:

```html
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/de.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    flatpickr('.flatpickr-date', {
      locale: 'de',
      dateFormat: 'd.m.Y',
      allowInput: true,
    });
  });
</script>
```

- [ ] **Step 3: Replace all `type="date"` inputs in templates**

For each template found in Step 1, change:

```html
<input type="date" ... value="{{ some_date | de_date }}">
```

To:

```html
<input type="text" class="form-control flatpickr-date" ... value="{{ some_date | de_date }}">
```

If the value is already in ISO format stored in the model, ensure `de_date` filter is applied to convert `YYYY-MM-DD` → `DD.MM.YYYY` for display/pre-fill.

- [ ] **Step 4: Write tests for `parse_de_date`**

Add to `tests/test_weighing_limits.py` (or a new `tests/test_utils.py`):

```python
def test_parse_de_date_valid():
    from app import parse_de_date
    assert parse_de_date("14.10.2026") == "2026-10-14"

def test_parse_de_date_iso_passthrough():
    from app import parse_de_date
    assert parse_de_date("2026-10-14") == "2026-10-14"

def test_parse_de_date_blank():
    from app import parse_de_date
    assert parse_de_date("") is None
    assert parse_de_date(None) is None

def test_parse_de_date_invalid():
    from app import parse_de_date
    assert parse_de_date("not-a-date") is None
```

Run these tests after implementing `parse_de_date` in Step 5 to confirm they pass.

- [ ] **Step 5: Add `parse_de_date` helper in `app.py`**

After the existing `de_date_filter` function (around line 184), add:

```python
def parse_de_date(s: str | None) -> str | None:
    """Convert DD.MM.YYYY string to ISO YYYY-MM-DD for DB storage.
    Returns None if blank or invalid. Accepts ISO format passthrough."""
    if not s or not s.strip():
        return None
    s = s.strip()
    # Already ISO?
    if len(s) == 10 and s[4] == '-':
        return s
    parts = s.split('.')
    if len(parts) == 3:
        try:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None
    return None
```

- [ ] **Step 5: Update POST routes that save dates**

Search for all `request.form.get` calls that store dates (e.g. `weighed_date`, `scheduled_date`, `receipt_date`, `preparation_date`, etc.) and wrap with `parse_de_date()`:

```python
# Before:
sample.weighed_date = request.form.get("weighed_date", "")
# After:
sample.weighed_date = parse_de_date(request.form.get("weighed_date", ""))
```

Run:

```bash
grep -n "weighed_date\|scheduled_date\|receipt_date\|coa_date\|preparation_date\|start_date\|end_date\|assigned_date\|g_analytical_date\|coa_valid_until\|titer_source_date" app.py | grep "request.form"
```

Update all matches.

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 7: Manual smoke test**

Open a form with a date field. Flatpickr calendar should open, German locale shown, date displayed as DD.MM.YYYY.

- [ ] **Step 8: Commit**

```bash
git add templates/ app.py
git commit -m "feat: replace date inputs with Flatpickr (DD.MM.YYYY everywhere)"
```

---

### Task 7: Verschnitt placeholder fix

**Files:**
- Modify: `templates/admin/batch_form.html`

- [ ] **Step 1: Find and fix the placeholder**

```bash
grep -n "Acetylsalicyl" templates/admin/batch_form.html
```

Change the placeholder to:

```html
placeholder="z.B. Mannitol"
```

- [ ] **Step 2: Commit**

```bash
git add templates/admin/batch_form.html
git commit -m "fix: correct Verschnitt placeholder text in batch form"
```

---

## Phase 2 — New Features

---

### Task 8: Colloquium model + migrations

**Files:**
- Modify: `models.py` (add `Colloquium` class, add `Student.is_excluded`)
- Create: `migrations/versions/<hash>_add_colloquium_and_is_excluded.py`
- Create: `tests/test_colloquium.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_colloquium.py`:

```python
"""Tests for Colloquium model and exclusion logic."""
import pytest
from models import Colloquium, Student, Block, Semester


def _make_fixtures(db):
    """Create self-contained Block + Semester + Student for each test."""
    import uuid
    code = uuid.uuid4().hex[:8]
    block = Block(code=code[:3], name=f"TestBlock-{code}")
    sem = Semester(code=f"T-{code}", name="Test", is_active=False)
    db.session.add_all([block, sem])
    db.session.flush()
    student = Student(semester_id=sem.id, matrikel=code[:8],
                      last_name="Tester", first_name="Test", running_number=1)
    db.session.add(student)
    db.session.flush()
    return block, sem, student


def test_colloquium_status_pending(db):
    """passed=None + scheduled_date → Geplant."""
    block, sem, student = _make_fixtures(db)
    c = Colloquium(student_id=student.id, block_id=block.id, attempt_number=1,
                   scheduled_date="2026-10-14")
    db.session.add(c)
    db.session.commit()
    assert c.passed is None
    assert c.status_label == "Geplant"


def test_colloquium_status_passed(db):
    """passed=True → Bestanden."""
    block, sem, student = _make_fixtures(db)
    c = Colloquium(student_id=student.id, block_id=block.id, attempt_number=1,
                   passed=True, conducted_date="2026-10-14")
    db.session.add(c)
    db.session.commit()
    assert c.status_label == "Bestanden"


def test_colloquium_status_failed(db):
    """passed=False → Nicht bestanden."""
    block, sem, student = _make_fixtures(db)
    c = Colloquium(student_id=student.id, block_id=block.id, attempt_number=2,
                   passed=False, conducted_date="2026-10-21")
    db.session.add(c)
    db.session.commit()
    assert c.status_label == "Nicht bestanden"


def test_student_is_excluded_default_false(db):
    """New students have is_excluded=False."""
    _, sem, student = _make_fixtures(db)
    assert student.is_excluded is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_colloquium.py -v
```

Expected: ImportError or AttributeError (model not yet created).

- [ ] **Step 3: Add `Colloquium` model and `Student.is_excluded` to `models.py`**

After `Student` class, add `Colloquium`:

```python
class Colloquium(db.Model):
    __tablename__ = "colloquium"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    scheduled_date = db.Column(db.String(20), nullable=True)
    conducted_date = db.Column(db.String(20), nullable=True)
    examiner = db.Column(db.String(200), nullable=True)
    passed = db.Column(db.Boolean, nullable=True)  # None = not yet held
    notes = db.Column(db.Text, nullable=True)

    student = db.relationship("Student", back_populates="colloquiums")
    block = db.relationship("Block", back_populates="colloquiums")

    __table_args__ = (
        db.UniqueConstraint("student_id", "block_id", "attempt_number"),
    )

    @property
    def status_label(self) -> str:
        if self.passed is True:
            return "Bestanden"
        if self.passed is False:
            return "Nicht bestanden"
        if self.scheduled_date:
            return "Geplant"
        return "Nicht geplant"

    @property
    def attempt_label(self) -> str:
        labels = {1: "Erstversuch", 2: "Nachholkolloquium", 3: "beim Chef"}
        return labels.get(self.attempt_number, f"Versuch {self.attempt_number}")
```

Add `is_excluded` to `Student` (after `group_code`):

```python
is_excluded = db.Column(db.Boolean, nullable=False, default=False)
```

Add back-references to `Student` and `Block`:

In `Student`, add:
```python
colloquiums = db.relationship("Colloquium", back_populates="student", cascade="all, delete-orphan")
```

In `Block`, add:
```python
colloquiums = db.relationship("Colloquium", back_populates="block")
```

Update `app.py` import line to include `Colloquium` and `ProtocolCheck` if not already there.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_colloquium.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Create migration**

```bash
flask db revision --autogenerate -m "add_colloquium_and_is_excluded"
```

Edit to add idempotency:

```python
def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    existing_student_cols = {col['name'] for col in inspector.get_columns('student')}

    if 'colloquium' not in existing_tables:
        op.create_table('colloquium',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('student_id', sa.Integer(), nullable=False),
            sa.Column('block_id', sa.Integer(), nullable=False),
            sa.Column('attempt_number', sa.Integer(), nullable=False),
            sa.Column('scheduled_date', sa.String(20), nullable=True),
            sa.Column('conducted_date', sa.String(20), nullable=True),
            sa.Column('examiner', sa.String(200), nullable=True),
            sa.Column('passed', sa.Boolean(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['student_id'], ['student.id']),
            sa.ForeignKeyConstraint(['block_id'], ['block.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('student_id', 'block_id', 'attempt_number'),
        )

    if 'is_excluded' not in existing_student_cols:
        with op.batch_alter_table('student', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_excluded', sa.Boolean(), nullable=False, server_default='0'))
```

- [ ] **Step 7: Apply migration**

```bash
flask db upgrade
```

- [ ] **Step 8: Commit**

```bash
git add models.py migrations/versions/ tests/test_colloquium.py
git commit -m "feat: add Colloquium model and Student.is_excluded field"
```

---

### Task 9: Colloquium routes + templates

**Files:**
- Modify: `app.py` (add colloquium routes)
- Create: `templates/colloquium/overview.html`
- Create: `templates/colloquium/plan_form.html`
- Modify: `templates/base.html` (add nav links)

- [ ] **Step 1: Add colloquium routes to `app.py`**

Add after existing routes (before the `if __name__ == "__main__"` block):

```python
# ── Kolloquien ────────────────────────────────────────────────────────────

@app.route("/colloquium/")
def colloquium_overview():
    semester = Semester.query.filter_by(is_active=True).first()
    if not semester:
        flash("Kein aktives Semester.", "warning")
        return redirect(url_for("home"))
    blocks = Block.query.order_by(Block.id).all()
    active_block_id = request.args.get("block_id", type=int) or (blocks[0].id if blocks else None)
    students = Student.query.filter_by(semester_id=semester.id, is_excluded=False)\
        .order_by(Student.last_name, Student.first_name).all()
    # Build colloquium map: {student_id: {block_id: [Colloquium]}}
    all_colloqs = Colloquium.query.filter(
        Colloquium.student_id.in_([s.id for s in students])
    ).all()
    colloq_map = {}
    for c in all_colloqs:
        colloq_map.setdefault(c.student_id, {}).setdefault(c.block_id, []).append(c)
    for bid in colloq_map.values():
        for attempts in bid.values():
            attempts.sort(key=lambda x: x.attempt_number)
    return render_template("colloquium/overview.html",
        semester=semester, blocks=blocks, active_block_id=active_block_id,
        students=students, colloq_map=colloq_map)


@app.route("/colloquium/plan", methods=["GET", "POST"])
def colloquium_plan():
    """Create or update a single colloquium entry."""
    semester = Semester.query.filter_by(is_active=True).first()
    blocks = Block.query.order_by(Block.id).all()
    students = Student.query.filter_by(semester_id=semester.id if semester else 0)\
        .order_by(Student.last_name).all()

    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        block_id = request.form.get("block_id", type=int)
        attempt_number = request.form.get("attempt_number", type=int, default=1)
        colloq = Colloquium.query.filter_by(
            student_id=student_id, block_id=block_id, attempt_number=attempt_number
        ).first() or Colloquium(student_id=student_id, block_id=block_id, attempt_number=attempt_number)
        colloq.scheduled_date = parse_de_date(request.form.get("scheduled_date"))
        colloq.conducted_date = parse_de_date(request.form.get("conducted_date"))
        colloq.examiner = request.form.get("examiner", "").strip() or None
        passed_raw = request.form.get("passed")
        colloq.passed = True if passed_raw == "true" else (False if passed_raw == "false" else None)
        colloq.notes = request.form.get("notes", "").strip() or None
        db.session.add(colloq)

        # Handle exclusion after attempt 3 failure
        if colloq.attempt_number == 3 and colloq.passed is False:
            student = db.session.get(Student, student_id)
            if student:
                student.is_excluded = True
                open_assignments = SampleAssignment.query.filter_by(
                    student_id=student_id, status="assigned"
                ).all()
                for a in open_assignments:
                    a.status = "cancelled"
                flash(f"{student.full_name} hat das Kolloquium dreimal nicht bestanden und scheidet aus dem Praktikum aus.", "danger")

        db.session.commit()
        flash("Kolloquium gespeichert.", "success")
        return redirect(url_for("colloquium_overview"))

    # Pre-fill from query params
    preselect_student = request.args.get("student_id", type=int)
    preselect_block = request.args.get("block_id", type=int)
    preselect_attempt = request.args.get("attempt_number", type=int, default=1)
    return render_template("colloquium/plan_form.html",
        blocks=blocks, students=students,
        preselect_student=preselect_student, preselect_block=preselect_block,
        preselect_attempt=preselect_attempt)
```

- [ ] **Step 2: Create `templates/colloquium/overview.html`**

```bash
mkdir -p templates/colloquium
```

```html
{% extends "base.html" %}
{% block title %}Kolloquien{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h1 class="h3">Kolloquien — {{ semester.name }}</h1>
  <a href="{{ url_for('colloquium_plan') }}" class="btn btn-primary btn-sm">+ Kolloquium planen</a>
</div>

{# Block tabs #}
<ul class="nav nav-tabs mb-3">
  {% for block in blocks %}
  <li class="nav-item">
    <a class="nav-link {% if block.id == active_block_id %}active{% endif %}"
       href="{{ url_for('colloquium_overview', block_id=block.id) }}">
      Block {{ block.code }}
    </a>
  </li>
  {% endfor %}
</ul>

<table class="table table-sm table-hover">
  <thead class="table-light">
    <tr>
      <th>Studierende/r</th>
      <th>Gr.</th>
      <th class="text-center">Versuch 1</th>
      <th class="text-center">Versuch 2 (Nachholkoll.)</th>
      <th class="text-center">Versuch 3 (Chef)</th>
      <th class="text-center">Status</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for student in students %}
    {% set attempts = colloq_map.get(student.id, {}).get(active_block_id, []) %}
    {% set by_attempt = {} %}
    {% for a in attempts %}{% set _ = by_attempt.update({a.attempt_number: a}) %}{% endfor %}
    <tr>
      <td>{{ student.full_name }}</td>
      <td>{{ student.group_code or '—' }}</td>
      {% for n in [1, 2, 3] %}
      {% set c = by_attempt.get(n) %}
      <td class="text-center">
        {% if c %}
          {% if c.passed is true %}
            <span class="badge bg-success">✓ {{ c.conducted_date | de_date }}</span>
          {% elif c.passed is false %}
            <span class="badge bg-danger">✗ {{ c.conducted_date | de_date }}</span>
          {% elif c.scheduled_date %}
            <span class="badge bg-warning text-dark">📅 {{ c.scheduled_date | de_date }}</span>
          {% endif %}
        {% else %}
          <span class="text-muted">—</span>
        {% endif %}
      </td>
      {% endfor %}
      <td class="text-center">
        {% set all_passed = by_attempt.values() | selectattr('passed', 'equalto', True) | list %}
        {% if all_passed %}
          <span class="badge bg-success">Bestanden</span>
        {% elif by_attempt.get(3) and by_attempt[3].passed is false %}
          <span class="badge bg-danger">Ausgeschieden</span>
        {% elif attempts %}
          <span class="badge bg-warning text-dark">Ausstehend</span>
        {% else %}
          <span class="badge bg-secondary">Nicht geplant</span>
        {% endif %}
      </td>
      <td>
        <a href="{{ url_for('colloquium_plan', student_id=student.id, block_id=active_block_id) }}"
           class="btn btn-outline-secondary btn-sm">Bearbeiten</a>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 3: Create `templates/colloquium/plan_form.html`**

```html
{% extends "base.html" %}
{% block title %}Kolloquium planen{% endblock %}
{% block content %}
<h1 class="h3 mb-3">Kolloquium planen / Ergebnis eintragen</h1>
<form method="POST">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="mb-3">
    <label class="form-label">Studierende/r</label>
    <select name="student_id" class="form-select" required>
      <option value="">— bitte wählen —</option>
      {% for s in students %}
      <option value="{{ s.id }}" {% if s.id == preselect_student %}selected{% endif %}>
        {{ s.full_name }} ({{ s.matrikel }})
      </option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">Block</label>
    <select name="block_id" class="form-select" required>
      {% for b in blocks %}
      <option value="{{ b.id }}" {% if b.id == preselect_block %}selected{% endif %}>
        Block {{ b.code }} — {{ b.name }}
      </option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">Versuch</label>
    <select name="attempt_number" class="form-select">
      <option value="1" {% if preselect_attempt == 1 %}selected{% endif %}>1 — Erstversuch</option>
      <option value="2" {% if preselect_attempt == 2 %}selected{% endif %}>2 — Nachholkolloquium</option>
      <option value="3" {% if preselect_attempt == 3 %}selected{% endif %}>3 — beim Chef</option>
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">Geplantes Datum</label>
    <input type="text" name="scheduled_date" class="form-control flatpickr-date">
  </div>
  <div class="mb-3">
    <label class="form-label">Tatsächliches Datum</label>
    <input type="text" name="conducted_date" class="form-control flatpickr-date">
  </div>
  <div class="mb-3">
    <label class="form-label">Prüfer/in</label>
    <input type="text" name="examiner" class="form-control">
  </div>
  <div class="mb-3">
    <label class="form-label">Ergebnis</label>
    <select name="passed" class="form-select">
      <option value="">— noch ausstehend —</option>
      <option value="true">Bestanden</option>
      <option value="false">Nicht bestanden</option>
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">Anmerkungen</label>
    <textarea name="notes" class="form-control" rows="2"></textarea>
  </div>
  <button type="submit" class="btn btn-primary">Speichern</button>
  <a href="{{ url_for('colloquium_overview') }}" class="btn btn-outline-secondary">Abbrechen</a>
</form>
{% endblock %}
```

- [ ] **Step 4: Add nav links in `templates/base.html`**

In the navbar, add a "Kolloquien" link in both the Admin section and Praktikum section:

```html
<a class="nav-link" href="{{ url_for('colloquium_overview') }}">Kolloquien</a>
```

- [ ] **Step 5: Update `app.py` imports**

Add `Colloquium` to the import from models.

- [ ] **Step 6: Guard assignment creation for excluded students**

In `app.py`, find the route that creates `SampleAssignment` records (search for `SampleAssignment(` in POST handlers). At the top of that handler, add:

```python
student = db.session.get(Student, student_id)
if student and student.is_excluded:
    flash(f"{student.full_name} ist aus dem Praktikum ausgeschieden. Keine neue Zuweisung möglich.", "danger")
    return redirect(request.referrer or url_for("home"))
```

- [ ] **Step 7: Add excluded badge to student list template**

In `templates/admin/students.html`, in the student name/row cell, add after the student name:

```html
{% if student.is_excluded %}
  <span class="badge bg-danger ms-1">Ausgeschieden</span>
{% endif %}
```

- [ ] **Step 8: Smoke test**

Start app, navigate to `/colloquium/`. Verify the overview loads. Plan a colloquium, save it, verify it appears in the table.

- [ ] **Step 9: Commit**

```bash
git add app.py templates/colloquium/ templates/base.html templates/admin/students.html
git commit -m "feat: add colloquium tracking UI (overview + plan/record form + exclusion guard)"
```

---

### Task 10: Auto group assignment

**Files:**
- Modify: `app.py` (add 2 routes: auto-assign preview + save, clear-all)
- Create: `templates/admin/auto_group_preview.html`
- Modify: `templates/admin/students.html`
- Create: `tests/test_auto_groups.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_auto_groups.py`:

```python
"""Tests for auto group assignment algorithm."""
import pytest
from models import GROUP_CODES


def _make_students(names):
    """Create mock students with last_name and group_code=None."""
    from unittest.mock import MagicMock
    students = []
    for name in names:
        s = MagicMock()
        s.last_name = name
        s.group_code = None
        students.append(s)
    return students


def _auto_assign(students, active_group_count=4):
    """Mirror of the algorithm to be implemented."""
    groups = GROUP_CODES[:active_group_count]
    unassigned = [s for s in students if s.group_code is None]
    unassigned.sort(key=lambda s: s.last_name.lower())
    assignments = {}
    for i, student in enumerate(unassigned):
        assignments[id(student)] = groups[i % len(groups)]
    return assignments


def test_round_robin_distribution():
    students = _make_students(["Ziegler", "Bauer", "Meyer", "Fischer"])
    result = _auto_assign(students)
    # Sorted: Bauer, Fischer, Meyer, Ziegler → A, B, C, D
    by_name = {s.last_name: result[id(s)] for s in students}
    assert by_name["Bauer"] == "A"
    assert by_name["Fischer"] == "B"
    assert by_name["Meyer"] == "C"
    assert by_name["Ziegler"] == "D"


def test_already_assigned_skipped():
    from unittest.mock import MagicMock
    s1 = MagicMock(); s1.last_name = "Bauer"; s1.group_code = "A"  # already assigned
    s2 = MagicMock(); s2.last_name = "Fischer"; s2.group_code = None
    result = _auto_assign([s1, s2])
    assert id(s1) not in result  # s1 skipped
    assert result[id(s2)] == "A"  # only s2 assigned, gets first group


def test_active_group_count_respected():
    students = _make_students(["A", "B", "C", "D", "E"])
    result = _auto_assign(students, active_group_count=3)
    groups_used = set(result.values())
    assert groups_used == {"A", "B", "C"}
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_auto_groups.py -v
```

Expected: all pass (algorithm is pure Python, no Flask needed).

- [ ] **Step 3: Add `active_group_count` to `Semester` and `max_days` to `Block` in `models.py`**

In `models.py`, `Semester` class, add:

```python
active_group_count = db.Column(db.Integer, nullable=False, default=4)
```

In `models.py`, `Block` class, add after `name`:

```python
max_days = db.Column(db.Integer, nullable=True)  # Orientation value; not a hard constraint
```

- [ ] **Step 4: Create migration for `Semester.active_group_count` and `Block.max_days`**

```bash
flask db revision --autogenerate -m "add_block_max_days_and_semester_group_count"
```

Edit with idempotency (check columns before adding):

```python
def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    semester_cols = {c['name'] for c in inspector.get_columns('semester')}
    block_cols = {c['name'] for c in inspector.get_columns('block')}

    if 'active_group_count' not in semester_cols:
        with op.batch_alter_table('semester', schema=None) as batch_op:
            batch_op.add_column(sa.Column('active_group_count', sa.Integer(), nullable=False, server_default='4'))

    if 'max_days' not in block_cols:
        with op.batch_alter_table('block', schema=None) as batch_op:
            batch_op.add_column(sa.Column('max_days', sa.Integer(), nullable=True))
```

```bash
flask db upgrade
```

- [ ] **Step 5: Add auto-assign routes to `app.py`**

```python
@app.route("/admin/students/<int:semester_id>/auto-assign-groups", methods=["GET", "POST"])
def auto_assign_groups(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    students_all = Student.query.filter_by(semester_id=semester_id)\
        .order_by(Student.last_name, Student.first_name).all()
    unassigned = [s for s in students_all if not s.group_code]

    active_count = semester.active_group_count or 4
    groups = GROUP_CODES[:active_count]

    if request.method == "POST":
        # Save assignments from form
        for student in unassigned:
            new_group = request.form.get(f"group_{student.id}", "").strip()
            if new_group in groups:
                student.group_code = new_group
        db.session.commit()
        flash(f"Gruppen für {len(unassigned)} Studierende gespeichert.", "success")
        return redirect(url_for("admin_students", semester_id=semester_id))

    # Compute preview
    unassigned_sorted = sorted(unassigned, key=lambda s: s.last_name.lower())
    proposals = {s.id: groups[i % len(groups)] for i, s in enumerate(unassigned_sorted)}
    return render_template("admin/auto_group_preview.html",
        semester=semester, students=unassigned_sorted, proposals=proposals, groups=groups)


@app.route("/admin/students/<int:semester_id>/clear-groups", methods=["POST"])
def clear_all_groups(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    Student.query.filter_by(semester_id=semester_id).update({"group_code": None})
    db.session.commit()
    flash("Alle Gruppen-Zuteilungen gelöscht.", "success")
    return redirect(url_for("admin_students", semester_id=semester_id))
```

- [ ] **Step 6: Create `templates/admin/auto_group_preview.html`**

```html
{% extends "base.html" %}
{% block title %}Gruppen auto-zuteilen{% endblock %}
{% block content %}
<h2 class="h4 mb-3">Gruppen auto-zuteilen — {{ semester.name }}</h2>
<p class="text-muted">{{ students|length }} ungruppiete Studierende · alphabetisch nach Nachname sortiert · editierbar vor dem Speichern</p>
<form method="POST">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <table class="table table-sm">
    <thead class="table-light">
      <tr><th>Nachname, Vorname</th><th>Matrikel</th><th>Gruppe</th></tr>
    </thead>
    <tbody>
      {% for student in students %}
      <tr>
        <td>{{ student.full_name }}</td>
        <td>{{ student.matrikel }}</td>
        <td>
          <select name="group_{{ student.id }}" class="form-select form-select-sm" style="width:80px">
            {% for g in groups %}
            <option value="{{ g }}" {% if proposals[student.id] == g %}selected{% endif %}>{{ g }}</option>
            {% endfor %}
          </select>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <button type="submit" class="btn btn-success">💾 Zuteilung speichern</button>
  <a href="{{ url_for('admin_students', semester_id=semester.id) }}" class="btn btn-outline-secondary">Abbrechen</a>
</form>
{% endblock %}
```

- [ ] **Step 7: Add buttons to `templates/admin/students.html`**

Find the button group in the students list header and add:

```html
<a href="{{ url_for('auto_assign_groups', semester_id=semester.id) }}"
   class="btn btn-outline-success btn-sm">⚡ Gruppen auto-zuteilen</a>
<form method="POST" action="{{ url_for('clear_all_groups', semester_id=semester.id) }}"
      style="display:inline"
      onsubmit="return confirm('Alle Gruppen-Zuteilungen für {{ students|length }} Studierende löschen?')">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <button type="submit" class="btn btn-outline-danger btn-sm">🗑 Alle Gruppen löschen</button>
</form>
```

- [ ] **Step 8: Smoke test**

Import students without groups, click auto-assign, verify preview, save. Then click clear groups, confirm dialog, verify all group_codes are NULL.

- [ ] **Step 9: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 10: Commit**

```bash
git add app.py models.py migrations/versions/ templates/admin/ tests/test_auto_groups.py
git commit -m "feat: add auto group assignment and clear-groups functionality"
```

---

### Task 11: Block configurability

**Files:**
- Modify: `models.py` (`Block.max_days` — already added in Task 10 migration)
- Modify: `app.py` (add block list/edit/create/delete routes)
- Modify: `templates/admin/practical_day_form.html` (free day number input)
- Create: `templates/admin/blocks.html`
- Create: `templates/admin/block_form.html`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_auto_groups.py` (or a new `tests/test_block_admin.py`):

```python
def test_block_list_route(client):
    resp = client.get("/admin/blocks")
    assert resp.status_code == 200

def test_block_edit_updates_max_days(client, db):
    from models import Block
    block = Block.query.first()
    assert block is not None
    resp = client.post(f"/admin/blocks/{block.id}/edit",
                       data={"name": block.name, "code": block.code, "max_days": "6"},
                       follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire(block)
    assert block.max_days == 6

def test_block_delete_blocked_with_practical_days(client, db):
    """Deleting a block with linked practical days must be refused."""
    from models import Block, PracticalDay, Semester
    # Use first block that has no practical days
    block = Block(code="ZZ", name="TestDeleteBlock")
    db.session.add(block)
    db.session.commit()
    resp = client.post(f"/admin/blocks/{block.id}/delete", follow_redirects=True)
    assert resp.status_code == 200  # succeeds — no linked days
```

Run: `pytest tests/test_block_admin.py -v` — expected FAIL (routes not yet defined).

- [ ] **Step 2: Add block routes to `app.py`**

```python
@app.route("/admin/blocks")
def admin_blocks():
    blocks = Block.query.order_by(Block.id).all()
    return render_template("admin/blocks.html", blocks=blocks)

@app.route("/admin/blocks/new", methods=["GET", "POST"])
@app.route("/admin/blocks/<int:block_id>/edit", methods=["GET", "POST"])
def edit_block(block_id=None):
    block = Block.query.get_or_404(block_id) if block_id else Block()
    if request.method == "POST":
        block.name = request.form.get("name", "").strip()
        block.code = request.form.get("code", "").strip()
        max_days_raw = request.form.get("max_days", "").strip()
        block.max_days = int(max_days_raw) if max_days_raw else None
        if block_id is None:
            db.session.add(block)
        db.session.commit()
        flash("Block gespeichert.", "success")
        return redirect(url_for("admin_blocks"))
    return render_template("admin/block_form.html", block=block)

@app.route("/admin/blocks/<int:block_id>/delete", methods=["POST"])
def delete_block(block_id):
    block = Block.query.get_or_404(block_id)
    if block.analyses or PracticalDay.query.filter_by(block_id=block.id).first():
        flash("Block kann nicht gelöscht werden — es sind Analysen oder Praktikumstage verknüpft.", "danger")
        return redirect(url_for("admin_blocks"))
    db.session.delete(block)
    db.session.commit()
    flash("Block gelöscht.", "success")
    return redirect(url_for("admin_blocks"))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_block_admin.py -v
```

Expected: all pass.

- [ ] **Step 5: Create `templates/admin/blocks.html` and `templates/admin/block_form.html`**

```html
{% extends "base.html" %}
{% block title %}Block bearbeiten{% endblock %}
{% block content %}
<h2 class="h4 mb-3">Block bearbeiten</h2>
<form method="POST">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="mb-3">
    <label class="form-label">Kürzel (z.B. I)</label>
    <input type="text" name="code" class="form-control" value="{{ block.code }}" required maxlength="10">
  </div>
  <div class="mb-3">
    <label class="form-label">Name (z.B. Acidimetrie)</label>
    <input type="text" name="name" class="form-control" value="{{ block.name }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">Max. Tage (Orientierung, optional)</label>
    <input type="number" name="max_days" class="form-control" min="1"
           value="{{ block.max_days if block.max_days is not none else '' }}">
    <div class="form-text">Richtwert für die Planung. Kein hartes Limit.</div>
  </div>
  <button type="submit" class="btn btn-primary">Speichern</button>
  <a href="{{ url_for('admin_blocks') }}" class="btn btn-outline-secondary">Abbrechen</a>
</form>
{% endblock %}
```

- [ ] **Step 6: Fix day number in `templates/admin/practical_day_form.html`**

Find the `block_day_number` input. Replace any `<select>` with options 1–4 with:

```html
<input type="number" name="block_day_number" class="form-control" min="1"
       value="{{ day.block_day_number if day else '' }}" required>
```

- [ ] **Step 7: Add "Blöcke verwalten" link to admin nav**

In `templates/base.html`, add:
```html
<a class="dropdown-item" href="{{ url_for('admin_blocks') }}">Blöcke</a>
```

- [ ] **Step 8: Smoke test**

Go to Admin → Blöcke, edit Block I, change `max_days` to 5, save. Verify persists.
Create a PracticalDay with `block_day_number = 6` — verify it saves without error.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin/ templates/base.html
git commit -m "feat: add block admin UI (create/edit/delete) and remove day number 1-4 restriction"
```

---

## Phase 3 — UX Improvements

---

### Task 12: V Lösung / V Aliquot — `aliquot_enabled` flag

**Files:**
- Modify: `models.py` (`Method.aliquot_enabled`, update `has_aliquot`, `aliquot_fraction`)
- Modify: `calculation_modes.py` (`MassBasedEvaluator._aliquot_fraction`)
- Modify: `app.py` (`_validate_aliquot`)
- Create: `migrations/versions/<hash>_add_aliquot_enabled.py`
- Modify: `templates/admin/method_form.html`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_hydrate_factor.py` or create a new `tests/test_aliquot_enabled.py`:

```python
"""Tests for aliquot_enabled flag on Method."""
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample_with_method(aliquot_enabled, v_solution_ml, v_aliquot_ml):
    method = MagicMock()
    method.aliquot_enabled = aliquot_enabled
    method.v_solution_ml = v_solution_ml
    method.v_aliquot_ml = v_aliquot_ml
    analysis = MagicMock()
    analysis.method = method
    analysis.substance = MagicMock()
    analysis.substance.molar_mass_gmol = 100.0
    analysis.substance.anhydrous_molar_mass_gmol = None
    analysis.e_ab_g = None
    batch = MagicMock()
    batch.analysis = analysis
    batch.p_effective = 100.0
    sample = MagicMock()
    sample.batch = batch
    sample.m_s_actual_g = 2.0
    sample.m_ges_actual_g = 4.0
    return sample


def test_aliquot_fraction_when_enabled():
    """aliquot_enabled=True uses v_aliquot_ml / v_solution_ml."""
    sample = _make_sample_with_method(True, 100.0, 20.0)
    ev = MassBasedEvaluator()
    assert abs(ev._aliquot_fraction(sample) - 0.2) < 0.0001


def test_aliquot_fraction_when_disabled():
    """aliquot_enabled=False returns 1.0 even if volumes are set."""
    sample = _make_sample_with_method(False, 100.0, 20.0)
    ev = MassBasedEvaluator()
    assert ev._aliquot_fraction(sample) == 1.0


def test_aliquot_fraction_when_none():
    """aliquot_enabled=None (old data) falls back to volume-based check."""
    sample = _make_sample_with_method(None, 100.0, 20.0)
    ev = MassBasedEvaluator()
    # None should behave like old code: use volumes if set
    assert abs(ev._aliquot_fraction(sample) - 0.2) < 0.0001
```

- [ ] **Step 2: Run tests — confirm `test_aliquot_fraction_when_disabled` fails**

```bash
pytest tests/test_aliquot_enabled.py -v
```

- [ ] **Step 3: Add `aliquot_enabled` to `Method` in `models.py`**

In the `Method` class, add after `v_aliquot_ml`:

```python
aliquot_enabled = db.Column(db.Boolean, nullable=True, default=None)
```

Update `has_aliquot` property:

```python
@property
def has_aliquot(self) -> bool:
    if self.aliquot_enabled is False:
        return False
    return bool(self.v_solution_ml and self.v_aliquot_ml)
```

Update `aliquot_fraction` property:

```python
@property
def aliquot_fraction(self) -> float:
    if self.aliquot_enabled is False:
        return 1.0
    if self.v_solution_ml and self.v_aliquot_ml and self.v_solution_ml > 0:
        return self.v_aliquot_ml / self.v_solution_ml
    return 1.0
```

- [ ] **Step 4: Update `MassBasedEvaluator._aliquot_fraction` in `calculation_modes.py`**

Replace lines 121–125:

```python
def _aliquot_fraction(self, sample) -> float:
    method = sample.batch.analysis.method
    if method is None:
        return 1.0
    if method.aliquot_enabled is False:
        return 1.0
    if method.v_solution_ml and method.v_aliquot_ml and method.v_solution_ml > 0:
        return method.v_aliquot_ml / method.v_solution_ml
    return 1.0
```

- [ ] **Step 5: Update `_validate_aliquot` in `app.py`**

Replace the function:

```python
def _validate_aliquot(method: Method) -> str | None:
    if not method.aliquot_enabled:
        return None  # Fields are disabled — no validation needed
    has_sol = method.v_solution_ml is not None
    has_aliq = method.v_aliquot_ml is not None
    if has_sol != has_aliq:
        return "Kolbenvolumen und Aliquotvolumen müssen beide gesetzt oder beide leer sein."
    if has_sol and has_aliq:
        if method.v_solution_ml <= 0 or method.v_aliquot_ml <= 0:
            return "Kolbenvolumen und Aliquotvolumen müssen größer als 0 sein."
        if method.v_aliquot_ml > method.v_solution_ml:
            return "Aliquotvolumen darf nicht größer als Kolbenvolumen sein."
    return None
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 7: Create migration with data backfill**

```bash
flask db revision --autogenerate -m "add_aliquot_enabled_to_method"
```

Edit the migration:

```python
def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method')}
    if 'aliquot_enabled' in existing_cols:
        return
    with op.batch_alter_table('method', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aliquot_enabled', sa.Boolean(), nullable=True))
    # Backfill: existing methods with both volumes set → aliquot_enabled = True
    conn.execute(sa.text(
        "UPDATE method SET aliquot_enabled = 1 "
        "WHERE v_solution_ml IS NOT NULL AND v_aliquot_ml IS NOT NULL"
    ))
```

```bash
flask db upgrade
```

- [ ] **Step 8: Update method form template**

In `templates/admin/method_form.html`, find the V Lösung and V Aliquot fields and wrap them with:

```html
<div class="mb-3">
  <div class="form-check">
    <input class="form-check-input" type="checkbox" id="aliquot_enabled"
           name="aliquot_enabled" value="1"
           {% if method.aliquot_enabled %}checked{% endif %}
           onchange="toggleAliquot(this.checked)">
    <label class="form-check-label" for="aliquot_enabled">
      <strong>Aliquotierung verwenden</strong>
    </label>
    <div class="form-text">Wenn aktiviert: Probe wird in einem Messkolben gelöst und davon ein Aliquot für jede Titration entnommen.</div>
  </div>
</div>

<div id="aliquot-fields" {% if not method.aliquot_enabled %}style="display:none"{% endif %}>
  <div class="mb-3">
    <label class="form-label">Kolbenvolumen V<sub>Lösung</sub> (mL)</label>
    <input type="number" step="0.1" name="v_solution_ml" class="form-control"
           value="{{ method.v_solution_ml or '' }}">
    <div class="form-text">Gesamtvolumen des Messkolbens (z.B. 100,0 mL). Bei Rücktitration: Kolbenvolumen <em>nach</em> Zugabe der Vorlage und Auffüllen.</div>
  </div>
  <div class="mb-3">
    <label class="form-label">Aliquotvolumen V<sub>Aliquot</sub> (mL)</label>
    <input type="number" step="0.1" name="v_aliquot_ml" class="form-control"
           value="{{ method.v_aliquot_ml or '' }}">
    <div class="form-text">Volumen des entnommenen Aliquots für jede Titration (z.B. 20,0 mL). Aliquotfaktor = V<sub>Aliquot</sub> / V<sub>Lösung</sub>.</div>
  </div>
</div>

<script>
function toggleAliquot(enabled) {
  document.getElementById('aliquot-fields').style.display = enabled ? '' : 'none';
}
</script>
```

- [ ] **Step 9: Update method POST handler in `app.py`**

In the method save route, handle `aliquot_enabled`:

```python
method.aliquot_enabled = bool(request.form.get("aliquot_enabled"))
if not method.aliquot_enabled:
    method.v_solution_ml = None
    method.v_aliquot_ml = None
else:
    v_sol = request.form.get("v_solution_ml", "").strip()
    v_aliq = request.form.get("v_aliquot_ml", "").strip()
    method.v_solution_ml = float(v_sol) if v_sol else None
    method.v_aliquot_ml = float(v_aliq) if v_aliq else None
```

- [ ] **Step 10: Bug check — verify `v_solution_ml` used in ASS back-titration**

In `calculation_modes.py` lines 151–160, confirm `_v_expected_explicit` for `back` method uses `aliquot_fraction` (which now correctly reflects `aliquot_enabled`). Also check if the legacy `_v_expected_legacy` path for back-titration uses `v_vorlage_ml` directly (line 176) — that is correct and unrelated to V_Lösung.

If `v_solution_ml` is confirmed not used in the `back` calculation path directly (only `aliquot_fraction` is, which is derived from it), the behavior is correct and no silent bug exists. Document this in a code comment.

- [ ] **Step 11: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 12: Smoke test**

Edit an existing method. Toggle aliquot checkbox — fields should show/hide. Uncheck, save — `v_solution_ml` and `v_aliquot_ml` should be NULL in DB.

- [ ] **Step 13: Commit**

```bash
git add models.py calculation_modes.py app.py migrations/versions/ templates/admin/method_form.html tests/test_aliquot_enabled.py
git commit -m "feat: add aliquot_enabled checkbox to method form with clearer labels"
```

---

## Final Verification

- [ ] **Run complete test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Check migrations are all applied**

```bash
flask db current
flask db history
```

Expected: head is at latest migration, no pending upgrades.

- [ ] **Commit any remaining loose files**

```bash
git status
git add -A
git commit -m "chore: final cleanup and verification"
```
