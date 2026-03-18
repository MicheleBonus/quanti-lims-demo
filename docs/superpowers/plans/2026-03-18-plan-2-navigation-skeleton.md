# Navigations-Skelett: Zwei-Phasen-Layout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the navigation into two clearly visible top-level areas — "Vorbereitung" and "Praktikum" — with a new landing page as the entry point. No route logic changes, no template moves — only navigation and landing page.

**Architecture:** New `home.html` landing page replaces `dashboard.html` as the app root. `base.html` navbar is reorganized into two named sections. The existing template files and routes stay in place; only their grouping in the navbar changes. A placeholder "Praktikum" section is created for future plans to fill in.

**Tech Stack:** Bootstrap 5.3 (already in use), Jinja2, Flask

**Spec:** `docs/superpowers/specs/2026-03-18-ux-redesign-two-phase-design.md` (section "Zwei-Phasen-Navigation")

**Depends on:** Plan 1 (DB Migration) — should be merged first, but this plan can run in parallel on a branch.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `templates/home.html` | New landing page with two-section cards |
| Modify | `templates/base.html` | Reorganize navbar into Vorbereitung / Praktikum |
| Modify | `app.py` | Change `dashboard` route to render `home.html` |
| Create | `templates/praktikum/tagesansicht.html` | Placeholder — "coming soon" page |
| Modify | `app.py` | Add `/praktikum/` route |
| Delete | `templates/dashboard.html` | Replaced by `home.html` |

---

### Task 1: Create new landing page (home.html)

**Files:**
- Create: `templates/home.html`
- Modify: `app.py` — `dashboard` route

- [ ] **Step 1: Write a route test**

```python
# tests/test_navigation.py
def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Vorbereitung" in resp.data
    assert b"Praktikum" in resp.data
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_navigation.py::test_home_page_loads -v
```
Expected: FAIL — `home.html` doesn't exist yet

- [ ] **Step 3: Create templates/home.html**

```html
{% extends "base.html" %}
{% block title %}Quanti-LIMS{% endblock %}
{% block content %}
<div class="row g-4 mt-2">

  <div class="col-md-6">
    <a href="{{ url_for('vorbereitung_stammdaten') }}" class="text-decoration-none">
      <div class="card h-100 border-primary">
        <div class="card-body p-4">
          <h2 class="card-title">
            <i class="bi bi-archive text-primary"></i> Vorbereitung
          </h2>
          <p class="card-text text-body-secondary">
            Stammdaten, Semesterplanung und Probenvorbereitung.
            Alles was vor dem Praktikum erledigt wird.
          </p>
          <ul class="list-unstyled mt-3">
            <li><i class="bi bi-chevron-right text-primary"></i> Stammdaten</li>
            <li><i class="bi bi-chevron-right text-primary"></i> Semesterplanung</li>
            <li><i class="bi bi-chevron-right text-primary"></i> Probenvorbereitung</li>
          </ul>
        </div>
      </div>
    </a>
  </div>

  <div class="col-md-6">
    <a href="{{ url_for('praktikum_tagesansicht') }}" class="text-decoration-none">
      <div class="card h-100 border-success">
        <div class="card-body p-4">
          <h2 class="card-title">
            <i class="bi bi-play-circle text-success"></i> Praktikum
          </h2>
          <p class="card-text text-body-secondary">
            Tagesansicht, Ansagen, Protokolle und Studentenstatus.
            Alles was während des Praktikums benötigt wird.
          </p>
          <ul class="list-unstyled mt-3">
            <li><i class="bi bi-chevron-right text-success"></i> Tagesansicht</li>
            <li><i class="bi bi-chevron-right text-success"></i> Ansage eintragen</li>
            <li><i class="bi bi-chevron-right text-success"></i> Protokoll abhaken</li>
          </ul>
        </div>
      </div>
    </a>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 4: Update dashboard route and add vorbereitung_stammdaten stub in app.py**

> **Important:** In `app.py`, ALL routes are defined inside the `register_routes(app)` function body using the local `app` parameter — not at module level. Find the existing `dashboard` route inside `register_routes(app)` and update it. Add the new stub directly below it, still inside `register_routes(app)`.

Find (inside `register_routes(app)`):
```python
@app.route("/")
def dashboard():
    return render_template("dashboard.html")
