# V_disp_theo Fix — Titereinstellung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zwei neue Felder (`c_stock_mol_l`, `v_dilution_ml`) auf der Methode einführen und alle abhängigen Formeln korrigieren, sodass V_disp,min/max und der Zielfaktor in der Einwaagemaske korrekt aus `V_theo = v_dilution × c_target / c_stock` berechnet werden.

**Architecture:** Reine Datenbankfeld + Formelfehler-Korrektur: (1) neue Spalten in `models.py` + Migration, (2) Lesen/Schreiben im Backend (`app.py`), (3) neue Eingabefelder in `method_form.html`, (4) korrigierte JS-Formel in `batch_form.html`, (5) korrigierte Zielfaktor-Formel in `weighing.html` + Seed-Daten in `init_db.py`.

**Tech Stack:** Flask/SQLAlchemy, SQLite (ALTER TABLE migration), Jinja2, vanilla JavaScript

---

## Dateiübersicht

| Datei | Änderung |
|---|---|
| `models.py` | 2 neue Spalten auf `Method`; 2 Einträge in `_migrate_schema()` |
| `app.py` | `admin_method_form` speichert neue Felder; API gibt `v_disp_theoretical_ml` zurück |
| `templates/admin/method_form.html` | Neue Eingabefelder + Vorschau-Erweiterung |
| `templates/admin/batch_form.html` | `recalcVolumeFields()` + Hinweistexte korrigiert |
| `templates/ta/weighing.html` | Zielfaktor-Formel in JS + Jinja2-Zelle korrigiert |
| `init_db.py` | Methode I.1 erhält `c_stock_mol_l=1.0`, `v_dilution_ml=100.0` |

---

## Task 1: Neue Felder im Model + Migration

**Files:**
- Modify: `models.py:197-224` (Method-Klasse)
- Modify: `models.py:340-368` (_migrate_schema, Ende des method-Blocks)

### Hintergrund
`Method` hat zwei neue nullable Float-Spalten. Die Migration folgt dem bestehenden Muster: `if "feldname" not in method_cols: conn.exec_driver_sql(...)`.

- [ ] **Step 1: Neue Spalten zur Method-Klasse hinzufügen**

In `models.py`, nach Zeile 218 (`e_ab_ps_g`), folgende zwei Zeilen einfügen:

```python
    c_stock_mol_l = db.Column(db.Float)      # Stammkonzentration (mol/L), z.B. 1.0 für 1M HCl
    v_dilution_ml = db.Column(db.Float)      # Verdünnungsvolumen (mL), z.B. 100.0
```

- [ ] **Step 2: Migration in `_migrate_schema()` ergänzen**

In `models.py`, nach dem Block `if "m_eq_primary_mg_override" not in method_cols:` (nach Zeile 367), anfügen:

```python
        if "c_stock_mol_l" not in method_cols:
            conn.exec_driver_sql("ALTER TABLE method ADD COLUMN c_stock_mol_l FLOAT")
        if "v_dilution_ml" not in method_cols:
            conn.exec_driver_sql("ALTER TABLE method ADD COLUMN v_dilution_ml FLOAT")
```

- [ ] **Step 3: Manuell verifizieren**

