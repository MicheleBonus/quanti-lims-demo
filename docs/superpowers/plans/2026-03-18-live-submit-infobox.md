# Live-Auswertungsbox in der Ansage-Maske – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den veralteten statischen "Referenzwerte (nur Praktikumsleitung)"-Block in der Submit-Maske entfernen und durch eine live-updatende, designtechnisch saubere Informationsbox ersetzen, die bei Eingabe sofort Abweichungen, Toleranzstatus und geschätzte Übertitrierung anzeigt.

**Architecture:** Zwei Änderungen: (1) `app.py` erweitert `live_eval_ctx` um alle Felder, die die neue Box benötigt. (2) `submit.html` tauscht die alte statische Karte gegen eine neue aus, deren dynamischer Teil via erweitertem Inline-JS befüllt wird. Kein neues JS-File, keine neuen Routes, keine neuen Models.

**Tech Stack:** Flask/Jinja2, Bootstrap 5.3, Bootstrap Icons, Vanilla JS (kein Build-Step)

---

## Kontext & Vorab-Verständnis

### Was entfernt wird

`templates/results/submit.html` Zeilen 105–128 — die rechte Spalte mit dem blauen `border-info`-Card:
- Zeigt statisch `Titer Soll / Titer min / Titer max` (Standardisierung) oder `G_wahr / A_min / A_max / V_erwartet` (Gehaltsbestimmung) + `Reinheit (p)` + `Titer`
- **Problem:** Diese Werte ändern sich bei Eingabe nicht. Die Bezeichnung "nur Praktikumsleitung" ist verwirrend – die Box soll für alle nützlich sein.

### Was neu entsteht

Rechte Spalte – neue Card "Probenauswertung":

```
┌─────────────────────────────────────────────────────────┐
│ 📊 Probenauswertung                                      │  ← card-header
├──────────────────────┬──────────────────────────────────┤
│ Sollwert (G_wahr)    │ 1.2345 %                         │  ← immer sichtbar
│ Erlaubte Spanne      │ 1.2098 – 1.2592 % (±2.0 %)      │
├─────────────────────────────────────────────────────────┤
│ [id="live-details" – initial: display:none]             │
│                                                         │
│  ───────────────────[⬥]──────────────────────────────  │  ← Range-Bar
│  ◀ zu niedrig    Sollzone    zu hoch ▶                   │
│                                                         │
│ Ihr Wert           1.2500 %                             │
│ Abweichung         +0.0155 % (+1.26 %)                  │
│                                                         │
│  ✓ Innerhalb der Toleranz                               │  ← eval badge
│    — oder —                                             │
│  ↑ Leichte Übertitrierung (ca. +0.12 mL)               │  ← vol. estimate
└─────────────────────────────────────────────────────────┘
```

### Berechnungslogik (JS, live)

```
delta_pct  = (val - true_value) / true_value * 100
delta_abs  = val - true_value
lo         = true_value * (1 - 4 * T_min / 100)     // linker Rand der Anzeigerange
hi         = true_value * (1 + 4 * T_max / 100)     // rechter Rand
pos_pct    = clamp((val - lo) / (hi - lo) * 100, 0, 100)  // Marker-Position 0–100 %

// Übertitrierungsschätzung (nur wenn v_expected_ml verfügbar):
delta_v_ml = ctx.v_expected_ml * delta_pct / 100
// Formel-Herleitung: Gehalt ∝ V_titriert → δV/V_exp = δGehalt/Gehalt_soll
```

---

## File-Map

| Datei | Aktion | Zeilen |
|---|---|---|
| `app.py` | Modify | ~1571–1587 (live_eval_ctx dict) |
| `templates/results/submit.html` | Modify | 105–128 (alte Karte entfernen) + 41–95 (JS erweitern) + neue HTML-Struktur |

---

## Task 1: `live_eval_ctx` in `app.py` erweitern

**Files:**
- Modify: `app.py:1571-1587`

Die neue Infobox benötigt zusätzliche Felder im Context-Dict:
- `a_min`, `a_max` – absolute Toleranzgrenzen
- `result_unit` – Einheitsstring (z. B. `"%"`, `"mol/L"`)
- `result_label` – Beschriftung (z. B. `"Gehalt"`, `"Titer"`)
- `true_value_label` – `"G_wahr"` oder `"Titer Soll"` (je nach Modus)
- `v_expected_ml` – geschätztes Titrationsvolumen (optional, nur `assay_mass_based`)