```
Replace with:
```python
@app.route("/")
def dashboard():
    return render_template("home.html")

@app.route("/vorbereitung/stammdaten")
def vorbereitung_stammdaten():
    return redirect(url_for("admin_substances"))
```

- [ ] **Step 5: Run test**

```bash
pytest tests/test_navigation.py::test_home_page_loads -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add templates/home.html app.py tests/test_navigation.py
git commit -m "feat: add two-phase landing page (home.html)"
```

---

### Task 2: Reorganize base.html navbar

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Write navbar structure tests**

```python
# tests/test_navigation.py  (append to existing file)
def test_navbar_has_vorbereitung_section(client):
    resp = client.get("/")
    assert b"Vorbereitung" in resp.data

def test_navbar_has_praktikum_section(client):
    resp = client.get("/")
    assert b"Praktikum" in resp.data

def test_navbar_stammdaten_link_present(client):
    resp = client.get("/admin/substances")
    assert b"Stammdaten" in resp.data

def test_navbar_semesterplanung_link_present(client):
    resp = client.get("/admin/substances")
    assert b"Semesterplanung" in resp.data
```

- [ ] **Step 2: Run to confirm tests fail (navbar not yet reorganized)**

```bash
pytest tests/test_navigation.py -v
```
Expected: `test_navbar_stammdaten_link_present` and `test_navbar_semesterplanung_link_present` FAIL

- [ ] **Step 3: Rewrite base.html navbar**

Replace the `<div class="collapse navbar-collapse" id="nav">` section in `templates/base.html`:

```html
<div class="collapse navbar-collapse" id="nav">
  <ul class="navbar-nav me-auto">

    <!-- VORBEREITUNG -->
    <li class="nav-item dropdown">
      <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">
        <i class="bi bi-archive"></i> Vorbereitung
      </a>
      <ul class="dropdown-menu">
        <li><h6 class="dropdown-header">Stammdaten</h6></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_substances') }}">
          <i class="bi bi-flask-vial"></i> Arzneistoffe / Analyten</a></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_lots') }}">
          <i class="bi bi-box-seam"></i> Chargen / CoA</a></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_reagents') }}">
          <i class="bi bi-prescription2"></i> Reagenzien</a></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_analyses') }}">
          <i class="bi bi-list-ol"></i> Prüfungen</a></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_methods') }}">
          <i class="bi bi-diagram-3"></i> Methoden</a></li>

        <li><hr class="dropdown-divider"></li>
        <li><h6 class="dropdown-header">Semesterplanung</h6></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_semesters') }}">
          <i class="bi bi-calendar3"></i> Semester</a></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_students') }}">
          <i class="bi bi-people"></i> Studierende &amp; Gruppen</a></li>

        <li><hr class="dropdown-divider"></li>
        <li><h6 class="dropdown-header">Probenvorbereitung</h6></li>
        <li><a class="dropdown-item" href="{{ url_for('admin_batches') }}">
          <i class="bi bi-collection"></i> Probensätze</a></li>
        <li><a class="dropdown-item" href="{{ url_for('ta_weighing') }}">
          <i class="bi bi-ui-checks-grid"></i> Einwaage</a></li>
      </ul>
    </li>

    <!-- PRAKTIKUM -->
    <li class="nav-item dropdown">
      <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">
        <i class="bi bi-play-circle"></i> Praktikum
      </a>
      <ul class="dropdown-menu">
        <li><a class="dropdown-item" href="{{ url_for('praktikum_tagesansicht') }}">
          <i class="bi bi-calendar-day"></i> Tagesansicht</a></li>
        <li><a class="dropdown-item" href="{{ url_for('assignments_overview') }}">
          <i class="bi bi-arrow-left-right"></i> Zuweisungen</a></li>
        <li><a class="dropdown-item" href="{{ url_for('results_overview') }}">
          <i class="bi bi-clipboard-check"></i> Ergebnisse</a></li>
      </ul>
    </li>

    <!-- BERICHTE -->
    <li class="nav-item dropdown">
      <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">
        <i class="bi bi-bar-chart"></i> Berichte
      </a>
      <ul class="dropdown-menu">
        <li><a class="dropdown-item" href="{{ url_for('reports_progress') }}">Fortschritt</a></li>
        <li><a class="dropdown-item" href="{{ url_for('reports_reagents') }}">Reagenzienbedarf</a></li>
      </ul>
    </li>

    <!-- SYSTEM -->
    <li class="nav-item">
      <a class="nav-link" href="{{ url_for('admin_system') }}">
        <i class="bi bi-hdd-stack"></i> System
      </a>
    </li>

  </ul>