Flask-App neu starten. In der SQLite-DB prüfen (oder durch Aufrufen von `/admin/methods`), dass kein Fehler auftritt. Die neuen Spalten sind NULL für bestehende Einträge — das ist korrekt (AC#4).

- [ ] **Step 4: Commit**

```bash
git add models.py
git commit -m "feat: add c_stock_mol_l and v_dilution_ml to Method model"
```

---

## Task 2: Backend — Route + API

**Files:**
- Modify: `app.py:486-508` (admin_method_form POST-Handler)
- Modify: `app.py:1863-1879` (api_analysis_defaults)

### Hintergrund
Der POST-Handler speichert die neuen Felder nur im Standardisierungs-Modus (wie `e_ab_ps_g`). Die API gibt `v_disp_theoretical_ml` zurück, wenn alle drei benötigten Felder gesetzt sind.

- [ ] **Step 1: Route speichert neue Felder**

In `app.py`, im `admin_method_form`-POST-Handler, nach der Zeile `item.e_ab_ps_g = _float(request.form.get("e_ab_ps_g"))` (ca. Zeile 508), einfügen:

```python
            if _mode == MODE_TITRANT_STANDARDIZATION:
                item.c_stock_mol_l = _float(request.form.get("c_stock_mol_l"))
                item.v_dilution_ml = _float(request.form.get("v_dilution_ml"))
```

Hinweis: `_mode` ist bereits weiter oben in diesem Block definiert (Zeile 489). `_float` ist eine bereits vorhandene Hilfsfunktion.

- [ ] **Step 2: API gibt `v_disp_theoretical_ml` zurück**

In `app.py`, im `api_analysis_defaults`-Endpunkt, den bestehenden `if method:` Block (ca. Zeile 1863) erweitern. **Nach** dem bestehenden Block für `v_theoretical_ml` (nach Zeile 1879), einfügen:

```python
            # For titrant standardization: dispensing volume from stock (NEW formula)
            if (
                method.v_dilution_ml is not None
                and method.c_titrant_mol_l is not None
                and method.c_stock_mol_l is not None
                and method.c_stock_mol_l > 0
            ):
                v_disp_theoretical = (
                    method.v_dilution_ml * method.c_titrant_mol_l / method.c_stock_mol_l
                )
                result["v_disp_theoretical_ml"] = round(v_disp_theoretical, 4)
```

- [ ] **Step 3: Manuell verifizieren**

Nach Task 5 Step 3 (Seed-Daten) prüfen:
```
GET /api/analysis/1/defaults
→ "v_disp_theoretical_ml": 10.0
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: save c_stock/v_dilution in method route; add v_disp_theoretical_ml to API"
```

---

## Task 3: Method Form — Neue Felder + Vorschau

**Files:**
- Modify: `templates/admin/method_form.html:29-42` (primary-standard-row, neue Felder)
- Modify: `templates/admin/method_form.html:231-234` (updateCalcPreview, V_disp_theo Zeile)
- Modify: `templates/admin/method_form.html:359-363` (Input-Listener-Liste)

### Hintergrund
Die neuen Felder erscheinen im Standardisierungs-Block neben `e_ab_ps_g`. Die Vorschau zeigt bereits korrekt `V_theoretisch` (Titrations-Volumen des Studierenden) — dieser Wert bleibt, zusätzlich kommt `V_disp,theo` (Dispensiervolumen der TA).

- [ ] **Step 1: Neue Eingabefelder im Template**

In `method_form.html`, im `<div id="primary-standard-row">` (Zeile 29), die bestehende innere `<div class="row">` erweitern. Nach dem `col-md-3`-Block für `e_ab_ps_g` (Zeile 32), zwei neue Spalten hinzufügen:

```html
      <div class="col-md-2">{{ field("c_stock_mol_l", "c_Stamm (mol/L)", item.c_stock_mol_l, type="number", step="0.001", help="Konzentration der Stammlösung die die TA dispensiert (z.B. 1.0 für 1 mol/L HCl). Nur für Titereinstellung.") }}</div>
      <div class="col-md-2">{{ field("v_dilution_ml", "V_Verdünnung (mL)", item.v_dilution_ml, type="number", step="0.1", help="Volumen auf das Studierende auffüllen (z.B. 100.0 mL). Nur für Titereinstellung.") }}</div>
```

Die neuen Felder kommen in eine **separate zweite Zeile** innerhalb von `#primary-standard-row` (vermeidet Bootstrap-Grid-Überlauf bei der bestehenden 10-Spalten-Zeile):
```html
  <div id="primary-standard-row">
    <div class="row">
      <div class="col-md-4">{{ select("primary_standard_id", ...) }}</div>
      <div class="col-md-3">{{ field("e_ab_ps_g", ...) }}</div>
      <div class="col-md-3">{{ field("m_eq_primary_mg", ...) }}...</div>
    </div>
    <div class="row">
      <div class="col-md-3">{{ field("c_stock_mol_l", "c_Stamm (mol/L)", item.c_stock_mol_l, type="number", step="0.001", help="Konzentration der Stammlösung die die TA dispensiert (z.B. 1.0 für 1 mol/L HCl). Nur für Titereinstellung.") }}</div>
      <div class="col-md-3">{{ field("v_dilution_ml", "V_Verdünnung (mL)", item.v_dilution_ml, type="number", step="0.1", help="Volumen auf das Studierende auffüllen (z.B. 100.0 mL). Nur für Titereinstellung.") }}</div>
    </div>
  </div>
```

- [ ] **Step 2: Vorschau zeigt V_disp_theo**

In `method_form.html`, in `updateCalcPreview()` im Standardisierungs-Zweig, nach der bestehenden `V_theoretisch`-Zeile (ca. nach Zeile 234 `html += \`<br><strong>V<sub>theoretisch</sub></strong>...`), einfügen:

```javascript
      const cStock = getFloat('c_stock_mol_l');
      const vDilution = getFloat('v_dilution_ml');
      if (cStock && cStock > 0 && vDilution && vDilution > 0 && cTitrant && cTitrant > 0) {
        const vDispTheo = (vDilution * cTitrant) / cStock;
        html += `<br><strong>V<sub>disp,theo</sub></strong> = (${vDilution} &times; ${cTitrant}) / ${cStock} = <strong>${vDispTheo.toFixed(3)} mL</strong>`;
        html += `<br><span class="text-body-secondary">→ V<sub>disp,min</sub> = ${(vDispTheo * 0.9).toFixed(3)} mL, V<sub>disp,max</sub> = ${(vDispTheo * 1.1).toFixed(3)} mL</span>`;
      }
```

- [ ] **Step 3: Input-Listener für neue Felder ergänzen**

In `method_form.html`, die Liste der Felder die `updateCalcPreview` auslösen (ca. Zeile 359-363), erweitern:

```javascript
  ['c_titrant_mol_l', 'n_eq_titrant', 'c_vorlage_mol_l', 'n_eq_vorlage',
   'v_vorlage_ml', 'v_solution_ml', 'v_aliquot_ml', 'm_eq_primary_mg', 'e_ab_ps_g',
   'c_stock_mol_l', 'v_dilution_ml'].forEach(id => {
```

- [ ] **Step 4: Manuell verifizieren**

Im Browser Methode I.1 öffnen (`/admin/methods/1/edit`). Die neuen Felder „c_Stamm" und „V_Verdünnung" sollten erscheinen. Werte 1.0 und 100.0 eingeben → Vorschau zeigt `V_disp,theo = 10.000 mL`.

- [ ] **Step 5: Commit**

```bash
git add templates/admin/method_form.html
git commit -m "feat: add c_stock/v_dilution fields to method form with V_disp_theo preview"
```

---

## Task 4: Batch Form — recalcVolumeFields korrigieren

**Files:**
- Modify: `templates/admin/batch_form.html:16-21` (hint-standardization Alert)
- Modify: `templates/admin/batch_form.html:53-54` (Help-Texte der V-Felder)
- Modify: `templates/admin/batch_form.html:176-189` (recalcVolumeFields)

### Hintergrund
`recalcVolumeFields()` verwendet bisher `v_theoretical_ml * k_determinations` — falsche Formel. Neu: `v_disp_theoretical_ml * 0.9` / `* 1.1`. Auch der Hinweistext und die Hilfe-Texte der Felder werden korrigiert.

- [ ] **Step 1: Hinweistext korrigieren**

In `batch_form.html`, den Alert `id="hint-standardization"` (Zeilen 16-21):

**Vorher:**
```html
<div class="alert alert-light border small" id="hint-standardization" style="display:none">
  <i class="bi bi-info-circle"></i> <strong>Hinweis (Titereinstellung):</strong>
  Die TA dispensiert nur das Volumen der Titrant-Lösung (z.B. HCl).
  V_min und V_max werden automatisch aus der Stöchiometrie des Primärstandards berechnet.
  Die Studierenden wiegen den Urtitersubstanz selbst ein, titrieren und melden den berechneten Faktor als Ansage.
</div>
```

**Nachher:**
```html
<div class="alert alert-light border small" id="hint-standardization" style="display:none">
  <i class="bi bi-info-circle"></i> <strong>Hinweis (Titereinstellung):</strong>
  Die TA dispensiert ein Volumen der Stammlösung; Studierende füllen auf V_Verdünnung auf.
  V_min/V_max = V_disp,theo × 0.9 / 1.1 (±10%). V_disp,theo = V_Verdünnung × c_Soll / c_Stamm.
  Studierende melden den berechneten Faktor (= V_disp / V_disp,theo) direkt als Ansage.
</div>
```

- [ ] **Step 2: Help-Texte der V-Felder korrigieren**

In `batch_form.html`, die beiden Felder `target_v_min_ml` und `target_v_max_ml` (Zeilen 53-54):

**Vorher:**
```html
    <div class="col-md-3">{{ field("target_v_min_ml", "Ziel V_disp,min (mL)", item.target_v_min_ml, type="number", step="0.001", help="Mindestvolumen der dispendierten Titrant-Lösung pro Probe. Wird automatisch aus Primärstandard-Stöchiometrie vorgeschlagen.") }}</div>
    <div class="col-md-3">{{ field("target_v_max_ml", "Ziel V_disp,max (mL)", item.target_v_max_ml, type="number", step="0.001", help="Maximalvolumen der dispendierten Titrant-Lösung pro Probe. Wird automatisch vorgeschlagen (V_min × 1,5).") }}</div>
```

**Nachher:**
```html
    <div class="col-md-3">{{ field("target_v_min_ml", "Ziel V_disp,min (mL)", item.target_v_min_ml, type="number", step="0.001", help="Mindestvolumen je Dispensierung. Vorschlag: V_disp,theo × 0.9 (aus Methode: V_Verdünnung × c_Soll / c_Stamm).") }}</div>
    <div class="col-md-3">{{ field("target_v_max_ml", "Ziel V_disp,max (mL)", item.target_v_max_ml, type="number", step="0.001", help="Maximalvolumen je Dispensierung. Vorschlag: V_disp,theo × 1.1.") }}</div>
```

- [ ] **Step 3: `recalcVolumeFields()` korrigieren**

In `batch_form.html`, die Funktion `recalcVolumeFields` (Zeilen 176-189):

**Vorher:**
```javascript
  function recalcVolumeFields() {
    if (!currentDefaults || !currentDefaults.v_theoretical_ml) return;
    const kDet = currentDefaults.k_determinations || 3;
    const vTheo = currentDefaults.v_theoretical_ml;
    const vMin = +(vTheo * kDet).toFixed(3);
    const vMax = +(vMin * 1.5).toFixed(3);

    if (!targetVMinInput.value) {
      targetVMinInput.value = vMin;
    }
    if (!targetVMaxInput.value) {
      targetVMaxInput.value = vMax;
    }
  }
```

**Nachher:**
```javascript
  function recalcVolumeFields() {
    if (!currentDefaults || !currentDefaults.v_disp_theoretical_ml) return;
    const vDisp = currentDefaults.v_disp_theoretical_ml;
    const vMin = +(vDisp * 0.9).toFixed(3);
    const vMax = +(vDisp * 1.1).toFixed(3);

    if (!targetVMinInput.value) {
      targetVMinInput.value = vMin;
    }
    if (!targetVMaxInput.value) {
      targetVMaxInput.value = vMax;
    }
  }
```

- [ ] **Step 4: Manuell verifizieren**

Neuen Ansatzbogen für Analyse I.1 anlegen (`/admin/batches/new`). Nach Auswahl der Analyse:
- V_disp,min sollte 9.000 vorgeschlagen werden
- V_disp,max sollte 11.000 vorgeschlagen werden
(Setzt voraus, dass Task 6 — Seed-Daten — bereits durchgeführt wurde oder Methode I.1 manuell aktualisiert wurde)

- [ ] **Step 5: Commit**

```bash
git add templates/admin/batch_form.html
git commit -m "fix: use v_disp_theoretical_ml for V_min/V_max suggestion (±10%)"
```

---

## Task 5: Weighing Form — Zielfaktor-Formel korrigieren + Seed-Daten

**Files:**
- Modify: `templates/ta/weighing.html:90-95` (server-seitige Zielfaktor-Zelle)
- Modify: `templates/ta/weighing.html:155-156` (V_THEORETICAL_ML JS-Konstante)
- Modify: `init_db.py:189-191` (Methode I.1 Seed)

### Hintergrund
Die aktuelle Formel `(e_ab_ps_g * 1000 / m_eq_primary_mg)` liefert das Titrations-Volumen des Studierenden (~10.49 mL für I.1, ~56.61 mL für Na₂CO₃-Methoden). Korrekt ist `v_dilution_ml * c_titrant_mol_l / c_stock_mol_l` (= 10.000 mL für I.1). Beide Stellen — Jinja2-Zelle und JS-Konstante — müssen korrigiert werden.

- [ ] **Step 1: Server-seitige Zielfaktor-Zelle korrigieren**

In `weighing.html`, die Tabellenzelle `id="factor-{{ s.id }}"` (Zeilen 90-95):

**Vorher:**
```html
        <td class="text-end" id="factor-{{ s.id }}">
          {%- set _m = batch.analysis.method -%}
          {%- if s.m_ges_actual_g and _m and _m.e_ab_ps_g and _m.m_eq_primary_mg and _m.m_eq_primary_mg > 0 -%}
            {{ (s.m_ges_actual_g / (_m.e_ab_ps_g * 1000 / _m.m_eq_primary_mg)) | round(4) | fmt(4) }}
          {%- endif -%}
        </td>
```

**Nachher:**
```html
        <td class="text-end" id="factor-{{ s.id }}">
          {%- set _m = batch.analysis.method -%}
          {%- if s.m_ges_actual_g and _m and _m.v_dilution_ml and _m.c_titrant_mol_l and _m.c_stock_mol_l and _m.c_stock_mol_l > 0 -%}
            {{ (s.m_ges_actual_g / (_m.v_dilution_ml * _m.c_titrant_mol_l / _m.c_stock_mol_l)) | round(4) | fmt(4) }}
          {%- endif -%}
        </td>
```

- [ ] **Step 2: JS-Konstante V_THEORETICAL_ML korrigieren**

In `weighing.html`, Zeile 155-156:

**Vorher:**
```javascript
{%- set _m = batch.analysis.method -%}
const V_THEORETICAL_ML = {{ (_m.e_ab_ps_g * 1000 / _m.m_eq_primary_mg) | round(4) if _m and _m.e_ab_ps_g and _m.m_eq_primary_mg and _m.m_eq_primary_mg > 0 else 'null' }};
```

**Nachher:**
```javascript
{%- set _m = batch.analysis.method -%}
const V_THEORETICAL_ML = {{ (_m.v_dilution_ml * _m.c_titrant_mol_l / _m.c_stock_mol_l) | round(4) if _m and _m.v_dilution_ml and _m.c_titrant_mol_l and _m.c_stock_mol_l and _m.c_stock_mol_l > 0 else 'null' }};
```

- [ ] **Step 3: Seed-Daten für I.1 ergänzen**

In `init_db.py`, nach Zeile 191 (`methods["I.1"].e_ab_ps_g = 0.200`):

```python
    methods["I.1"].c_stock_mol_l = 1.0
    methods["I.1"].v_dilution_ml = 100.0
```

- [ ] **Step 4: Manuell verifizieren (Akzeptanzkriterien aus dem Spec)**

**AC#1:** API gibt `v_disp_theoretical_ml=10.0` für I.1 zurück:
```
GET /api/analysis/1/defaults → "v_disp_theoretical_ml": 10.0  ✓
```

**AC#2:** Ansatzbogen schlägt V_min=9.000, V_max=11.000 vor ✓

**AC#3:** Einwaagemaske öffnen für einen I.1-Probensatz. Volumen 9.46 eingeben → Zielfaktor zeigt `0.9460` (statt ~0.167 wie zuvor) ✓

**AC#4:** Methode ohne c_stock/v_dilution → Zielfaktor-Zelle bleibt leer, kein Fehler ✓

**AC#5:** ASS-Ansatzbogen (massenbasiert) öffnen → Formular funktioniert unverändert ✓

- [ ] **Step 5: Commit**

```bash
git add templates/ta/weighing.html init_db.py
git commit -m "fix: correct Zielfaktor formula to use c_stock/v_dilution instead of primary standard titration volume"
```
