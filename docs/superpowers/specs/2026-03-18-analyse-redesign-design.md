# Design: Analyse-Terminologie, Bug-Fixes & Live-Bewertung

**Datum:** 2026-03-18
**Status:** Approved
**Ansatz:** Alles in einem PR

---

## Überblick

Dieses Design adressiert fünf zusammenhängende Änderungen am quanti-lims-System:

1. Terminologie-Fix: „Erstanalyse" vs. „A-Analyse" (konzeptioneller Fehler)
2. Bug-Fix: Zuweisungs-Zählung ignoriert Einwagestatus
3. Bug-Fix: Toleranzberechnung im Titrant-Standardization-Modus falsch
4. Neues Feature: Ergebnis-Widerruf
5. Neues Feature: Live-Bewertung bei Ergebniseingabe

---

## 1. Terminologie-Fix: Erstanalyse vs. A-Analyse

### Problem

Die Erstanalyse (erster Versuch eines Studierenden) wird im Code und UI fälschlicherweise als „A-Analyse" bezeichnet. Korrekt ist:

- **Erstanalyse** = attempt_number 1 (kein Wiederholungsbuchstabe)
- **A-Analyse** = erste Wiederholungsanalyse = attempt_number 2
- **B-Analyse** = zweite Wiederholungsanalyse = attempt_number 3
- **C-Analyse**, **D-Analyse**, ... = weitere Wiederholungen (unbegrenzt)

### Neues Mapping

| attempt_number | attempt_type (alt) | attempt_type (neu) |
|---------------|--------------------|--------------------|
| 1 | "A" | "Erstanalyse" |
| 2 | "B" | "A" |
| 3 | "C" | "B" |
| 4 | "D" | "C" |
| n ≥ 2 | gecapped auf "D" | chr(ord('A') + n - 2) → unbegrenzt |

Die bisherige Kappe auf "D" entfällt. Die Formel für attempt_number ≥ 2:
```python
attempt_type = chr(ord('A') + attempt_number - 2)
```

### DB-Migration (Alembic)

```sql
UPDATE sample_assignment SET attempt_type = 'Erstanalyse' WHERE attempt_number = 1;
UPDATE sample_assignment SET attempt_type = 'A' WHERE attempt_number = 2;
UPDATE sample_assignment SET attempt_type = 'B' WHERE attempt_number = 3;
UPDATE sample_assignment SET attempt_type = 'C' WHERE attempt_number = 4;
-- attempt_number >= 5: chr(ord('A') + attempt_number - 2) via Python loop
```

### UI

- `"Erstanalyse"` → grauer Badge
- `"A"`, `"B"`, `"C"`, ... → farbige Badges (wie bisher für Wiederholungen)

---

## 2. Bug-Fix: Zuweisungs-Zählung

### Problem

`admin_batch_assign_initial()` legt Zuweisungen für alle n Studierenden an, unabhängig ob die zugehörige Probe eingewogen ist. Resultat: Zuweisungen für Proben, die de facto nicht existieren.

### Fix

Vor dem Anlegen einer Zuweisung werden zwei Bedingungen geprüft:

1. Sample mit passendem `running_number` existiert
2. Sample ist vollständig eingewogen: `m_s_actual_g is not None` AND `m_ges_actual_g is not None`

Nur bei Erfüllung beider Bedingungen wird die Zuweisung angelegt.

### Rückmeldung

Flash-Message mit Aufschlüsselung:
> „3 von 5 Proben zugewiesen (2 Proben noch nicht eingewogen)."

Nicht zugewiesene Studierende werden in der UI mit Status „Probe noch nicht bereit" markiert.

---

## 3. Bug-Fix: Toleranzberechnung (Titrant Standardization)

### Problem

In `TitrantStandardizationMode.calculate_sample()` werden die Toleranzgrenzen als absolute Werte berechnet:

```python
titer_min = tol_min / 100   # z.B. 0.98 – fix, unabhängig vom Probenfaktor
titer_max = tol_max / 100   # z.B. 1.02
```

Dies ist falsch. Die Toleranzgrenzen beziehen sich stets auf den **wahren Wert** (titer_expected) der Probe.

### Korrekte Formel

```python
titer_min = titer_expected * (1 - tol_min / 100)
titer_max = titer_expected * (1 + tol_max / 100)
```

**Beispiel:** titer_expected = 0.9400, tol = ±2%
- titer_min = 0.9400 × 0.98 = **0.9212**
- titer_max = 0.9400 × 1.02 = **0.9588**

