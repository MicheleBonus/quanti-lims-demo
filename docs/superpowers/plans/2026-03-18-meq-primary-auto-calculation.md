# m_eq Primärstandard Auto-Berechnung – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Im Formular "Methode bearbeiten" soll `m_eq Primärstandard (mg/mL)` automatisch aus `c_Titrant`, dem Molgewicht des Primärstandards und dem z-Faktor (n_eq_titrant) berechnet werden – außer ein manueller Override-Haken ist gesetzt.

**Architecture:** Drei Änderungen greifen ineinander: (1) Ein neues Boolean-Feld `m_eq_primary_mg_override` in der DB, (2) serverseitige Berechnung beim Speichern wenn kein Override gesetzt ist, (3) clientseitige Live-Berechnung + Override-Checkbox im HTML-Formular.

**Tech Stack:** Python/Flask, SQLAlchemy, SQLite (migrate_schema-Pattern), Jinja2-Templates, Vanilla JavaScript

---

## Formel & Hintergrund

In der Titereinstellung (MODE_TITRANT_STANDARDIZATION) gilt:

```
m_eq_PS (mg/mL) = c_Titrant (mol/L) × MW_PS (g/mol) / z
```

wobei z = `n_eq_titrant` = Äquivalente Titrant pro Mol Primärstandard.

**Herleitung:** 1 mL Titrant mit c mol/L enthält c mmol Titrant → reagiert mit c/z mmol Primärstandard → wiegt c/z × MW mg.

Beispiel: HCl 0,1 mol/L + Na₂B₄O₇ (MW=381,37, z=2):
`m_eq = 0,1 × 381,37 / 2 = 19,069 mg/mL` ✓

Das Feld `n_eq_titrant` ist in Standardisierungsmodus somit **nicht** redundant – es ist der z-Faktor für die Ableitung von `m_eq_primary_mg`. Beide Felder zusammen ergeben Transparenz.

---

## File Structure

| Datei | Änderung |
|-------|----------|
| `models.py` | Neues Feld `m_eq_primary_mg_override: Boolean` + Migration in `migrate_schema()` |
| `app.py` | POST-Handler: m_eq auto-berechnen wenn kein Override; Template-Kontext: PS-Molmassen als JSON-Map |
| `templates/admin/method_form.html` | Override-Checkbox, JS-Auto-Berechnung, erweitertes Berechnungsvorschau |

---

## Task 1: Neues DB-Feld `m_eq_primary_mg_override` in models.py

**Files:**
- Modify: `models.py:216` (nach `m_eq_primary_mg`-Feld)
- Modify: `models.py:349` (in `migrate_schema()`, `method`-Block)

### Schritt-für-Schritt

- [ ] **Schritt 1: Feld in Method-Klasse einfügen**

Nach Zeile 216 (`m_eq_primary_mg = db.Column(db.Float)`) einfügen:

```python
    m_eq_primary_mg_override = db.Column(db.Boolean, nullable=False, default=False)
```

- [ ] **Schritt 2: Migration in migrate_schema() einfügen**

Im Block `method_cols` (nach Zeile 352, nach dem `e_ab_ps_g`-Block) einfügen:

```python
        if "m_eq_primary_mg_override" not in method_cols:
            conn.exec_driver_sql(
                "ALTER TABLE method ADD COLUMN m_eq_primary_mg_override BOOLEAN NOT NULL DEFAULT 0"
            )
            # Bestehende Methoden mit manuell gesetztem m_eq_primary_mg → Override auf True setzen
            conn.exec_driver_sql(
                "UPDATE method SET m_eq_primary_mg_override = 1 WHERE m_eq_primary_mg IS NOT NULL"
            )
```

**Warum Backfill?** Bestehende Methoden haben `m_eq_primary_mg` manuell eingetragen – wir setzen Override=True damit der gespeicherte Wert erhalten bleibt.

- [ ] **Schritt 3: App starten und prüfen**

```bash
cd /c/Users/Miche/Documents/GitHub/quanti-lims
python app.py
```

Erwartung: Keine Fehler, App startet. Im Browser: http://localhost:5000/admin/methods – Methoden werden angezeigt.

---

## Task 2: Backend – POST-Handler + Template-Kontext

**Files:**
- Modify: `app.py` (Funktion `admin_method_form`)

### Schritt-für-Schritt

- [ ] **Schritt 1: PS-Molmassen-Map für Template vorbereiten**

In `admin_method_form()` gibt es aktuell an **zwei Stellen** identischen Code für `ps_opts`: Zeile 495-496 (POST-Fehler bei fehlgeschlagener Aliquot-Validierung) und Zeile 507-509 (GET). An **beiden Stellen** `ps_opts` erweitern und eine `ps_molar_masses`-Variable hinzufügen:

```python
        all_reagents = Reagent.query.order_by(Reagent.name).all()
        ps_list = [r for r in all_reagents if r.is_primary_standard]
        ps_opts = [(r.id, f"{r.name} ({r.formula}, MW={r.molar_mass_gmol})") for r in ps_list]
        ps_molar_masses = {r.id: r.molar_mass_gmol for r in ps_list if r.molar_mass_gmol}
```

Und in beiden `render_template`-Aufrufen ergänzen:
```python
        return render_template("admin/method_form.html", item=item, ana_opts=ana_opts,
                               primary_std_opts=ps_opts, ps_molar_masses=ps_molar_masses)
```

Hinweis: Der IntegrityError-Pfad (Zeile 504-505) hat keinen eigenen `render_template`-Aufruf – er fällt durch zum GET-Render auf Zeile 509. Es gibt also genau **zwei** `render_template`-Aufrufe.

- [ ] **Schritt 2: POST-Handler – m_eq_primary_mg-Zuweisung umstrukturieren**

Im POST-Block muss die Zuweisung von `item.m_eq_primary_mg` (aktuell Zeile 487: `item.m_eq_primary_mg = _float(request.form.get("m_eq_primary_mg"))`) **durch folgenden Block ersetzt** werden:

```python
            item.m_eq_primary_mg_override = bool(request.form.get("m_eq_primary_mg_override"))
            if item.m_eq_primary_mg_override:
                # Manueller Wert aus dem Formular übernehmen
                item.m_eq_primary_mg = _float(request.form.get("m_eq_primary_mg"))
            else:
                # Auto-Berechnung: m_eq = c_Titrant × MW_PS / z
                # Hinweis: item.primary_standard ist die bereits geladene Relationship
                ps = item.primary_standard  # via FK primary_standard_id, kein extra DB-Query nötig
                if (ps and ps.molar_mass_gmol
                        and item.c_titrant_mol_l and item.c_titrant_mol_l > 0
                        and item.n_eq_titrant and item.n_eq_titrant > 0):
                    item.m_eq_primary_mg = round(
                        item.c_titrant_mol_l * ps.molar_mass_gmol / item.n_eq_titrant, 4
                    )
                else:
                    item.m_eq_primary_mg = None
```

**Wichtig:** Die bestehende Zeile 487 nicht belassen und diesen Block dahinter hängen – sondern die alte Zeile **ersetzen**. Andernfalls würde der Wert erst auf `None` gesetzt (da disabled inputs nicht gesendet werden) und dann überschrieben – das ist fragil.

- [ ] **Schritt 3: Manuell testen (Regression)**

Bestehende Methode aufrufen: http://localhost:5000/admin/methods → Bleistift-Icon bei einer Titereinstellung-Methode.
Erwartung: Formular lädt fehlerfrei, Override-Checkbox ist noch nicht sichtbar (kommt in Task 3).

---

## Task 3: Frontend – Override-Checkbox + JS-Auto-Berechnung + Vorschau-Update

**Files:**
- Modify: `templates/admin/method_form.html`

### Schritt-für-Schritt

- [ ] **Schritt 1: PS-Molmassen-Map in JS einbetten**

Im `<script>`-Block, nach Zeile 97 (`const analysisMW = {};`), hinzufügen:

```javascript
  const psMolarMasses = {{ ps_molar_masses | tojson }};  // {id: molar_mass_gmol}
```

- [ ] **Schritt 2: Override-Checkbox ins HTML einfügen**

Den aktuellen `m_eq_primary_mg`-Container (Zeile 33) ersetzen:

Aktuell:
```html
      <div class="col-md-3">{{ field("m_eq_primary_mg", "m_eq Primärstandard (mg/mL)", item.m_eq_primary_mg, type="number", step="0.001", help="mg Primärstandard pro mL Titrant bei Sollkonzentration. Für V_min/V_max-Berechnung bei Titereinstellung.") }}</div>
```

Ersetzen durch:
```html
      <div class="col-md-3">
        {{ field("m_eq_primary_mg", "m_eq Primärstandard (mg/mL)", item.m_eq_primary_mg, type="number", step="0.0001", help="mg Primärstandard pro mL Titrant bei Sollkonzentration. Wird automatisch aus c_Titrant × MW_PS / z berechnet.") }}
        <div class="form-check mt-n2 mb-2">
          <input type="checkbox" class="form-check-input" id="m_eq_primary_mg_override" name="m_eq_primary_mg_override"
            {% if item.m_eq_primary_mg_override %}checked{% endif %}>
          <label class="form-check-label small text-muted" for="m_eq_primary_mg_override">Manuell überschreiben</label>
        </div>
      </div>
```

- [ ] **Schritt 3: JS-Logik für Auto-Berechnung hinzufügen**

