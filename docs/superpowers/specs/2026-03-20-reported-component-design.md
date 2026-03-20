# Design: Reported Component für Elementgehaltsbestimmung

**Datum:** 2026-03-20
**Status:** Approved
**Betrifft:** Versuch III.1 (Phosphorgehalt) und zukünftige Elementgehaltsbestimmungen

---

## Hintergrund

Bei Versuch III.1 wird der **Phosphorgehalt** (% P) der Probe Na₂HPO₄·2H₂O bestimmt — nicht der Gehalt der Substanz selbst. Die Methode fällt Phosphat als MgNH₄PO₄, löst es in HCl auf und titriert das freigesetzte Mg²⁺ komplexometrisch (EDTA-Überschuss, Rücktitration mit ZnSO₄).

Die stöchiometrische Kette lautet:
`1 P ≙ 1 PO₄³⁻ ≙ 1 MgNH₄PO₄ ≙ 1 Mg²⁺ ≙ 1 EDTA`

Das Ergebnis soll in **% P** angegeben werden. Diese Anforderung gilt unabhängig davon, welche Phosphatverbindung eingewogen wird (Na₂HPO₄·2H₂O, Na₂HPO₄, H₃PO₄, etc.) — die molare Masse der Substanz wird stets korrekt aus dem Substanzmodell genommen.

---

## Anforderungen

- Der **Zielwert (g_wahr)** in der Einwaagemaske soll in % P ausgedrückt sein
- Das **Analysenergebnis** der Studierenden soll in % P verglichen werden
- Die Lösung soll generisch sein (nicht nur für P, auch für andere Elemente/Komponenten)
- **Kein Breaking Change** für bestehende Analysen ohne Elementgehaltsbestimmung

---

## Entscheidung: Ansatz A — Zwei Felder auf `Analysis`

### Neue Felder

| Feld | Typ | Default | Bedeutung |
|---|---|---|---|
| `reported_molar_mass_gmol` | Float, nullable | `None` | Molare Masse der berichteten Komponente (z.B. 30,974 g/mol für P) |
| `reported_stoichiometry` | Float, nullable | `None` (= 1.0) | Anzahl berichteter Einheiten pro Formeleinheit der Substanz |

`reported_stoichiometry` ist `Float` (nicht `Integer`), konsistent mit allen anderen numerischen Methodenparametern (`n_eq_titrant` etc.) und um nichtstöchiometrische Verhältnisse nicht auszuschließen.

**Wenn `reported_molar_mass_gmol` `None`:** bisheriges Verhalten (inkl. Hydratkorrektur) bleibt exakt erhalten — `reported_stoichiometry` wird dann ignoriert.

**Prioritätsregel:** `reported_molar_mass_gmol` hat Vorrang vor der Hydratkorrektur (`anhydrous_molar_mass_gmol`). Die beiden dürfen nicht gleichzeitig für dieselbe Analyse sinnvoll aktiv sein; bei gesetztem `reported_molar_mass_gmol` wird die Hydratkorrektur vollständig übersprungen.

### Konfiguration III.1

```
reported_molar_mass_gmol = 30.974   # M(P)
reported_stoichiometry   = 1.0      # 1 P pro Na₂HPO₄·2H₂O
```

In `init_db.py` werden diese Werte als **Post-Flush-Attributzuweisungen** gesetzt (gleiche Pattern wie `c_titrant_mol_l`, `n_eq_titrant` etc.), nicht als Erweiterung des `ana_data`-Tupels.

### Beispielrechnung (300,0 mg Na₂HPO₄·2H₂O, p = 100%)

```
g_wahr(P) = 100% × (1,0 × 30,974) / 177,99 = 17,40%
```

Bei Na₂HPO₄ (gleiche Analyse, andere Substanz):
```
g_wahr(P) = 100% × (1,0 × 30,974) / 141,96 = 21,82%
```

---

## Berechnung

### g_wahr (`calculation_modes.py`)

Voraussetzung: `substance.molar_mass_gmol is not None and substance.molar_mass_gmol > 0` (guard bereits im bestehenden Code, gilt gleichermaßen für den neuen Zweig).

```python
if analysis.reported_molar_mass_gmol is not None:
    n = analysis.reported_stoichiometry or 1.0
    correction = (n * analysis.reported_molar_mass_gmol) / substance.molar_mass_gmol
else:
    # bisherige Hydratkorrektur
    correction = anhydrous_mw / hydrate_mw  # falls Hydrat, sonst 1.0
```

`a_min` / `a_max` (Toleranzgrenzen) werden weiterhin relativ zu `g_wahr` berechnet (`g_wahr × tol / 100`). Das ist korrekt: wenn `g_wahr` in % P ausgedrückt ist, sind die Grenzen ebenfalls in % P — dimensionsgleich, kein Sonderfall nötig.

### Ergebnisberechnung: n → m (`calculation_modes.py`)

```python
if analysis.reported_molar_mass_gmol is not None:
    n = analysis.reported_stoichiometry or 1.0
    m_reported = n_net_mmol * n * analysis.reported_molar_mass_gmol
else:
    m_reported = n_net_mmol * substance.molar_mass_gmol  # bisheriges Verhalten
```

### V_erw (`_v_expected_explicit` / `_v_expected_legacy`)

Wenn `reported_molar_mass_gmol` gesetzt ist, verwendet `_v_expected_explicit` als effektive Molmasse:

```python
if analysis.reported_molar_mass_gmol is not None:
    n = analysis.reported_stoichiometry or 1.0
    mw_effective = n * analysis.reported_molar_mass_gmol
else:
    mw_effective = substance.anhydrous_molar_mass_gmol or substance.molar_mass_gmol
```

Dann:
```python
n_analyte_mmol = (e_ab_mg * g_wahr / 100.0) / mw_effective
```

**Begründung:** `g_wahr` ist nun „% P". Um von „mg P in der Einwaage" auf „mmol Analyt (= Mg²⁺)" zurückzurechnen, teilt man durch `n × M(P)` — denn `n_stoich × M(P)` ist die Masse, die einem Mol Analyt entspricht.

Für III.1 mit 300,0 mg und g_wahr = 17,40%:
```
m_P = 300,0 × 17,40/100 = 52,2 mg
n_Mg = 52,2 / (1,0 × 30,974) = 1,685 mmol  →  korrekt
```

---

## Abgelehnte Alternativen

**Ansatz B — `ReportedComponent`-Modell (FK):**
Wiederverwendbarkeit erst sinnvoll bei 5+ Analysen mit demselben Element. Aktuell YAGNI.

**Ansatz C — Vorbrechenter `result_conversion_factor`:**
Semantisch opak, fehleranfällig bei Substanzwechsel.

---

## Scope

- **DB-Migration:** 2 neue nullable Float-Spalten `reported_molar_mass_gmol` und `reported_stoichiometry` auf `analysis`-Tabelle via `flask db migrate` (Alembic auto-generation)
- **`calculation_modes.py`:** Guard-Bedingung an drei Stellen: `_g_wahr`, n→m-Konversion, `_v_expected_explicit`
- **`init_db.py`:** III.1 bekommt die zwei neuen Felder als Post-Flush-Zuweisungen
- **Admin-UI** (`analysis`-Formular): zwei neue optionale Float-Felder
- **Tests:** g_wahr, Ergebnisberechnung und V_erw für den Phosphorgehalt-Fall

**Nicht im Scope:** Anzeige des Element-Symbols in der Ergebnisansicht (`result_label` deckt das bereits ab).
