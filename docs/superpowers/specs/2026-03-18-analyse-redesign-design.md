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
- **C-Analyse**, **D-Analyse**, ... = weitere Wiederholungen (theoretisch unbegrenzt)

### Neues Mapping

| attempt_number | attempt_type (alt) | attempt_type (neu) |
|---------------|--------------------|--------------------|
| 1 | "A" | "Erstanalyse" |
| 2 | "B" | "A" |
| 3 | "C" | "B" |
| 4 | "D" | "C" |
| n ≥ 2 | gecapped auf "D" | chr(ord('A') + n - 2) |

Die bisherige Kappe auf "D" entfällt. Die Formel für attempt_number ≥ 2:
```python
attempt_type = chr(ord('A') + attempt_number - 2)
```

**Obergrenze:** Für `attempt_number > 27` (also jenseits von 'Z') ist das Ergebnis kein Buchstabe mehr (`chr(91) = '['`). In diesem Fall wird `f"#{attempt_number}"` als Fallback verwendet (z.B. `#28`). Dieser Fall ist in der Praxis ausgeschlossen, muss aber defensiv abgefangen werden.

```python
def attempt_type_for(attempt_number: int) -> str:
    if attempt_number == 1:
        return "Erstanalyse"
    n = attempt_number - 2
    if 0 <= n <= 25:
        return chr(ord('A') + n)
    return f"#{attempt_number}"
```

Diese Hilfsfunktion ersetzt überall im Code die bisherige Inline-Logik, inklusive `assign_buffer()`.

### Scope: Betroffene Routen

Beide Assignment-Routen müssen auf die neue Formel umgestellt werden:
- `admin_batch_assign_initial()` (initiale Zuweisung)
- `assign_buffer()` (Wiederholungszuweisung) — bisher cappt diese auf "D" via `types = ["A", "B", "C", "D"]`; dieser Code wird durch `attempt_type_for()` ersetzt.

### DB-Migration (Alembic)

**Schritt 1:** Spalte `sample_assignment.attempt_type` von `String(2)` auf `String(20)` erweitern (damit `"Erstanalyse"` passt):

```python
op.alter_column('sample_assignment', 'attempt_type',
    existing_type=sa.String(2), type_=sa.String(20))
```

**Schritt 2:** Werte aktualisieren — via reines SQL (SQLite unterstützt `CHAR()`):

```sql
UPDATE sample_assignment SET attempt_type = 'Erstanalyse' WHERE attempt_number = 1;
UPDATE sample_assignment SET attempt_type = CHAR(65 + attempt_number - 2)
    WHERE attempt_number >= 2 AND attempt_number <= 27;
```

Auch `models.py` anpassen: `attempt_type = db.Column(db.String(20), ...)`.

### UI

- `"Erstanalyse"` → grauer Badge (`badge-secondary` oder ähnlich)
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

**Die bestehende Idempotenz-Prüfung** (skip wenn bereits eine nicht-stornierte Zuweisung existiert) bleibt erhalten; die neue Einwage-Prüfung kommt zusätzlich dazu.

### Rückmeldung

Flash-Message mit Aufschlüsselung:
> „3 von 5 Proben zugewiesen (2 Proben noch nicht eingewogen)."

### UI: „Probe noch nicht bereit"

In der Zuweisungsübersicht (`assignments/overview.html`) müssen Studierende ohne gültige Zuweisung dargestellt werden. Da für diese Studierenden kein `SampleAssignment`-Objekt existiert, wird der Template-Kontext angepasst:

Die View-Funktion übergibt statt einer Liste von Assignments eine Liste von Dicts pro Studierenden:
```python
{
    "student": student,
    "assignment": assignment_or_None,  # None wenn Probe nicht bereit
    "sample_ready": bool
}
```

Das Template prüft `entry.assignment is None` und zeigt dann einen grauen "Probe noch nicht bereit"-Badge ohne Widerruf-Button.

---

## 3. Bug-Fix: Toleranzberechnung (Titrant Standardization)

### Problem

In `TitrantStandardizationMode.calculate_sample()` werden die Toleranzgrenzen als absolute Werte berechnet:

```python
titer_min = tol_min / 100   # z.B. 0.98 – fix, unabhängig vom Probenfaktor
titer_max = tol_max / 100   # z.B. 1.02
```

Dies ist falsch. `tol_min` (z.B. 98.0) bedeutet: "Untergrenze = 98% des wahren Wertes der Probe". Die Grenzen müssen relativ zum tatsächlichen `titer_expected` der Probe berechnet werden.