Im `<script>`-Block eine neue Funktion `updateMeqPrimary()` hinzufügen und in die Event-Listener einbinden.

Nach der `getFloat`-Funktion (nach Zeile 105) einfügen:

```javascript
  function updateMeqPrimary() {
    const overrideCheckbox = document.getElementById('m_eq_primary_mg_override');
    const meqInput = document.getElementById('m_eq_primary_mg');
    if (!overrideCheckbox || !meqInput) return;

    // Nur im Standardisierungsmodus aktiv – beim Laden der Seite ist currentCalcMode
    // noch null (async fetch läuft noch). In dem Fall Feld-Disabled-Status nicht ändern
    // und kein Blanking vornehmen.
    if (currentCalcMode !== MODE_STANDARDIZATION) return;

    const isOverride = overrideCheckbox.checked;
    meqInput.disabled = !isOverride;

    if (!isOverride) {
      const psId = document.getElementById('primary_standard_id')?.value;
      // psMolarMasses-Keys sind Strings (JSON-Serialisierung von Python-int → string key)
      const mwPS = psId ? (psMolarMasses[psId] ?? null) : null;
      const cTitrant = getFloat('c_titrant_mol_l');
      const z = getFloat('n_eq_titrant');

      if (mwPS && cTitrant && cTitrant > 0 && z && z > 0) {
        meqInput.value = (cTitrant * mwPS / z).toFixed(4);
      } else {
        meqInput.value = '';
      }
    }

    updateCalcPreview();
  }
```

- [ ] **Schritt 4: Event-Listener für updateMeqPrimary registrieren**

Nach Zeile 311 (`if (el) el.addEventListener('input', updateCalcPreview);`) bzw. am Ende des forEach-Blocks für die Parameter-Inputs, folgende Listener hinzufügen:

```javascript
  // Auto-Berechnung von m_eq_primary_mg steuern
  const overrideCheckbox = document.getElementById('m_eq_primary_mg_override');
  if (overrideCheckbox) overrideCheckbox.addEventListener('change', updateMeqPrimary);

  const psSelect = document.getElementById('primary_standard_id');
  if (psSelect) psSelect.addEventListener('change', updateMeqPrimary);

  ['c_titrant_mol_l', 'n_eq_titrant'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateMeqPrimary);
  });
```

Außerdem: `updateMeqPrimary()` muss **innerhalb** von `loadAnalysisDefaults()` aufgerufen werden, nachdem `currentCalcMode` gesetzt wurde (da es async ist). In der bestehenden `.then(data => {...})`-Callback:

```javascript
          currentCalcMode = data.calculation_mode || MODE_ASSAY;
          syncModeVisibility();
          updateMeqPrimary();    // ← neu: nach syncModeVisibility, da currentCalcMode nun gesetzt
          updateCalcPreview();
```

Der separate Aufruf `updateMeqPrimary()` am Ende des Skripts (nach `loadAnalysisDefaults()`) ist **nicht** nötig, da die Funktion aufgrund des `currentCalcMode`-Guards beim Seitenload sowieso nichts tut, solange der Fetch noch aussteht.

- [ ] **Schritt 5: Berechnungsvorschau erweitern – Formel für m_eq_PS zeigen**

In `updateCalcPreview()`, im `if (currentCalcMode === MODE_STANDARDIZATION)`-Block (ab Zeile 166), nach der Formelzeile für `f = ...` die Herleitung von `m_eq_PS` einblenden.

Aktuell (Zeile 176-178):
```javascript
      let html = '<strong>Formel (Titereinstellung):</strong><br>';
      html += 'f = (m<sub>PS</sub> &times; 1000) / (m_eq<sub>PS</sub> &times; V<sub>Titrant</sub>)<br>';
      html += '<span class="text-body-secondary">m<sub>PS</sub> = Einwaage Primärstandard (g), V<sub>Titrant</sub> = Verbrauch (mL)</span><br>';
```

Erweitern zu:
```javascript
      const cTitrant = getFloat('c_titrant_mol_l');
      const z = getFloat('n_eq_titrant') ?? 1.0;

      let html = '<strong>Formel (Titereinstellung):</strong><br>';
      html += 'f = (m<sub>PS</sub> &times; 1000) / (m_eq<sub>PS</sub> &times; V<sub>Titrant</sub>)<br>';
      html += '<span class="text-body-secondary">m<sub>PS</sub> = Einwaage Primärstandard (g), V<sub>Titrant</sub> = Verbrauch (mL)</span><br>';

      // Herleitung von m_eq_PS
      html += '<hr class="my-1">';
      html += '<strong>Herleitung m_eq<sub>PS</sub>:</strong> ';
      html += 'm_eq<sub>PS</sub> = c<sub>Soll</sub> &times; MW<sub>PS</sub> / z<br>';
      const psId = document.getElementById('primary_standard_id')?.value;
      const mwPS = psId ? (psMolarMasses[psId] ?? null) : null;
      if (cTitrant && mwPS && z) {
        const meqDerived = (cTitrant * mwPS / z);
        html += `<span class="text-body-secondary">= ${cTitrant} &times; ${mwPS} / ${z} = <strong>${meqDerived.toFixed(4)} mg/mL</strong></span><br>`;
      } else {
        html += '<span class="text-body-secondary">(Primärstandard, c_Soll und z eingeben um Ableitung zu sehen)</span><br>';
      }
      html += '<hr class="my-1">';
```

