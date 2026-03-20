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
| `reported_stoichiometry` | Integer, nullable | `None` (= 1) | Anzahl berichteter Einheiten pro Formeleinheit der Substanz |

**Wenn beide `None`:** bisheriges Verhalten (inkl. Hydratkorrektur) bleibt exakt erhalten.

### Konfiguration III.1

```
reported_molar_mass_gmol = 30.974   # M(P)
reported_stoichiometry   = 1        # 1 P pro Na₂HPO₄·2H₂O
```

### Beispielrechnung (300,0 mg Na₂HPO₄·2H₂O, p = 100%)

```
g_wahr(P) = 100% × (1 × 30,974) / 177,99 = 17,40%
```

Bei Na₂HPO₄ (gleiche Analyse, andere Substanz):
```
g_wahr(P) = 100% × (1 × 30,974) / 141,96 = 21,82%
```

---

## Berechnung

### g_wahr (`calculation_modes.py`)

```python
if analysis.reported_molar_mass_gmol is not None:
    n = analysis.reported_stoichiometry or 1
    correction = (n * analysis.reported_molar_mass_gmol) / substance.molar_mass_gmol
else:
    # bisherige Hydratkorrektur
    correction = anhydrous_mw / hydrate_mw  # falls Hydrat, sonst 1.0
```

### Ergebnisberechnung: n → m

```python
if analysis.reported_molar_mass_gmol is not None:
    n = analysis.reported_stoichiometry or 1
    m_reported = n_net_mmol * n * analysis.reported_molar_mass_gmol
else:
    m_reported = n_net_mmol * substance.molar_mass_gmol  # bisheriges Verhalten
```

---

## Abgelehnte Alternativen

**Ansatz B — `ReportedComponent`-Modell (FK):**
Wiederverwendbarkeit erst sinnvoll bei 5+ Analysen mit demselben Element. Aktuell YAGNI.

**Ansatz C — Vorbrechenter `result_conversion_factor`:**
Semantisch opak, fehleranfällig bei Substanzwechsel.

---

## Scope

- DB-Migration: 2 neue nullable Spalten auf `analysis`
- `calculation_modes.py`: Guard-Bedingung an zwei Stellen (g_wahr + n→m)
- `init_db.py`: III.1 bekommt die zwei neuen Felder
- Admin-UI (`analysis`-Formular): zwei neue optionale Felder
- Tests: g_wahr und Ergebnisberechnung für Phosphorgehalt-Fall

**Nicht im Scope:** Anzeige des Element-Symbols in der Ergebnisansicht (result_label deckt das bereits ab).