- [ ] **Step 1: Test schreiben, der die neuen Felder prüft**

Datei: `tests/test_submit_ctx.py`

```python
"""Tests für den erweiterten live_eval_ctx in results_submit."""
from datetime import date
import pytest
from app import create_app
from models import (db, Block, Substance, SubstanceLot, SampleBatch,
                    Analysis, Method, Sample, SampleAssignment, Student,
                    Semester)

TEST_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "WTF_CSRF_ENABLED": False,
    "SECRET_KEY": "test-secret",
}


@pytest.fixture(scope="module")
def app():
    return create_app(test_config=TEST_CONFIG)


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def mass_based_aid(app):
    """Seed a mass-based assignment once for all tests in this module."""
    with app.app_context():
        sem = Semester(name="WS2026-ctx", is_active=True)
        db.session.add(sem)
        db.session.flush()

        block = Block(name="Block A", semester_id=sem.id)
        db.session.add(block)
        db.session.flush()

        sub = Substance(name="NaOH", formula="NaOH",
                        g_ab_min_pct=98.0, g_ab_max_pct=102.0)
        db.session.add(sub)
        db.session.flush()

        lot = SubstanceLot(substance_id=sub.id, lot_number="L1-ctx",
                           g_coa_pct=99.5)
        db.session.add(lot)
        db.session.flush()

        ana = Analysis(code="NA01-CTX", name="NaOH-Gehalt-ctx",
                       block_id=block.id, substance_id=sub.id,
                       calculation_mode="assay_mass_based",
                       result_unit="%", result_label="Gehalt",
                       tolerance_override_min_pct=98.0,
                       tolerance_override_max_pct=102.0)
        db.session.add(ana)
        db.session.flush()

        meth = Method(analysis_id=ana.id, method_type="direct",
                      m_eq_mg=40.0, v_solution_ml=100.0,
                      v_aliquot_ml=20.0, c_titrant_mol_l=0.1,
                      n_eq_titrant=1, molar_mass=40.0)
        db.session.add(meth)
        db.session.flush()

        batch = SampleBatch(semester_id=sem.id, analysis_id=ana.id,
                            substance_lot_id=lot.id)
        db.session.add(batch)
        db.session.flush()

        sample = Sample(batch_id=batch.id, running_number=1,
                        m_s_actual_g=0.5000, m_ges_actual_g=50.0)
        db.session.add(sample)
        db.session.flush()

        student = Student(running_number=99, first_name="Max",
                          last_name="Muster-ctx", semester_id=sem.id)
        db.session.add(student)
        db.session.flush()

        assign = SampleAssignment(
            sample_id=sample.id,
            student_id=student.id,
            attempt_number=1,
            status="assigned",
            assigned_date=date.today().isoformat(),
            assigned_by="System",
        )
        db.session.add(assign)
        db.session.commit()
        return assign.id


def test_live_eval_ctx_has_new_fields(app, client, mass_based_aid):
    """GET /results/submit/<id> renders template with extended live_eval_ctx."""
    resp = client.get(f"/results/submit/{mass_based_aid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # All new fields must appear in the tojson-serialised ctx
    assert '"a_min"' in body
    assert '"a_max"' in body
    assert '"result_unit"' in body
    assert '"result_label"' in body
    assert '"true_value_label"' in body


def test_live_eval_ctx_v_expected_present_for_mass_based(app, client, mass_based_aid):
    resp = client.get(f"/results/submit/{mass_based_aid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # v_expected_ml key must be present (value may be null if not calculable)
    assert '"v_expected_ml"' in body
```

- [ ] **Step 2: Test ausführen → muss FEHLSCHLAGEN**

```bash
cd C:\Users\Miche\Documents\GitHub\quanti-lims
python -m pytest tests/test_submit_ctx.py -v
```

Erwartetes Ergebnis: FAIL (`AssertionError: '"a_min"' not found in body`)

- [ ] **Step 3: `live_eval_ctx` in `app.py` erweitern**

In `app.py` den Block bei ~Zeile 1572 ersetzen:

