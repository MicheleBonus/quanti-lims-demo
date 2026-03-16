# Quanti-LIMS – Internship Code Review

**Reviewer:** Claude (automated review)
**Date:** 2026-03-16
**Scope:** Full codebase review – errors, incorrect assumptions, usability, and improvement suggestions

---

## 1. Errors and Incorrect Assumptions

### 1.1 Critical: Truthiness checks on float values (`calculation_modes.py`)

**File:** `calculation_modes.py:42`

```python
if sample.m_s_actual_g and sample.m_ges_actual_g and sample.m_ges_actual_g > 0:
```

This uses Python truthiness. If `m_s_actual_g` is `0.0` (a valid measurement), the condition is `False` and `g_wahr` returns `None`. The same problem exists at line 114:

```python
and result.ansage_value
```

An `ansage_value` of `0.0` would skip titer calculation.

**Fix:** Replace with explicit `is not None` checks:
```python
if sample.m_s_actual_g is not None and sample.m_ges_actual_g is not None and sample.m_ges_actual_g > 0:
```

---

### 1.2 Critical: Missing Method for analysis I.1 (titrant standardization)

**File:** `init_db.py:84–104`

The seed data defines methods for I.2, I.3, II.1–II.4, III.1, III.2, III.4 – but **not** for I.1 (Einstellung Salzsäure), which is the titrant standardization analysis. Since `results_submit` checks for a valid method and `m_eq_mg`, this means:

- Result submission for I.1 is permanently blocked ("Methodenäquivalent fehlt").
- The core standardization workflow – the foundation for all subsequent analyses – cannot be completed.

Also missing: methods for I.4 (Lithiumcitrat) and III.3 (Theophyllin).

---

### 1.3 Critical: Repeated `_calc()` calls without caching (`models.py:313–335`)

**File:** `models.py:313–335`

Each property (`g_wahr`, `a_min`, `a_max`, `v_expected`, `titer_expected`) calls `self._calc()` independently. In the weighing overview template, all five are displayed per sample. For 10 samples, that is **50 evaluator calls** instead of 10, each traversing `self.batch.analysis.method` relationships.

**Fix:** Cache the calculation result per instance:
```python
def _calc(self):
    if not hasattr(self, '_calc_cache'):
        evaluator = get_evaluator(self.batch.analysis.calculation_mode)
        self._calc_cache = evaluator.calculate_sample(self)
    return self._calc_cache
```

---

### 1.4 High: No CSRF protection

**File:** `app.py` (entire application)

Flask-WTF is listed in `requirements.txt` but `CSRFProtect` is never initialized. No template includes `{{ csrf_token() }}` or `{{ form.hidden_tag() }}`. All POST forms (delete, submit result, assign buffer, weighing save) are vulnerable to cross-site request forgery.

**Fix:** Add `CSRFProtect(app)` in `create_app()` and add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to all forms (or use `{{ form.hidden_tag() }}` with WTForms).

---

### 1.5 High: No authentication or authorization

The application has zero access control. Anyone with network access can:
- View and modify student personal data (Matrikelnummer, email)
- Delete students, batches, assignments, and results
- View tolerance bounds and correct answers (reference values)
- Submit results on behalf of any student

For a university system handling student data, this is a GDPR / data protection concern.

---

### 1.6 High: Unhandled `ValueError` in float/int parsing

**Files:** `app.py:1144–1153`, `app.py:828`, `app.py:1025`

The `_float()` helper and inline `float()` calls will crash with `ValueError` on non-numeric input:

```python
# app.py:828 – weighing input
s.m_s_actual_g = float(m_s.replace(",", "."))  # crashes on "abc"

# app.py:1025 – result submission
val = float(request.form["ansage_value"].replace(",", "."))  # crashes on "abc"
```

These produce raw 500 errors with no user feedback.

---

### 1.7 Medium: `assigned` count is always 0 in batches template

**File:** `templates/admin/batches.html:14–15`