**Achtung – Variable Hoisting:** `cTitrant` und `z` werden aktuell an zwei Stellen in `updateCalcPreview()` deklariert (Zeile 167 im Standardization-Block, Zeile 202 im Assay-Block). Zwei `const`-Deklarationen gleichen Namens in derselben Funktion → `SyntaxError`. Lösung: beide Variablen **vor** das erste `if` hoisten und die inneren Deklarationen löschen:

```javascript
  function updateCalcPreview() {
    // Gemeinsame Variablen für beide Modi (hoisted, kein Duplikat)
    const cTitrant = getFloat('c_titrant_mol_l');
    const z = getFloat('n_eq_titrant') ?? 1.0;  // Std-Modus: z-Faktor; Assay-Modus: n_eq_titrant

    if (currentCalcMode === MODE_STANDARDIZATION) {
      // cTitrant & z bereits oben – NICHT erneut deklarieren
      const mEqPrimary = getFloat('m_eq_primary_mg');
      ...
    }

    // ── Assay Preview ──
    // cTitrant & z bereits oben – NICHT erneut deklarieren
    const mtype = methodTypeSelect.value;
    // const nEqTitrant = ... ← LÖSCHEN; z verwenden stattdessen
    ...
  }
```

Konkret zu löschen:
- Zeile 167: `const cTitrant = getFloat('c_titrant_mol_l');`
- Zeile 168: `const nEqPS = getFloat('n_eq_titrant') ?? 1.0;`
- Zeile 202 (nach `// ── Assay Preview ──`): die dortige `const cTitrant`-Deklaration
- Zeile 203: die dortige `const nEqTitrant`-Deklaration

Alle Vorkommen von `nEqTitrant` und `nEqPS` im Funktionsrumpf durch `z` ersetzen (insgesamt ca. 4-5 Stellen in den Beispielrechnungen).

- [ ] **Schritt 6: Initiales disabled-Zustand beim Laden sicherstellen**

`updateMeqPrimary()` wird beim Seitenload aufgerufen (Schritt 4). Damit ist das Input korrekt disabled wenn Override=false.

**Wichtig:** Beim Laden der Seite im Edit-Modus: bestehende Methoden mit `m_eq_primary_mg_override=True` haben das Input aktiviert (manuell editierbar). Methoden ohne Override haben das Input deaktiviert und zeigen den berechneten Wert.

- [ ] **Schritt 7: Ende-zu-Ende-Test im Browser**

1. Neue Methode anlegen (Analyse = Titereinstellung-Analyse wählen)
2. Primärstandard wählen (z.B. Natriumtetraborat)
3. c_Titrant = 0.1, z = 2 eingeben
4. Erwartung: m_eq_PS-Feld zeigt automatisch 19.0685 (= 0.1 × 381.37 / 2)
5. Berechnungsvorschau zeigt Formel und Ableitung
6. Override-Haken setzen → Feld wird editierbar
7. Override-Haken entfernen → Feld berechnet sich neu
8. Speichern → Wert korrekt in DB gespeichert
9. Formular wieder öffnen → Override=False, Feld zeigt berechneten Wert (disabled)

- [ ] **Schritt 8: Bestehende Methoden prüfen**

Eine bestehende Titereinstellung-Methode öffnen (z.B. HCl-Methode aus Seed-Daten).
Erwartung: Override-Checkbox ist angehakt (durch Backfill in Migration), m_eq_primary_mg-Feld ist editierbar mit dem alten Wert.

---

## Notizen

- Das `n_eq_titrant`-Feld in Standardisierungsmodus ist **nicht** redundant – es ist der z-Faktor. Beide Felder (`c_titrant_mol_l` als Sollkonzentration und `n_eq_titrant` als z) werden zur Ableitung von `m_eq_primary_mg` benötigt.
- Das Label "Äquivalente pro Mol Primärstandard" für `n_eq_titrant` im Standardisierungsmodus bleibt korrekt.
- Der `m_eq_primary_mg`-Wert in der DB ist immer gesetzt (entweder manuell oder auto-berechnet), da die Berechnung bereits beim Speichern serverseitig erfolgt. Das Frontend zeigt nur den Zustand.
