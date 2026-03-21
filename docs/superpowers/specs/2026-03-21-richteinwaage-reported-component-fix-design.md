# Design: Fix Richteinwaage-Berechnung für Reported-Component-Analysen (III.1)

**Datum:** 2026-03-21
**Status:** Genehmigt

---

## Problem

Für Analyse III.1 (Phosphorgehalt, Na₂HPO₄·2H₂O) werden die automatisch berechneten
Richteinwaagen (`target_m_s_min_g`) falsch berechnet. Das System schlägt ~0.15 g vor,
obwohl ~0.85 g korrekt wären.

### Hintergrund

Bei reported-component-Analysen (erkennbar an gesetztem `reported_molar_mass_gmol`) wird
der **Elementgehalt** (z.B. %P) statt des Substanzgehalts gemessen. Die TA bereitet einen
Verschnitt aus Substanz (Na₂HPO₄·2H₂O) + Füllstoff (NaCl) vor; der Student wiegt ~300 mg
des Verschnitts ein. m_s = Masse der Substanz im Verschnitt, m_ges = Gesamtmasse des Verschnitts.

Die zentrale Umrechnungsgröße ist:

```
CONTENT_FACTOR = reported_stoichiometry × reported_molar_mass_gmol / molar_mass_gmol
               = 1.0 × 30.974 / 177.99 = 0.1740   (für III.1)
```

`g_wahr = (m_s / m_ges) × p_eff × CONTENT_FACTOR`  → ergibt %P
(p_eff und g_wahr sind beide in Prozent, z.B. 99.5 und 17.13)

Das Feld `gehalt_min_pct` im Batch-Formular enthält den **Mindest-Phosphorgehalt in %**
(z.B. 15 %), nicht den Substanzanteil im Verschnitt.

---

## Gefundene Bugs

### Bug 1 — JS `recalcMassFields()` in `batch_form.html` (Hauptfehler)

**Aktuelle Formel:**
```javascript
const mSMin = +(mGesMin * gehaltMin / 100).toFixed(3);
// Bei mGesMin=0.99 g, gehaltMin=15 → mSMin = 0.149 g  ← falsch
```

`gehaltMin` ist hier 15 (% Phosphor), wird aber wie ein Substanzanteil (%) behandelt.
Korrekt wäre: Substanzanteil im Verschnitt = gehaltMin / (100 × CONTENT_FACTOR).

**Korrekte Formel:**
```javascript
const mSMin = contentFactor
  ? +(mGesMin * gehaltMin / (100 * contentFactor)).toFixed(3)
  : +(mGesMin * gehaltMin / 100).toFixed(3);
// Bei mGesMin=0.99 g, gehaltMin=15, contentFactor=0.174 → mSMin = 0.854 g  ✓
```

Der falsche JS-Wert wird ins Formular geschrieben und überschreibt den server-seitigen
Fallback, da dieser nur greift wenn das Feld leer ist.

### Bug 2 — API `/api/analysis/defaults` gibt kein `reported_molar_mass_gmol` zurück

Die JS-Seite kann CONTENT_FACTOR nicht berechnen, weil `reported_molar_mass_gmol` und
`reported_stoichiometry` fehlen. Hinweis: `reported_stoichiometry` kann NULL in der DB
sein; der Client soll `?? 1.0` als Default verwenden.

### Bug 3 — Server-seitiger Fallback (app.py ~Zeile 1248)

Die aktuelle Implementierung verwendet eine falsche Formel:

```python
# Aktuell (falsch — verwendet Reinheitstoleranzen statt Elementgehalt):
g_ab_min = analysis.g_ab_min_pct if analysis.g_ab_min_pct is not None else 98.0
computed_m_s = round(e_ab * g_ab_min / 100.0, 3)
# = 0.3 × 0.98 = 0.294 g  ← bedeutungslos als "Mindest-Substanzmasse im Verschnitt"
```