```jinja2
{% set assigned = 0 %}
{% for s in b.samples %}{% if s.active_assignment %}{% set assigned = assigned + 1 %}{% endif %}{% endfor %}
```

Due to Jinja2 scoping rules, `set` inside a `for` loop creates a **new variable in the inner scope**. The outer `assigned` remains `0`. The "Zugewiesen" column always shows `0`.

**Fix:** Use a namespace:
```jinja2
{% set ns = namespace(assigned=0) %}
{% for s in b.samples %}{% if s.active_assignment %}{% set ns.assigned = ns.assigned + 1 %}{% endif %}{% endfor %}
```

---

### 1.8 Medium: `resolve_standardization_titer` takes any student's result

**File:** `app.py:31–50`

This function picks the single most recent `titer_result` from **any** student's standardization result in the semester. If student A gets a titer of 0.997 and student B later gets 1.005, all future batches would use 1.005 – even though typically a single authoritative standardization should be performed by the TA or instructor, not derived from student results.

This may be an intentional design choice, but it conflates student practice results with official titer values used for evaluating all subsequent analyses.

---

### 1.9 Medium: Date fields stored as strings

**File:** `models.py` (throughout)

All date fields use `db.String(20)`:
```python
start_date = db.Column(db.String(20))
receipt_date = db.Column(db.String(20))
submitted_date = db.Column(db.String(20))
```

Consequences:
- No database-level date validation (can store "not-a-date")
- String sorting may fail for non-ISO date formats
- Cannot use date functions in queries (e.g., "results from last week")

---

### 1.10 Low: Cascade delete risks

**File:** `app.py:159–163`

Deleting a `Substance` that has associated `SubstanceLot` and `Analysis` records will either fail with an opaque `IntegrityError` or silently cascade-delete dependent data. The delete endpoint has no guard checking for dependencies:

```python
@app.route("/admin/substances/<int:id>/delete", methods=["POST"])
def admin_substance_delete(id):
    db.session.delete(Substance.query.get_or_404(id))
    db.session.commit()
```

Same issue applies to `Analysis`, `Method`, `Reagent`, `Semester` deletes.

---

### 1.11 Low: Default sample count is `n_students + 50`

**File:** `templates/admin/batch_form.html:47`

```
item.total_samples_prepared or (n_students + 50)
```

For 50 students, this defaults to 100 total samples (50 buffer = 100% buffer rate). A more reasonable default would be `n_students + ceil(n_students * 0.3)` (~30% buffer).

---

## 2. Usability and Administration Simplifications

### 2.1 Monolithic `app.py` (1,161 lines)

All 40+ routes live in a single function `register_routes()`. This makes navigation, maintenance, and collaboration difficult.

**Recommendation:** Split into Flask Blueprints:
- `blueprints/admin.py` – all `/admin/*` routes
- `blueprints/ta.py` – `/ta/*` routes
- `blueprints/assignments.py` – `/assignments/*` routes
- `blueprints/results.py` – `/results/*` routes
- `blueprints/reports.py` – `/reports/*` routes
- `blueprints/api.py` – `/api/*` routes

---

### 2.2 No search or filtering on list views

Admin lists for substances, reagents, lots, students, and analyses have no search, filter, or sort functionality. With 25+ reagents and 50+ students, finding specific items requires visual scanning.

**Recommendation:** Add a simple text filter using JavaScript (client-side table filtering) for immediate improvement, or server-side search for larger datasets.

---

### 2.3 No data export

There is no way to export student progress, results, or reagent demand to CSV/Excel. Course coordinators typically need this for grade reporting and administrative purposes.

**Recommendation:** Add CSV export endpoints for:
- Student list with progress summary
- Results per analysis (with all evaluation details)
- Reagent demand report

---

### 2.4 No confirmation before overwriting weighing data

The weighing form (`ta/weighing.html`) allows overwriting existing values with no warning. A TA could accidentally clear carefully entered data.

**Recommendation:** Add visual indication of already-entered values and a confirmation dialog when overwriting non-empty fields.

---

### 2.5 Duplicate code in batch form validation

