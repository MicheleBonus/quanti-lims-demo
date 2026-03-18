# Design: Plan 4 – Auflösungslogik Tagesansicht

**Datum:** 2026-03-18
**Status:** Approved

---

## Überblick

Plan 4 implementiert die Tagesansicht (`/praktikum/`) mit der zentralen Auflösungslogik: gegeben ein ausgewählter `PracticalDay` und ein aktives Semester, wird für jeden Studierenden bestimmt, welche `SampleAssignment`-Einträge heute relevant sind.

---

## 1. Architektur

Die Auflösungslogik lebt in einem neuen Service-Modul `praktikum.py` — nicht in `app.py` und nicht in `models.py`. Die Route bleibt dünn (~10 Zeilen). Das Modul ist direkt testbar ohne HTTP-Layer.

---

## 2. Datenstruktur: `StudentSlot`

```python
@dataclass
class StudentSlot:
    student: Student
    rotation_analysis: Analysis | None
    rotation_assignment: SampleAssignment | None
    extra_assignments: list[SampleAssignment]
```

| Feld | Bedeutung |
|---|---|
| `rotation_analysis` | Heutige Rotations-Analyse für diese Gruppe (None auf Nachkochtag) |
| `rotation_assignment` | Das SampleAssignment für die Rotations-Analyse (None = noch nicht zugewiesen oder Nachkochtag) |
| `extra_assignments` | Alle anderen offenen Assignments (Wiederholungen, andere Blöcke); auf Nachkochtag: alle offenen Block-Assignments |

Das Template arbeitet ausschließlich mit `StudentSlot`-Objekten.

---

## 3. Auflösungslogik

### Zentrale Funktion

```python
def resolve_student_slots(practical_day, semester) -> list[StudentSlot]:
    students = Student.query.filter_by(semester_id=semester.id)\
                            .order_by(Student.running_number).all()
    if practical_day.day_type == "nachkochtag":
        return _resolve_nachkochtag(practical_day, semester, students)
    return _resolve_normal_day(practical_day, semester, students)
```

### Normaltag (`_resolve_normal_day`)

**Schritt 1:** `GroupRotation`s für diesen Tag als Dict `{group_code → rotation}` vorladen.

**Schritt 2:** Alle offenen `SampleAssignment`s für dieses Semester in einem Query laden (status not in `["passed", "cancelled"]`), gruppiert als `{student_id → [assignments]}`.

**Schritt 3:** Alle `SampleBatch`-Einträge für dieses Semester als Dict `{analysis_id → batch}` vorladen. Alle `Sample`-Einträge für diese Batches als Dict `{(batch_id, running_number) → sample}` vorladen. Damit werden O(n_students) Einzel-Queries für Batch- und Sample-Lookup vermieden.

**Schritt 4:** Pro Student:
1. `student.group_code` → `GroupRotation` → `analysis`
2. `batch = batches_by_analysis[analysis.id]` (aus Vorladung Schritt 3)
3. `sample = samples_by_key[(batch.id, student.running_number)]` (aus Vorladung Schritt 3, `is_buffer = False`)
4. `rotation_assignment`: das Assignment aus Schritt 2, das zu diesem Sample gehört (`sample_id` stimmt überein) — oder `None` wenn kein solches Assignment existiert
5. `extra_assignments`: alle anderen offenen Assignments dieses Studierenden — **explizit exkludiert: das in Schritt 4 gefundene `rotation_assignment`** (Ausschluss per `assignment.id != rotation_assignment.id`)

Alle Studierenden des Semesters erscheinen in der Ausgabe (auch wenn `rotation_assignment = None`).

### Nachkochtag (`_resolve_nachkochtag`)

**Scope:** Nur Assignments deren `batch.analysis.block_id = practical_day.block_id`.

**Schritt 1:** Alle offenen Assignments des Semesters laden, gefiltert auf `analysis.block_id = practical_day.block_id`.

**Schritt 2:** Pro Student einen Slot erzeugen — `rotation_analysis = None`, `rotation_assignment = None`. `extra_assignments` enthält alle offenen Block-Assignments (kann leer sein).

**Alle Studierenden werden angezeigt**, auch jene ohne offene Assignments. Leere `extra_assignments` = Student hat den Block abgeschlossen → Template zeigt ausgegraut / „Block abgeschlossen"-Badge.

---

## 4. Edge Cases