```python
        # Prepare live-evaluation context for JS (None if tolerances not configured)
        live_eval_ctx = None
        if analysis.tol_min is not None and analysis.tol_max is not None:
            sample = assignment.sample
            if mode == MODE_TITRANT_STANDARDIZATION:
                true_val = sample.titer_expected
                true_value_label = "Titer Soll"
            else:
                true_val = sample.g_wahr
                true_value_label = "G_wahr"
            if true_val is not None:
                v_exp = sample.v_expected if mode != MODE_TITRANT_STANDARDIZATION else None
                live_eval_ctx = {
                    "true_value": true_val,
                    "true_value_label": true_value_label,
                    "tol_min_pct": analysis.tol_min,
                    "tol_max_pct": analysis.tol_max,
                    "attempt_type": assignment.attempt_type,
                    "mode": mode,
                    "a_min": sample.a_min,
                    "a_max": sample.a_max,
                    "result_unit": analysis.result_unit or "",
                    "result_label": analysis.result_label or "",
                    "v_expected_ml": v_exp,
                }
```

Ersetzt den Block von `live_eval_ctx = None` bis zum Ende des `if true_val is not None:` Blocks (alte Version hatte nur 6 Felder).

- [ ] **Step 4: Test ausführen → muss BESTEHEN**

```bash
python -m pytest tests/test_submit_ctx.py -v
```

Erwartetes Ergebnis: PASS (alle 2 Tests grün)

- [ ] **Step 5: Bestehende Tests noch grün?**

```bash
python -m pytest tests/ -v
```