**File:** `app.py:676–775`

The batch form route renders the same template with the same context (`ana_opts`, `lot_opts`, etc.) in **five** different error branches. Each copy is ~3 lines of identical context-building code.

**Recommendation:** Extract the template context into a helper or use `render_template` once at the end with early returns that `flash()` and fall through.

---

### 2.6 No batch/analysis deletion route

There is no endpoint to delete a `SampleBatch`. Once created (even by mistake), a batch cannot be removed through the UI.

---

### 2.7 Hardcoded 20% safety margin in reagent demand

**File:** `app.py:1108`

```python
safety = 1.2  # hardcoded
```

Different labs may need different safety margins. This should be configurable per semester or batch.

---

### 2.8 No pagination

All list views load all records via `.all()`. For larger semesters (100+ students, multiple semesters of historical data), this will degrade performance.

---

## 3. Additional Improvement Suggestions

### 3.1 Add automated tests

There are zero test files. The calculation logic in `calculation_modes.py` is the most critical part of the system and should have comprehensive unit tests. At minimum:
- `MassBasedEvaluator.calculate_sample()` with various input combinations
- `TitrantStandardizationEvaluator.evaluate_result()` boundary cases
- `p_effective` hierarchy (analytical > CoA > 100%)
- Edge cases: `None` values, zero values, negative values

### 3.2 Add database migrations

The app uses `db.create_all()` which cannot handle schema changes on existing databases. Adding a column, renaming a field, or changing a type requires manual SQLite manipulation or database recreation.

**Recommendation:** Use Flask-Migrate (Alembic) for versioned schema migrations.

### 3.3 Use WTForms for form validation

Flask-WTF is in `requirements.txt` but all forms use raw `request.form` access. WTForms would provide:
- Server-side validation with error messages
- CSRF protection (via `FlaskForm`)
- Type coercion (no manual `float()` / `int()` calls)
- Consistent error display

### 3.4 Add proper error pages

No custom 404 or 500 error pages exist. Database errors or missing records show raw Flask debug pages (or worse, stack traces in production).

### 3.5 Add audit logging

There is no record of who performed admin actions (deleting students, modifying batches, overriding titers). Given that this is an examination-adjacent system, an audit trail is important for academic integrity.

### 3.6 N+1 query performance in progress report

**File:** `app.py:1066–1088`

The progress matrix builds by querying per-student per-analysis:
```python
for st in students:
    for a in analyses:
        batch = SampleBatch.query.filter_by(...)  # 1 query per cell
        assgns = SampleAssignment.query.join(Sample)...  # 1 query per cell
```

With 50 students × 12 analyses = **1,200+ queries** per page load.

**Fix:** Prefetch all assignments for the semester in a single query and build the matrix in Python.

### 3.7 CDN dependency without fallback

Bootstrap CSS and JS are loaded exclusively from `cdn.jsdelivr.net`. If the CDN is unavailable (network restrictions in a university lab environment), the app renders as unstyled HTML.

**Recommendation:** Either bundle Bootstrap locally or add a local fallback.

### 3.8 Consider environment-specific configuration

**File:** `config.py:7`

```python
SECRET_KEY = os.environ.get("SECRET_KEY", "quanti-lims-dev-key-change-in-prod")
```

The default secret key is predictable. In production, session cookies can be forged. At minimum, generate a random key on first run and persist it.

---

## Summary

| Category | Count | Critical | High | Medium | Low |
|----------|-------|----------|------|--------|-----|
| Errors / Incorrect Assumptions | 11 | 3 | 3 | 3 | 2 |
| Usability Simplifications | 8 | – | – | – | – |
| Additional Improvements | 8 | – | – | – | – |

**Top 5 priorities:**
1. Fix truthiness checks in calculation logic (silent wrong results)
2. Add missing methods for I.1, I.4, III.3 (blocks core workflow)
3. Add CSRF protection (security)
4. Add authentication (data protection / GDPR)
5. Fix Jinja2 scoping bug in assigned count (incorrect UI)
