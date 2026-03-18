# Zielfaktor in Einwaagemaske (Titereinstellung) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In der Einwaagemaske für Titereinstellungs-Analysen den Zielfaktor (= V_disp / V_theoretisch) live und server-seitig anzeigen, damit Studierende wissen, welchen Faktor ihre hergestellte Maßlösung hat.

**Architecture:** Rein template-seitige Änderung in `weighing.html`. Für standardization-Mode wird eine neue Tabellenspalte „Zielfaktor" ergänzt, die server-seitig vorbelegt wird (für bereits gespeicherte Volumina) und per JavaScript live aktualisiert wird, während die TA das Volumen eingibt. Keine Änderungen an Datenbankmodellen, Backend-Routen oder Berechnungslogik notwendig.

**Tech Stack:** Jinja2 (Flask-Templates), JavaScript (vanilla), Bootstrap 5

---

## Hintergrund

Bei der Titereinstellung (z. B. „Einstellung 0,1 M Salzsäure") dispensiert die TA ein bestimmtes Volumen einer Stammlösung (z. B. 1 M HCl). Der Faktor der daraus hergestellten Maßlösung ergibt sich direkt aus dem dispensierten Volumen:

```
V_theoretisch = (e_ab_ps_g × 1000) / m_eq_primary_mg
Zielfaktor = V_disp / V_theoretisch
```

Beispiel: e_ab_ps_g = 0.100 g, m_eq_primary_mg = 10 mg/mL → V_theoretisch = 10 mL
→ V_disp = 9.46 mL → Zielfaktor = 9.46 / 10 = **0.9460**

Dieser Faktor muss in der Einwaagemaske sichtbar sein, damit die Studierenden wissen, welchen Faktor sie für ihre hergestellte Lösung angeben müssen.

## File Structure

| Datei | Änderung |
|-------|----------|
| `templates/ta/weighing.html` | Neue Spalte + Server-side Berechnung + JS-Erweiterung |

---

## Task 1: Zielfaktor-Spalte in weighing.html

**Files:**
- Modify: `templates/ta/weighing.html:39–51` (Tabellenkopf)
- Modify: `templates/ta/weighing.html:81–89` (Tabellenzellen pro Zeile)
- Modify: `templates/ta/weighing.html:120–148` (JS-Konstanten)
- Modify: `templates/ta/weighing.html:195–248` (JS-Event-Handler)

### Schritt 1a: Tabellenkopf ergänzen (Zielfaktor-Spalte)

Ändere den `{% else %}`-Block (Standardisierungs-Header) in den `<thead>`-Zeilen.

**Vor (Zeile 49–51):**
```html
{% else %}
<th style="width:180px">V_disp (mL)</th>
{% endif %}
```

**Nach:**
```html
{% else %}
<th style="width:180px">V_disp (mL)</th>
<th style="width:120px">Zielfaktor</th>
{% endif %}
```

- [ ] **Step 1: Tabellenkopf-Änderung in weighing.html vornehmen**

- [ ] **Step 2: Änderung manuell im Browser prüfen** (Spaltenüberschrift erscheint)

---

### Schritt 1b: Tabellenzelle für Zielfaktor (pro Zeile)

Der server-seitige Zielfaktor wird berechnet als `V_disp / V_theo`. Die Method-Felder `e_ab_ps_g` und `m_eq_primary_mg` sind über `batch.analysis.method` zugänglich.

**Vor (Zeile 81–89):**
```html
{% else %}
<td>
  <input type="text" class="form-control form-control-sm weighing-input {% if flags.volume_range_violation %}is-invalid{% endif %}"
         name="m_ges_{{ s.id }}" value="{{ s.m_ges_actual_g if s.m_ges_actual_g else '' }}"
         data-sample-id="{{ s.id }}" data-field="m_ges"
         placeholder="0.000" inputmode="decimal">
  <div class="field-hint text-danger small" data-hint-field="m_ges" {% if not flags.volume_range_violation %}style="display:none"{% endif %}>außerhalb Zielbereich</div>
</td>
{% endif %}
```

**Nach:**
```html
{% else %}
<td>
  <input type="text" class="form-control form-control-sm weighing-input {% if flags.volume_range_violation %}is-invalid{% endif %}"
         name="m_ges_{{ s.id }}" value="{{ s.m_ges_actual_g if s.m_ges_actual_g else '' }}"
         data-sample-id="{{ s.id }}" data-field="m_ges"
         placeholder="0.000" inputmode="decimal">
  <div class="field-hint text-danger small" data-hint-field="m_ges" {% if not flags.volume_range_violation %}style="display:none"{% endif %}>außerhalb Zielbereich</div>
</td>
<td class="text-end" id="factor-{{ s.id }}">
  {%- set _m = batch.analysis.method -%}
  {%- if s.m_ges_actual_g and _m and _m.e_ab_ps_g and _m.m_eq_primary_mg and _m.m_eq_primary_mg > 0 -%}
    {{ (s.m_ges_actual_g / (_m.e_ab_ps_g * 1000 / _m.m_eq_primary_mg)) | round(4) | fmt(4) }}
  {%- endif -%}
</td>
{% endif %}
```

- [ ] **Step 3: Tabellenzellen-Änderung vornehmen**

- [ ] **Step 4: Im Browser prüfen** (bei bereits gespeicherten Proben erscheint der Zielfaktor in der neuen Spalte)

---

### Schritt 1c: JavaScript-Konstante V_THEORETICAL_ML

Direkt unterhalb von `TARGET_V_MAX_ML` (Zeile 147) wird die Konstante V_THEORETICAL_ML ergänzt.

**Vor (Zeile 144–148):**
```javascript
const TARGET_M_S_MIN_G = {{ batch.target_m_s_min_g if batch.target_m_s_min_g is not none else 'null' }};
const TARGET_M_GES_G = {{ batch.target_m_ges_g if batch.target_m_ges_g is not none else 'null' }};
const TARGET_V_MIN_ML = {{ batch.target_v_min_ml if batch.target_v_min_ml is not none else 'null' }};
const TARGET_V_MAX_ML = {{ batch.target_v_max_ml if batch.target_v_max_ml is not none else 'null' }};
```

**Nach:**
```javascript
const TARGET_M_S_MIN_G = {{ batch.target_m_s_min_g if batch.target_m_s_min_g is not none else 'null' }};
const TARGET_M_GES_G = {{ batch.target_m_ges_g if batch.target_m_ges_g is not none else 'null' }};
const TARGET_V_MIN_ML = {{ batch.target_v_min_ml if batch.target_v_min_ml is not none else 'null' }};
const TARGET_V_MAX_ML = {{ batch.target_v_max_ml if batch.target_v_max_ml is not none else 'null' }};
{% if is_standardization %}
{%- set _m = batch.analysis.method -%}
const V_THEORETICAL_ML = {{ (_m.e_ab_ps_g * 1000 / _m.m_eq_primary_mg) | round(4) if _m and _m.e_ab_ps_g and _m.m_eq_primary_mg and _m.m_eq_primary_mg > 0 else 'null' }};
{% endif %}
```

- [ ] **Step 5: JS-Konstante ergänzen**

---

### Schritt 1d: JS-Event-Handler für Live-Berechnung

Im Standardisierungs-Zweig des Event-Handlers (nach `evaluateLimits`) den Zielfaktor berechnen und anzeigen.

**Vor (Zeile 244–246):**
```javascript
    const limFlags = evaluateLimits(ms, mges);
    applyLimitUi(row, limFlags, ms, mges);
  });
```

**Nach:**
```javascript
    const limFlags = evaluateLimits(ms, mges);
    applyLimitUi(row, limFlags, ms, mges);

    // Live Zielfaktor für Titereinstellung
    if (MODE === 'titrant_standardization') {
      const factorCell = document.getElementById('factor-' + sid);
      if (factorCell && V_THEORETICAL_ML !== null && V_THEORETICAL_ML > 0 && !isNaN(mges)) {
        factorCell.textContent = (mges / V_THEORETICAL_ML).toFixed(4);
      } else if (factorCell && isNaN(mges)) {
        factorCell.textContent = '';
      }
    }
  });
```

- [ ] **Step 6: JS-Event-Handler erweitern**

- [ ] **Step 7: Funktionstest im Browser**
  - Einen Probensatz mit Titereinstellungs-Analyse öffnen
  - Volumen eintippen → Zielfaktor erscheint live
  - Beispiel: V_theo = 10 mL, V_disp = 9.46 → Zielfaktor = 0.9460

- [ ] **Step 8: Commit**

```bash
git add templates/ta/weighing.html
git commit -m "feat: show Zielfaktor live in weighing mask for titrant standardization

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Randbemerkungen

- Der Zielfaktor ist rein informativ; er wird weder gespeichert noch in Berechnungen verwendet.
- `V_THEORETICAL_ML` ist dieselbe Formel, die bereits im API-Endpunkt `/api/analysis/<id>/defaults` (app.py:1878) berechnet wird.
- Falls `m_eq_primary_mg` oder `e_ab_ps_g` nicht konfiguriert sind, bleibt die Zielfaktor-Zelle leer (kein Fehler).
- Der Jinja2-Filter `fmt(4)` muss verfügbar sein (ist bereits in der Basis-Template-Konfiguration registriert).