### Korrekte Formel

Analog zu `assay_mass_based` (`a_min = g_wahr * tol_min / 100`):

```python
titer_min = round(titer_expected * tol_min / 100.0, 4)
titer_max = round(titer_expected * tol_max / 100.0, 4)
```

**Beispiel:** titer_expected = 0.9400, tol_min = 98.0, tol_max = 102.0
- titer_min = 0.9400 × 0.98 = **0.9212**
- titer_max = 0.9400 × 1.02 = **0.9588**

**Keine Datenmigration nötig:** Die gespeicherten `tol_min`/`tol_max`-Werte sind korrekt (als %-des-Sollwerts); nur die Formel war falsch.

Die bestehende Toleranzquellen-Hierarchie (tolerance_override > g_ab > Substance-Default) bleibt unverändert.

### Betroffene Datei

Nur `calculation_modes.py`, Klasse `TitrantStandardizationMode`, Methode `calculate_sample()`. Die `assay_mass_based`-Berechnung ist korrekt und bleibt unverändert.

---

## 4. Neues Feature: Ergebnis-Widerruf

### Verhalten

Ein Admin kann ein eingereichtes, nicht-widerrufenes Ergebnis widerrufen:

1. `Result.revoked = True`, `Result.revoked_by` (Username), `Result.revoked_date` (`date.today().isoformat()`, Format `YYYY-MM-DD`) werden gesetzt
2. `SampleAssignment.status` kehrt zurück zu `"assigned"`
3. Der Student kann eine neue Ansage einreichen
4. Das widerrufene Ergebnis bleibt in der DB sichtbar (durchgestrichen, Datum + Widerrufer angezeigt)
5. Widerrufene Ergebnisse werden bei der Pass/Fail-Auswertung ignoriert

**Mehrfach-Widerruf:** Ein Student kann beliebig oft widerrufen und neu einreichen. Jedes Widerruf-Cycle erzeugt ein neues (dann ggf. ebenfalls widerrufenes) Result-Objekt. Alle bleiben in der DB.

### Aktives vs. widerrufenes Ergebnis

Das Konzept "aktives Ergebnis" wird eingeführt: das neueste `Result`-Objekt der Zuweisung mit `revoked = False`. Für die Darstellung und Auswertung gilt:

- `SampleAssignment.active_result` → neues Property: `next((r for r in sorted(self.results, key=lambda r: r.id, reverse=True) if not r.revoked), None)` — explizit nach `id` absteigend sortiert, da SQLAlchemy ohne `order_by` keine Reihenfolge garantiert. Die `results`-Relationship in `models.py` erhält zusätzlich `order_by="Result.id"`.
- `SampleAssignment.latest_result` (bestehend) bleibt für historische Anzeige erhalten

Die Ergebnisübersicht zeigt:
- Aktives Ergebnis (falls vorhanden) normal
- Widerrufene Ergebnisse darunter, durchgestrichen, mit Label „Widerrufen am [Datum] von [Benutzer]"

### Neues Datenmodell (Result)

```python
revoked       = Column(Boolean, default=False, nullable=False)
revoked_by    = Column(String(100), nullable=True)
revoked_date  = Column(String(20), nullable=True)
```

DB-Migration erforderlich.

### Route & UI

- Neue Route: `POST /results/<int:result_id>/revoke`
- Widerruf-Button in der Ergebnisübersicht neben jedem **aktiven** Ergebnis (nur Admins)
- Button muss CSRF-Token enthalten (entsprechend der bestehenden Konvention in `assignments/overview.html`)
- Widerrufene Ergebnisse haben keinen Widerruf-Button

---

## 5. Neues Feature: Live-Bewertung bei Ergebniseingabe

### Datenweitergabe Server → Browser

Beim Laden von `/results/submit/<id>` übergibt der Server die Bewertungsparameter als JSON-Block ins Template (via `data-`-Attribut oder eingebettetes `<script>`):

**Titrant Standardization:**
```json
{
  "true_value": 0.9400,
  "tol_min_pct": 98.0,
  "tol_max_pct": 102.0,
  "attempt_type": "Erstanalyse",
  "mode": "titrant_standardization"
}
```

**Assay Mass-Based:**
```json
{
  "true_value": 97.85,
  "tol_min_pct": 98.0,
  "tol_max_pct": 102.0,
  "attempt_type": "A",
  "mode": "assay_mass_based"
}
```