| Situation | Verhalten |
|---|---|
| Student hat kein `group_code` | `rotation_analysis = None`, `rotation_assignment = None` |
| Kein `GroupRotation` für diese Gruppe heute | wie oben |
| `SampleBatch` für diese Analyse fehlt | `rotation_assignment = None` |
| `Sample` mit passender `running_number` fehlt | `rotation_assignment = None` |
| `assign_initial` noch nicht gelaufen | `rotation_assignment = None` (Badge: „Noch nicht zugewiesen") |
| `assign_initial` gelaufen, aber Sample war beim Aufruf nicht eingewogen | `rotation_assignment = None` (Badge: „Noch nicht zugewiesen") — visuell identisch; Ursache liegt in der Einwaagelage |
| Normaltag, Student hat keine offenen Extra-Assignments | `extra_assignments = []`, Slot trotzdem angezeigt |
| Nachkochtag, Student hat keine offenen Block-Assignments | Slot angezeigt, ausgegraut, Badge „Block abgeschlossen" |

---

## 5. Route

```python
@app.route("/praktikum/")
def praktikum_tagesansicht():
    date_str = request.args.get("date") or date.today().isoformat()
    semester = Semester.query.filter_by(is_active=True).first()
    practical_day = (
        PracticalDay.query.filter_by(semester_id=semester.id, date=date_str).first()
        if semester else None
    )
    slots = resolve_student_slots(practical_day, semester) if practical_day else []
    return render_template(
        "praktikum/tagesansicht.html",
        practical_day=practical_day,
        semester=semester,
        slots=slots,
        selected_date=date_str,
    )
```

Bei fehlendem Semester oder kein `PracticalDay` für das gewählte Datum: leere `slots`-Liste, Template zeigt Info-Banner.

---

## 6. Template-Grobstruktur

`templates/praktikum/tagesansicht.html`:

- **Header:** Datepicker (Default = heute), Block + Tagestyp, Rotationsübersicht (welche Gruppe → welche Analyse)
- **Info-Banner** wenn kein Semester aktiv oder kein PracticalDay für gewähltes Datum
- **Studierendentabelle:** Eine Zeile pro `StudentSlot`
  - `rotation_assignment` vorhanden → Badge mit Analyse + `attempt_type`
  - `rotation_assignment = None` → grauer Badge „Noch nicht zugewiesen"
  - `extra_assignments` → je ein Badge pro Assignment (Analyse + `attempt_type`)
  - Nachkochtag, `extra_assignments` leer → Zeile ausgegraut, Badge „Block abgeschlossen"

**Status-Farben** — abgeleitet aus Modellfeldern, kein eigenes `status`-Feld:

| UI-Zustand | Bedingung (aus Modell) | Farbe |
|---|---|---|
| Zugewiesen | `assignment.status == "assigned"` und `assignment.active_result is None` | blau |
| Ansage ausstehend | `assignment.status == "assigned"` und `assignment.active_result is not None` und `active_result.passed is None` | gelb |
| Bestanden | `assignment.status == "passed"` | grün |
| Wiederholung fällig | `assignment` ist ein Erstanalyse-Assignment (`attempt_number == 1`) mit `active_result.passed == False` und ein Wiederholungs-Assignment existiert noch nicht | orange |

---

## 7. Testing

`tests/test_praktikum_resolution.py` testet `praktikum.py` direkt:

- Normaltag: Student mit Rotation-Assignment
- Normaltag: Student ohne `group_code` → `rotation_assignment = None`
- Normaltag: `assign_initial` nicht gelaufen → `rotation_assignment = None`
- Normaltag: Student mit offenem Extra-Assignment (Wiederholung)
- Nachkochtag: Student mit offenen Block-Assignments → erscheint in Slots
- Nachkochtag: Student ohne offene Block-Assignments → erscheint ausgegraut
- Nachkochtag: Student mit mehreren offenen Block-Assignments

---

## 8. Betroffene Dateien

| Datei | Änderung |
|---|---|
| `praktikum.py` | Neu: `StudentSlot`, `resolve_student_slots`, `_resolve_normal_day`, `_resolve_nachkochtag` |
| `app.py` | Route `praktikum_tagesansicht` ersetzen (Placeholder → echte Logik) |
| `templates/praktikum/tagesansicht.html` | Placeholder ersetzen durch vollständige Tagesansicht |
| `tests/test_praktikum_resolution.py` | Neu: Unit-Tests für Service-Modul |