Erwartetes Ergebnis: Alle grün (kein bestehender Test bricht durch die Dict-Erweiterung)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_submit_ctx.py
git commit -m "feat: extend live_eval_ctx with a_min/a_max/unit/label/v_expected"
```

---

## Task 2: Submit-Template – alten Card entfernen, neue Info-Box einfügen

**Files:**
- Modify: `templates/results/submit.html`

Dieser Task ist ein reiner Template-/JS-Umbau ohne Backend-Logik. Kein neuer Python-Code, keine Tests nötig (Korrektheit über Browser-Smoke-Test).

### Designspezifikation der neuen Box

**Immer sichtbar (statischer Block):**
- Probe-Header mit Analysencode und Proben-Nr.
- `Sollwert (G_wahr)` / `Sollwert (Titer Soll)`: true_value + unit
- `Erlaubte Spanne`: a_min – a_max + unit + prozentualer Klammerhinweis

**Live-Block** (`id="live-details"`, initial `display:none`, eingeblendet sobald Wert ≠ leer):
- **Range-Bar:** Horizontaler Balken (gradient red→yellow→green→yellow→red), darüber ein beweglicher Marker (schwarzes Pill)
- **Ihr Wert:** eingegeben + unit
- **Abweichung:** `±delta_abs unit  (±delta_pct %)` farbig
- **Evaluierungsstatus:** großer Badge (✓ grün / f↑ orange / f↑↑↑ rot etc.)
- **Titrationskorrektur** (nur wenn `ctx.v_expected_ml` gesetzt): `"Geschätzte Übertitrierung: ca. +0.12 mL"` oder `"Geschätzte Untertitrierung: ca. −0.12 mL"`

### JS-Logik-Erweiterung

Das bestehende IIFE (Zeilen 43-95) bleibt fast unverändert, es wird nur `update()` um die neue Box ergänzt:

```javascript
function update() {
    var raw = input.value.replace(',', '.');
    var val = parseFloat(raw);
    var label = (raw === '' || isNaN(val)) ? '' : evalLabel(val);
    badge.textContent = label;
    badge.className = 'mb-3 fs-5 fw-bold text-center ' + colorClass(label);

    // ── Neue Live-Box ────────────────────────────────────────────
    if (raw === '' || isNaN(val)) {
        liveDetails.style.display = 'none';
        return;
    }
    liveDetails.style.display = '';

    // Range-Bar Marker positionieren
    var lo = ctx.true_value * (1 - 4 * T_min / 100);
    var hi = ctx.true_value * (1 + 4 * T_max / 100);
    var posPct = Math.max(0, Math.min(100, (val - lo) / (hi - lo) * 100));
    rangeMarker.style.left = posPct + '%';

    // Abweichungen
    var deltaAbs = val - ctx.true_value;
    var deltaPct = ctx.true_value !== 0
        ? (deltaAbs / ctx.true_value * 100) : 0;
    var sign = deltaAbs >= 0 ? '+' : '';
    liveValEl.textContent  = val.toFixed(4) + ' ' + ctx.result_unit;
    liveDeltaEl.textContent = sign + deltaAbs.toFixed(4) + ' '
        + ctx.result_unit + '  (' + sign + deltaPct.toFixed(2) + ' %)';
    liveDeltaEl.className = 'fw-bold ' + colorClass(label);

    // Titrationskorrektur (optional)
    if (ctx.v_expected_ml && ctx.v_expected_ml > 0) {
        var dv = ctx.v_expected_ml * deltaPct / 100;
        var signV = dv >= 0 ? '+' : '';
        var word = dv >= 0 ? 'Übertitrierung' : 'Untertitrierung';
        liveVolEl.textContent = 'Geschätzte ' + word
            + ': ca. ' + signV + dv.toFixed(2) + ' mL';
        liveVolEl.style.display = '';
    } else {
        liveVolEl.style.display = 'none';
    }
}
```

- [ ] **Step 1: Alten rechten Card-Block entfernen**

In `templates/results/submit.html` den Block von Zeile 105 bis 128 ersetzen durch den neuen HTML-Code (Step 2).

Zu entfernender Block:
```html
  <div class="col-md-6">
    <div class="card border-info">
      <div class="card-header bg-info text-white"><i class="bi bi-info-circle"></i> Referenzwerte (nur Praktikumsleitung)</div>
      <div class="card-body">
        <table class="table table-sm mb-0">
          {% if is_standardization %}
          <tr><th>Titer Soll</th><td>{{ assignment.sample.titer_expected|fmt(4) if assignment.sample.titer_expected else '–' }}</td></tr>
          <tr><th>Titer min</th><td>{{ assignment.sample.a_min|fmt(4) if assignment.sample.a_min else '–' }}</td></tr>
          <tr><th>Titer max</th><td>{{ assignment.sample.a_max|fmt(4) if assignment.sample.a_max else '–' }}</td></tr>
          {% else %}
          <tr><th>G_wahr</th><td>{{ assignment.sample.g_wahr|fmt(4) if assignment.sample.g_wahr else '–' }}</td></tr>
          <tr><th>A_min</th><td>{{ assignment.sample.a_min|fmt(4) if assignment.sample.a_min else '–' }}</td></tr>
          <tr><th>A_max</th><td>{{ assignment.sample.a_max|fmt(4) if assignment.sample.a_max else '–' }}</td></tr>
          <tr><th>V_erwartet</th><td>{{ assignment.sample.v_expected|fmt(3) if assignment.sample.v_expected else '–' }} mL</td></tr>
          {% endif %}
          <tr><th>Reinheit (p)</th><td>{{ assignment.sample.batch.p_effective|fmt(2) }}% ({{ assignment.sample.batch.p_source }})</td></tr>
          <tr><th>{{ titer_label }}</th><td>{{ assignment.sample.batch.titer|fmt(3) }} <span class="text-body-secondary">({{ assignment.sample.batch.titer_source_label }})</span></td></tr>
          {% if not is_standardization and analysis.method and analysis.method.has_aliquot %}
          <tr><th>Aliquot</th><td>{{ analysis.method.v_aliquot_ml }} / {{ analysis.method.v_solution_ml }} mL (Faktor {{ "%.4f"|format(analysis.method.aliquot_fraction) }})</td></tr>
          {% endif %}
        </table>
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Neuen Card-Block einfügen**

Ersetze den alten Block (Step 1) durch:

```html
  <div class="col-md-6">
    {% if live_eval_ctx %}
    <div class="card border-0 shadow-sm">
      <div class="card-header d-flex align-items-center gap-2 bg-body-secondary fw-semibold">
        <i class="bi bi-graph-up-arrow"></i> Probenauswertung
      </div>
      <div class="card-body">
        {# --- Statischer Block --- #}
        <table class="table table-sm mb-3">
          <tr>
            <th style="width:50%">Sollwert ({{ live_eval_ctx.true_value_label }})</th>
            <td class="fw-semibold">{{ live_eval_ctx.true_value|round(4) }} {{ live_eval_ctx.result_unit }}</td>
          </tr>
          <tr>
            <th>Erlaubte Spanne</th>
            <td>
              {% if live_eval_ctx.a_min is not none and live_eval_ctx.a_max is not none %}
                {{ live_eval_ctx.a_min|round(4) }} – {{ live_eval_ctx.a_max|round(4) }} {{ live_eval_ctx.result_unit }}
                {% set tol_lo = (100 - live_eval_ctx.tol_min_pct)|round(1) %}
                {% set tol_hi = (live_eval_ctx.tol_max_pct - 100)|round(1) %}
                <span class="text-body-secondary small">
                  {% if tol_lo == tol_hi %}(±{{ tol_lo }} %){% else %}(−{{ tol_lo }} / +{{ tol_hi }} %){% endif %}
                </span>
              {% else %}
                <span class="text-body-secondary">–</span>
              {% endif %}
            </td>
          </tr>
        </table>

        {# --- Dynamischer Block (via JS befüllt) --- #}
        <div id="live-details" style="display:none;">
          <hr class="my-2">

          {# Range-Bar #}
          <div class="position-relative mb-1" style="height:24px;">
            <div class="rounded w-100" style="
              height:10px;
              margin-top:7px;
              background: linear-gradient(to right,
                #dc3545 0%,
                #fd7e14 18%,
                #ffc107 28%,
                #198754 40%,
                #198754 60%,
                #ffc107 72%,
                #fd7e14 82%,
                #dc3545 100%
              );
            "></div>
            <div id="live-range-marker"
                 class="position-absolute rounded-pill bg-dark border border-2 border-white"
                 style="top:0;width:10px;height:24px;transform:translateX(-50%);left:50%;"></div>
          </div>
          <div class="d-flex justify-content-between text-body-secondary" style="font-size:.7rem;">
            <span>← zu niedrig</span>
            <span>Sollzone</span>
            <span>zu hoch →</span>
          </div>

          <table class="table table-sm mt-3 mb-1">
            <tr>
              <th style="width:50%">Ihr Wert</th>
              <td id="live-val-el" class="fw-semibold"></td>
            </tr>
            <tr>
              <th>Abweichung</th>
              <td id="live-delta-el" class="fw-semibold"></td>
            </tr>
          </table>

          <div id="live-vol-el" class="text-body-secondary small mt-1" style="display:none;"></div>
        </div>
      </div>
    </div>
    {% else %}
    <div class="card border-secondary-subtle">
      <div class="card-body text-body-secondary small">
        <i class="bi bi-info-circle"></i>
        Keine Auswertungsvorschau verfügbar (Toleranzgrenzen oder Probendaten fehlen).
      </div>
    </div>
    {% endif %}
  </div>
```

- [ ] **Step 3: JS-`update()`-Funktion um Live-Box erweitern**

Im bestehenden `<script>`-Block (nach `{% if live_eval_ctx %}`), die `update()`-Funktion erweitern.

**Alter Code (Zeilen 80-94):**
```javascript
            var input  = document.querySelector('input[name="ansage_value"]');
            var badge  = document.getElementById('live-eval-badge');

            function update() {
              // Accept both comma and period as decimal separator
              var raw = input.value.replace(',', '.');
              var val = parseFloat(raw);
              var label = (raw === '' || isNaN(val)) ? '' : evalLabel(val);
              badge.textContent = label;
              badge.className = 'mb-3 fs-5 fw-bold text-center ' + colorClass(label);
            }

            input.addEventListener('input', update);
            update();
```