Falls `tol_min` oder `tol_max` `None` sind (Toleranzgrenzen nicht konfiguriert): der gesamte Live-Bewertungs-Block wird im Template nicht gerendert. Kein JS-Fehler, kein Badge.

### Bewertungslogik (JavaScript, plain – kein Framework)

Relative Abweichung vom wahren Wert:
```
δ = (eingabe − true_value) / true_value × 100
T_min = 100 − tol_min_pct      (z.B. 100 − 98.0 = 2.0)
T_max = tol_max_pct − 100      (z.B. 102.0 − 100 = 2.0)
```

Stufenzuordnung (asymmetrisch, da T_min ≠ T_max möglich):

| Symbol | Bedingung |
|--------|-----------|
| `f↑↑↑` | δ > 4 × T_max |
| `f↑↑` | 2 × T_max < δ ≤ 4 × T_max |
| `f↑` | T_max < δ ≤ 2 × T_max |
| `✓` | −T_min ≤ δ ≤ T_max |
| `f↓` | −2 × T_min ≤ δ < −T_min |
| `f↓↓` | −4 × T_min ≤ δ < −2 × T_min |
| `f↓↓↓` | δ < −4 × T_min |

Bei leerem oder ungültigem Eingabewert: kein Badge anzeigen.

### Konsequenz-Anzeige

Der nächste Analyse-Typ ergibt sich aus dem aktuellen `attempt_type`:

| attempt_type (aktuell) | Ergebnis falsch | Anzeige |
|------------------------|-----------------|---------|
| "Erstanalyse" | f↑/f↓/etc. | `f↑ → A` |
| "A" | f↑/f↓/etc. | `f↑ → B` |
| "B" | f↑/f↓/etc. | `f↑ → C` |
| beliebig | ✓ | `✓ bestanden` |

### evaluation_label: Server-seitige Berechnung

`evaluation_label` wird **server-seitig** in `results_submit()` berechnet — dieselbe Logik wie das JS, implementiert in Python. Kein verstecktes Formularfeld wird verwendet (nicht spoofbar). Das Label wird auf dem `Result`-Objekt gespeichert, bevor `db.session.commit()` aufgerufen wird.

Die Python-Implementierung verwendet **dieselbe δ-Formel** wie das JS:
```python
delta = (ansage_value - true_value) / true_value * 100
T_min = 100 - tol_min_pct
T_max = tol_max_pct - 100
```
und dieselben Stufen-Schwellen. Die absoluten `titer_min`/`titer_max`-Grenzen aus Abschnitt 3 werden für Pass/Fail verwendet — **nicht** für die Stufenzuordnung des Labels.

Falls `tol_min`/`tol_max` `None`: `evaluation_label = None`.

### Persistenz

Neues Feld `Result.evaluation_label` (String(20), nullable, z.B. `"f↑ → A"` oder `"✓"`), dauerhaft in der Ergebnisübersicht angezeigt.

DB-Migration erforderlich.

---

## Betroffene Dateien (Zusammenfassung)

| Datei | Änderungen |
|-------|------------|
| `models.py` | SampleAssignment: `attempt_type` String(2)→String(20), `active_result`-Property; Result: +`revoked`, `revoked_by`, `revoked_date`, `evaluation_label` |
| `calculation_modes.py` | TitrantStandardizationMode: Toleranzformel korrigiert; neue `attempt_type_for()`-Hilfsfunktion (alternativ in `models.py`) |
| `app.py` | `attempt_type_for()` verwenden in `assign_initial` + `assign_buffer`; Einwage-Filter in `assign_initial`; Widerruf-Route `POST /results/<id>/revoke`; Submit-Route: `evaluation_label` server-seitig berechnen + speichern; JSON-Ausgabe für Live-Bewertung |
| `templates/results/submit.html` | Live-Bewertungs-JS + Badge-Anzeige (nur wenn Toleranzgrenzen vorhanden) |
| `templates/results/overview.html` | Widerruf-Button (CSRF), `evaluation_label`, widerrufene Ergebnisse durchgestrichen |
| `templates/assignments/overview.html` | Erstanalyse-Badge (grau), „Probe noch nicht bereit"-Eintrag für Studierende ohne bereite Probe |
| `migrations/versions/XXXX_analyse_redesign.py` | `attempt_type` String(2)→String(20) + Wert-Update; neue Result-Spalten (`revoked`, `revoked_by`, `revoked_date`, `evaluation_label`) |
