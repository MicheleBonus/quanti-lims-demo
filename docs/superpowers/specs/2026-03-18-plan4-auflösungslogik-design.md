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

**Schritt 2:** Alle offenen `SampleAssignment`s für dieses Semester in einem Query laden (status not in `["passed", "cancelled"]`), gruppiert als `{student_id → [assignments]}`. Vermeidet N+1-Queries.

**Schritt 3:** Pro Student:
1. `student.group_code` → `GroupRotation` → `analysis`
2. `SampleBatch` für `(semester.id, analysis.id)` (UniqueConstraint, max. 1 Treffer)
3. `Sample` mit `running_number = student.running_number` und `is_buffer = False`
4. `rotation_assignment`: das Assignment aus Schritt 2, das zu diesem Sample gehört (`sample_id` stimmt überein) — oder `None` wenn `assign_initial` noch nicht gelaufen
5. `extra_assignments`: alle anderen offenen Assignments dieses Studierenden (Wiederholungen aus früheren Tagen, offene Analysen anderer Blöcke)

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
        PracticalDay.query.filter_by(date=date_str).first()
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

Status-Farben: zugewiesen (blau), Ansage ausstehend (gelb), bestanden (grün), Wiederholung fällig (orange).

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