</div>
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add templates/base.html
git commit -m "feat: reorganize navbar into Vorbereitung / Praktikum sections"
```

---

### Task 3: Add Praktikum placeholder route and template

**Files:**
- Create: `templates/praktikum/tagesansicht.html`
- Modify: `app.py` — add `praktikum_tagesansicht` route

- [ ] **Step 1: Write route test**

```python
# tests/test_navigation.py (append)
def test_praktikum_tagesansicht_loads(client):
    resp = client.get("/praktikum/")
    assert resp.status_code == 200
    assert b"Tagesansicht" in resp.data
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_navigation.py::test_praktikum_tagesansicht_loads -v
```
Expected: FAIL (404 or template missing)

- [ ] **Step 3: Create templates/praktikum/tagesansicht.html**

```html
{% extends "base.html" %}
{% block title %}Tagesansicht – Quanti-LIMS{% endblock %}
{% block content %}
<div class="d-flex align-items-center gap-2 mb-4">
  <i class="bi bi-calendar-day fs-3 text-success"></i>
  <h1 class="h3 mb-0">Tagesansicht</h1>
</div>
<div class="alert alert-info">
  <i class="bi bi-info-circle"></i>
  Die Tagesansicht wird in einem späteren Schritt implementiert (Plan 4).
  Sie zeigt dann: Rotationsübersicht, Studentenstatus, Dienste des Tages
  und ermöglicht die schnelle Ansage-Eingabe.
</div>
{% endblock %}
```

- [ ] **Step 4: Add route to app.py**

> **Important:** Add this inside `register_routes(app)`, alongside the other route definitions.

```python
@app.route("/praktikum/")
def praktikum_tagesansicht():
    return render_template("praktikum/tagesansicht.html")
```

- [ ] **Step 5: Run test**

```bash
pytest tests/test_navigation.py -v
```
Expected: all PASS

- [ ] **Step 6: Remove old dashboard.html (optional)**

Check if `dashboard.html` is still referenced anywhere:
```bash
grep -r "dashboard.html" templates/ app.py
```
If no references remain, delete it:
```bash
git rm templates/dashboard.html
```

- [ ] **Step 7: Commit**

```bash
git add templates/praktikum/ app.py
git commit -m "feat: add Praktikum placeholder route and Tagesansicht template"
```

---

### Task 4: Delete the vorbereitung_stammdaten redirect stub

Once Plan 3 is complete and a proper Vorbereitung landing exists, the temporary redirect added in Task 1 should be cleaned up. This is a reminder task — execute when Plan 3 is done.

- [ ] **Step 1: Check if a proper Vorbereitung landing page was added in Plan 3**

If yes, remove the stub redirect from `app.py` and update `home.html` to point to the new route.

- [ ] **Step 2: Commit**

```bash
git add app.py templates/home.html
git commit -m "chore: remove vorbereitung_stammdaten redirect stub"
```