Der begleitende Code-Kommentar ("per-determination minimum, derived from e_ab and substance
purity tolerance") beschreibt eine falsche Interpretation. `target_m_s_min_g` ist die
**Mindest-Substanzmasse im Verschnitt** (nicht eine pro-Bestimmung-Grenze). Für
reported-component-Analysen gilt dieselbe Logik wie für reguläre Analysen — nur mit
CONTENT_FACTOR als Umrechnungsfaktor.

**Korrekte Formel:**
```python
n = analysis.reported_stoichiometry or 1.0
substance = analysis.substance
cf = (n * analysis.reported_molar_mass_gmol / substance.molar_mass_gmol
      if substance and substance.molar_mass_gmol else 1.0)
computed_m_s = round(computed_m_ges * gehalt_min / (100.0 * cf), 3)
# = 0.99 × 15 / (100 × 0.174) = 0.854 g  ✓
```

### Bug 4 — `evaluate_weighing_limits()` in `app.py`: `hydrate_factor` statt `content_factor`

Die Python-Funktion berechnet:
```python
hydrate_factor = (mw_a / mw) if (mw_a and mw and mw > 0) else 1.0
m_ges_max = m_s_actual_g * p_eff * hydrate_factor / p_min
```

Für III.1 ist `anhydrous_molar_mass_gmol = NULL`, daher `hydrate_factor = 1.0`.
Korrekt wäre `content_factor = 0.174`, sodass `m_ges_max` ~6× kleiner ausfällt.

**Zusätzlich:** Das `checks.append()`-Format-String auf den folgenden Zeilen referenziert
`hydrate_factor={hydrate_factor:.4f}` — nach dem Fix muss dies auf `content_factor`
umgestellt werden, sonst entsteht ein `NameError` bei Verletzungen.

**Hinweis:** Die JS-Funktion `evaluateLimits()` in `weighing.html` verwendet bereits korrekt
`CONTENT_FACTOR` (Zeile 250). Nur der Orientierungshinweis (Zeile 437-438) verwendet noch
`HYDRATE_FACTOR` — das ist der fünfte Fix.

### Bug 5 — Orientierungshinweis in `weighing.html` (Zeile 437-438)

```javascript
// Aktuell (falsch):
const maxAtMin = ... ? mSMin * P_EFF * HYDRATE_FACTOR / P_MIN : null;
// Korrekt:
const maxAtMin = ... ? mSMin * P_EFF * CONTENT_FACTOR / P_MIN : null;
```

---

## Lösung (Option B)

### Änderung 1 — `app.py`: API-Endpoint erweitern

In `api_analysis_defaults()` (außerhalb des `if method:` Blocks):

```python
result["reported_molar_mass_gmol"] = analysis.reported_molar_mass_gmol
result["reported_stoichiometry"]   = analysis.reported_stoichiometry
```

### Änderung 2 — `templates/admin/batch_form.html`: JS-Logik korrigieren

Nach dem Laden der API-Defaults CONTENT_FACTOR berechnen (in `analysisSelect.addEventListener`
nach `currentDefaults` Zuweisung):

```javascript
const reportedMw     = currentDefaults.reported_molar_mass_gmol;  // null wenn nicht gesetzt
const reportedStoich = currentDefaults.reported_stoichiometry ?? 1.0;
const molarMass      = currentDefaults.molar_mass_gmol;
const contentFactor  = (reportedMw && molarMass && molarMass > 0)
  ? (reportedStoich * reportedMw) / molarMass
  : null;
```

`mSMin`-Berechnung in `recalcMassFields()`:

```javascript
const mSMin = contentFactor
  ? +(mGesMin * gehaltMin / (100 * contentFactor)).toFixed(3)
  : +(mGesMin * gehaltMin / 100).toFixed(3);
```

Hinweistext — zwei Varianten:

```javascript
massCalcDetail.textContent = contentFactor
  ? `Berechnung (Elementgehalt): E_AB (${eAb} g) × (${kDet} + ${nExtra} Zusatz) × ` +
    `${mortarF} Mörserfaktor = ${mGesMin} g Mindest-Gesamt; ` +
    `${mGesMin} g × ${gehaltMin}% / (100 × ${contentFactor.toFixed(4)}) = ${mSMin} g Mindest-Substanz ` +
    `[max. ${(contentFactor * 100).toFixed(2)}% Elementgehalt bei reiner Substanz]`
  : `Berechnung: E_AB (${eAb} g) × (${kDet} + ${nExtra} Zusatz) × ${mortarF} Mörserfaktor` +
    ` = ${mGesMin} g Mindest-Gesamt; davon ${gehaltMin}% = ${mSMin} g Mindest-Substanz`;
```

`recalcMassFields()` liest `currentDefaults` bereits direkt (die Funktion ist eine Closure).
Daher wird `contentFactor` direkt innerhalb von `recalcMassFields()` aus `currentDefaults`
berechnet — keine zusätzliche Scope-Variable nötig:

```javascript
function recalcMassFields() {
  if (!currentDefaults) return;
  const eAb = currentDefaults.e_ab_g;
  // ... bestehende Variablen ...
  const reportedMw     = currentDefaults.reported_molar_mass_gmol;
  const reportedStoich = currentDefaults.reported_stoichiometry ?? 1.0;
  const molarMass      = currentDefaults.molar_mass_gmol;
  const contentFactor  = (reportedMw && molarMass && molarMass > 0)
    ? (reportedStoich * reportedMw) / molarMass
    : null;
  // ... mGesMin Berechnung unverändert ...
  const mSMin = contentFactor
    ? +(mGesMin * gehaltMin / (100 * contentFactor)).toFixed(3)
    : +(mGesMin * gehaltMin / 100).toFixed(3);
  // ...
}
```

### Änderung 3 — `app.py`: Server-seitiger Fallback korrigieren (Zeilen ~1248-1255)

```python
if analysis.reported_molar_mass_gmol is not None:
    substance = analysis.substance
    n = analysis.reported_stoichiometry or 1.0
    cf = (n * analysis.reported_molar_mass_gmol / substance.molar_mass_gmol
          if substance and substance.molar_mass_gmol else 1.0)
    computed_m_s = round(computed_m_ges * gehalt_min / (100.0 * cf), 3)
else:
    computed_m_s = round(computed_m_ges * gehalt_min / 100.0, 3)
# target_m_ges_g ist unverändert — computed_m_ges = e_ab × k_total × mortar_f gilt für
# beide Fälle (reported-component und regulär).
```

### Änderung 4 — `app.py`: `evaluate_weighing_limits()` content_factor verwenden

**Zeilen 91–94 (bestehend) vollständig ersetzen** — `substance`, `mw`, `mw_a` und
`hydrate_factor` — durch den folgenden Block (`content_factor` ersetzt `hydrate_factor`
durchgängig, einschließlich des `checks.append()` Format-Strings):

```python
# Ersetzt Zeilen 91-94:
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

# Zeile 100: hydrate_factor= → content_factor=
m_ges_max = m_s_actual_g * p_eff * content_factor / p_min

# checks.append() Format-String (Zeile ~106):
# hydrate_factor={hydrate_factor:.4f}  →  content_factor={content_factor:.4f}
```

### Änderung 5 — `templates/ta/weighing.html`: Orientierungshinweis

```javascript
// Zeile 437-438: HYDRATE_FACTOR → CONTENT_FACTOR
const maxAtMin = (P_MIN && P_MIN > 0 && P_EFF && P_EFF > 0 && mSMin > 0)
  ? mSMin * P_EFF * CONTENT_FACTOR / P_MIN : null;
```

---

## Verifikation

Nach dem Fix für III.1 mit typischen Werten (k=2, n_extra=1, mortar=1.1, gehalt_min=15%,
p_eff=99.5%, anhydrous_molar_mass_gmol=NULL → hydrate_factor=1.0 vor Fix):

| Größe | Vorher (falsch) | Nachher (korrekt) |
|---|---|---|
| `mSMin` (Batch-Formular) | 0.149 g | **0.854 g** |
| `mGesMin` | 0.990 g | 0.990 g (unverändert) |
| `m_ges_max` bei m_s=0.854 g, p_eff=99.5 | 5.67 g | **0.987 g** |
| Orientierungshinweis max. m_ges | falsch | korrekt |

Kontrollrechnung: g_wahr = (0.854/0.990) × 99.5% × 0.174 = 14.97 % P ≥ 15.0 % (Grenzfall ✓)
Exakt bei p_eff=99.5%: m_s_min = m_ges × p_min / (p_eff × cf) = 0.990 × 15 / (99.5 × 0.174) = 0.858 g

---

## Betroffene Dateien

1. `app.py` — `api_analysis_defaults()`, Batch-Fallback (~Z.1248), `evaluate_weighing_limits()` (~Z.87-107)
2. `templates/admin/batch_form.html` — JS `recalcMassFields()`: `contentFactor` wird lokal innerhalb der Funktion aus `currentDefaults` berechnet (keine äußere Scope-Variable nötig)
3. `templates/ta/weighing.html` — Orientierungshinweis (~Z.437-438)

Keine Datenbankänderungen erforderlich.