**Neuer Code (alten Block ersetzen):**
```javascript
            var input       = document.querySelector('input[name="ansage_value"]');
            var badge       = document.getElementById('live-eval-badge');
            var liveDetails = document.getElementById('live-details');
            var rangeMarker = document.getElementById('live-range-marker');
            var liveValEl   = document.getElementById('live-val-el');
            var liveDeltaEl = document.getElementById('live-delta-el');
            var liveVolEl   = document.getElementById('live-vol-el');

            function update() {
              var raw = input.value.replace(',', '.');
              var val = parseFloat(raw);
              var label = (raw === '' || isNaN(val)) ? '' : evalLabel(val);
              badge.textContent = label;
              badge.className = 'mb-3 fs-5 fw-bold text-center ' + colorClass(label);

              if (raw === '' || isNaN(val)) {
                liveDetails.style.display = 'none';
                return;
              }
              liveDetails.style.display = '';

              // Range-Bar: total display range ±4× tolerance around true_value
              var lo = ctx.true_value * (1 - 4 * T_min / 100);
              var hi = ctx.true_value * (1 + 4 * T_max / 100);
              var posPct = Math.max(0, Math.min(100,
                (hi > lo) ? (val - lo) / (hi - lo) * 100 : 50
              ));
              rangeMarker.style.left = posPct + '%';

              // Abweichungen
              var deltaAbs = val - ctx.true_value;
              var deltaPct = (ctx.true_value !== 0)
                ? (deltaAbs / ctx.true_value * 100) : 0;
              var sign = deltaAbs >= 0 ? '+' : '';
              liveValEl.textContent  = val.toFixed(4) + '\u202F' + ctx.result_unit;
              liveDeltaEl.textContent = sign + deltaAbs.toFixed(4) + '\u202F'
                + ctx.result_unit + '\u2002(' + sign + deltaPct.toFixed(2) + '\u202F%)';
              liveDeltaEl.className = 'fw-bold ' + colorClass(label);

              // Titrationskorrektur (nur wenn v_expected_ml bekannt)
              if (ctx.v_expected_ml && ctx.v_expected_ml > 0) {
                var dv = ctx.v_expected_ml * deltaPct / 100;
                var signV = dv >= 0 ? '+' : '';
                var word = dv >= 0 ? 'Übertitrierung' : 'Untertitrierung';
                liveVolEl.textContent = 'Geschätzte\u202F' + word
                  + ':\u202Fca.\u202F' + signV + dv.toFixed(2) + '\u202FmL';
                liveVolEl.style.display = '';
              } else {
                liveVolEl.style.display = 'none';
              }
            }

            input.addEventListener('input', update);
            update();
```

- [ ] **Step 4: Template manuell testen (Browser Smoke-Test)**

Server starten:
```bash
python app.py
```

Navigiere zu einer Zuweisung mit `assay_mass_based`-Analyse, deren Probe Einwaagedaten hat:
1. Rechte Karte zeigt "Probenauswertung" mit Sollwert + Spanne (statisch, korrekt)
2. Live-Block ist initial ausgeblendet
3. Eingabe eines Werts → Live-Block erscheint, Range-Bar-Marker bewegt sich, Abweichung wird angezeigt
4. Eingabe des exakten Sollwerts → Marker in Mitte, Abweichung `+0.0000`, Eval-Badge `✓`
5. Eingabe eines zu hohen Werts → Marker rechts, orange/rote Farbe, Übertitrierungshinweis
6. Eingabe für `titrant_standardization`-Probe: kein Titrationskorrektur-Hinweis (da `v_expected_ml` = null)
7. Komma als Dezimaltrennzeichen funktioniert

- [ ] **Step 5: Alle Tests grün?**

```bash
python -m pytest tests/ -v
```

Erwartetes Ergebnis: alle grün (Template-Änderung bricht keine Python-Tests)

- [ ] **Step 6: Commit**

```bash
git add templates/results/submit.html
git commit -m "feat: replace static Referenzwerte card with live-updating Probenauswertung box"
```

---

## Smoke-Test-Checkliste (nach beiden Tasks)

Nach Abschluss beider Tasks: manuell im Browser prüfen:

- [ ] Kein "Referenzwerte (nur Praktikumsleitung)" mehr sichtbar
- [ ] Neue Box zeigt statischen Block (Sollwert, Spanne) für beide Modi korrekt
- [ ] Live-Block initial nicht sichtbar
- [ ] Live-Block erscheint bei erster Eingabe ohne Seitenreload
- [ ] Range-Bar-Marker bewegt sich proportional zur Abweichung
- [ ] Abweichung korrekt vorzeichenbehaftet und farbig
- [ ] Bei Standardisierungs-Analyse: kein Titrationskorrektur-Hinweis
- [ ] Bei Gehalts-Analyse (mit V_erwartet): Titrationskorrektur-Hinweis korrekt
- [ ] Komma-Eingabe (z. B. `1,2345`) funktioniert wie Punkt
- [ ] Eval-Badge (oberhalb des Submit-Buttons) weiterhin korrekt
- [ ] `python -m pytest tests/ -v` → all green