Die bestehende Toleranzquellen-Hierarchie (tolerance_override > g_ab > Substance-Default) bleibt unverändert.

### Betroffene Datei

Nur `calculation_modes.py`, Klasse `TitrantStandardizationMode`, Methode `calculate_sample()`. Die `assay_mass_based`-Berechnung ist korrekt und bleibt unverändert.

---

## 4. Neues Feature: Ergebnis-Widerruf

### Verhalten

Ein Admin kann ein eingereichtes Ergebnis widerrufen:

1. `Result.revoked = True`, `Result.revoked_by`, `Result.revoked_date` werden gesetzt
2. `SampleAssignment.status` kehrt zurück zu `"assigned"`
3. Der Student kann eine neue Ansage einreichen
4. Das widerrufene Ergebnis bleibt in der DB sichtbar (durchgestrichen, Datum + Widerrufer angezeigt)
5. Widerrufene Ergebnisse werden bei der Pass/Fail-Auswertung ignoriert

### Neues Datenmodell (Result)

```python
revoked       = Column(Boolean, default=False)
revoked_by    = Column(String(100), nullable=True)
revoked_date  = Column(String(20), nullable=True)
```

DB-Migration erforderlich.

### Route & UI

- Neue Route: `POST /results/<int:result_id>/revoke`
- In der Ergebnisübersicht: Widerruf-Button neben jedem aktiven Ergebnis (nur Admins)
- Widerrufene Ergebnisse: durchgestrichen dargestellt mit Label „Widerrufen am [Datum] von [Benutzer]"

---

## 5. Neues Feature: Live-Bewertung bei Ergebniseingabe

### Datenweitergabe Server → Browser

Beim Laden von `/results/submit/<id>` übergibt der Server die Bewertungsparameter als JSON ins Template:

```json
{
  "titer_expected": 0.9400,
  "tol_min_pct": 2.0,
  "tol_max_pct": 2.0,
  "attempt_type": "Erstanalyse",
  "mode": "titrant_standardization"
}
```

Für `assay_mass_based` analog mit `g_wahr`, `a_min`, `a_max`.

### Bewertungslogik (JavaScript, plain – kein Framework)

Relative Abweichung vom wahren Wert:
```
δ = (eingabe − wahr) / wahr × 100
T_min, T_max = tol_min_pct, tol_max_pct
```

Stufenzuordnung (asymmetrisch, da tol_min ≠ tol_max möglich):

| Symbol | Bedingung |
|--------|-----------|
| `f↑↑↑` | δ > 4 × T_max |
| `f↑↑` | 2 × T_max < δ ≤ 4 × T_max |
| `f↑` | T_max < δ ≤ 2 × T_max |
| `✓` | −T_min ≤ δ ≤ T_max |
| `f↓` | −2 × T_min ≤ δ < −T_min |
| `f↓↓` | −4 × T_min ≤ δ < −2 × T_min |
| `f↓↓↓` | δ < −4 × T_min |

### Konsequenz-Anzeige

| attempt_type | Ergebnis falsch | Anzeige |
|-------------|-----------------|---------|
| "Erstanalyse" | f↑/f↓/etc. | `f↑ → A` |
| "A" | f↑/f↓/etc. | `f↑ → B` |
| "B" | f↑/f↓/etc. | `f↑ → C` |
| beliebig | ✓ | `✓ bestanden` |

Bei leerem oder ungültigem Eingabewert: kein Badge.

### Persistenz

Neues Feld `Result.evaluation_label` (String, z.B. `"f↑ → A"` oder `"✓"`), das bei Submission gesetzt und in der Ergebnisübersicht dauerhaft angezeigt wird.

DB-Migration erforderlich.

---

## Betroffene Dateien (Zusammenfassung)

| Datei | Änderungen |
|-------|------------|
| `models.py` | Result: +`revoked`, `revoked_by`, `revoked_date`, `evaluation_label` |
| `calculation_modes.py` | TitrantStandardizationMode: Toleranzformel korrigiert |
| `app.py` | Assignment-Filter, Widerruf-Route, Submit-Route (evaluation_label), JSON-Ausgabe für Live-Bewertung |
| `templates/results/submit.html` | Live-Bewertungs-JS + Badge-Anzeige |
| `templates/results/overview.html` | Widerruf-Button, evaluation_label, revoked-Darstellung |
| `templates/assignments/overview.html` | Erstanalyse-Badge, „Probe noch nicht bereit"-Status |
| `migrations/versions/XXXX_analyse_redesign.py` | Alembic-Migration für attempt_type + neue Result-Felder |
