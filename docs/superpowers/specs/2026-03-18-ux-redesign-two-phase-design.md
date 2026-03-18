# Quanti-LIMS: UX-Redesign & Technische Modernisierung

**Datum:** 2026-03-18
**Status:** Genehmigt

---

## Kontext

Quanti-LIMS ist ein webbasiertes LIMS (Laboratory Information Management System) für pharmazeutisch-chemische Praktika an Hochschulen. Es wird von Lehrenden/Assistenten zur Vorbereitung und Durchführung von Semesterpraktika genutzt. Studierende nutzen die App **nicht** direkt.

**Aktuelle Schwachstellen:**
- Die Navigation spiegelt die natürliche Arbeitsstruktur (Vorbereitung vs. laufendes Semester) nicht wider
- Vorbereitungs- und Praktikumsfunktionen sind nicht klar getrennt
- Die UI wirkt "altbacken" und nicht intuitiv
- Manuelle Datenbankmigration (`migrate_schema()`) ist 200+ Zeilen fragiler PRAGMA-SQL
- SQLite ist nicht optimal für gleichzeitige Schreibzugriffe mehrerer Assistenten

---

## Zielgruppen & Nutzungsmuster

- **Technische Assistenz (TA):** Nutzt die App hauptsächlich in der Semestervorbereitung (Stammdaten, Semesterplanung, Probenvorbereitung). Meist allein, kein Zeitdruck.
- **Assistenten (während Praktikum):** 2–5 Personen gleichzeitig, unter Zeitdruck. Brauchen schnelle, übersichtliche Oberfläche für Ansagen und Statusverfolgung.
- **Studierende:** Nutzen die App **nicht**. Kommen physisch zur Assistenz und melden ihre Ergebnisse mündlich.

---

## Kernentscheidung: Zwei-Phasen-Navigation

Die App wird in zwei klar getrennte Hauptbereiche gegliedert, die sofort auf der Startseite sichtbar sind:

1. **Vorbereitung** — alles was vor und zwischen den Semestern passiert
2. **Praktikum** — alles was während der aktiven Praktikumstage passiert

---

## Bereich 1: Vorbereitung

### 1.1 Stammdaten *(einmalig, selten geändert)*

Semester-übergreifende Referenzdaten:

- **Substanzen**: Name, Formel, Molmasse, Arzneibuch-Einwaage, Toleranzgrenzen — inklusive zugehöriger **Substanz-Chargen** (Lot-Nummer, Lieferant, CoA-Gehalt vom Etikett)
- **Reagenzien**: Katalog aller verwendeten Reagenzien mit BOM (Bill of Materials) für Mischreagenzien
- **Blöcke & Analysen**: Blockstruktur (I, II, III), Analysenkonfiguration, Berechnungsmodi
- **Methoden**: Titrationsparameter, Primärstandards, Reagenzienliste pro Methode

> **Hinweis Titer:** Es gibt keine "Titer-Einstellung" als TA-Aufgabe. Die Titrant-Standardisierung (z.B. Salzsäure) ist selbst eine Analyse, die Studierende als erste Analyse durchführen. TAs erfassen lediglich den CoA-Gehalt einer Substanz-Charge (Aufdruck auf dem Etikett) — nicht mehr. Die bestehende automatische Titer-Übernahme von einem Standardisierungs-Ergebnis in `SampleBatch.titer` (via `titer_source = "standardization_result"`) bleibt unverändert erhalten und ist nicht Teil dieses Redesigns.

### 1.2 Semesterplanung *(einmal pro Semester)*

- **Semester**: anlegen, benennen, Zeitraum festlegen
- **Studierende**: erfassen, **Gruppen A/B/C/D** zuweisen
- **Praktikumskalender**:
  - Praktikumstage definieren (Datum, Block, Blocktag 1–4 oder Nachkochtag)
  - Startrotation festlegen: welche Gruppe beginnt mit welcher Analyse
  - Rotation ist standardmäßig automatisch (Gruppe rückt täglich eine Analyse weiter), aber **manuell überschreibbar** pro Tag/Gruppe
  - Pro Block gibt es genau **einen Nachkochtag** im Anschluss an die 4 normalen Blocktage
- **Dienste**: Saaldienst und Entsorgungsdienst pro Praktikumstag festlegen (2–4 Studierende je Dienst), manuell oder automatisch generiert

### 1.3 Probenvorbereitung *(kurz vor Praktikum)*

- **Probensätze** anlegen: Verknüpfung Semester + Analyse + Substanz-Charge, Einwaageziele, Gesamtzahl Proben
- **Proben einwiegen**: tatsächliche Einwaagen erfassen (m_S, m_ges)

---

## Bereich 2: Praktikum

Fokussierte Oberfläche für den Einsatz während der Praktikumstage. Kein Navigieren durch Untermenüs.

### 2.1 Tagesansicht (Startseite des Praktikumsbereichs)

Sofort sichtbar beim Öffnen:

- Heutiges Datum, welcher Block und Blocktag (z.B. "Block II – Tag 3" oder "Block I – Nachkochtag")
- **Rotationsübersicht**: welche Gruppe (A/B/C/D) macht heute welche Analyse
- **Saaldienst & Entsorgungsdienst** für heute
- **Studentenstatus-Übersicht**: alle Studierenden farblich codiert
  - Zugewiesen (wartet auf Analyse)
  - Ansage ausstehend
  - Bestanden, Protokoll noch offen
  - Bestanden, Protokoll abgehakt
  - Wiederholung erforderlich (mit Wiederholungstyp: A, B, C…)
  - Nachkochtag: welche Studierenden müssen was nachholen

### 2.2 Ansage eintragen

- Klick auf Studierenden → Eingabefeld für Ansagewert → sofortige Auswertung
- Anzeige: bestanden / nicht bestanden, Fehlerrichtung (f↑, f↓, f↑↑ …), Erwartungswert
- Keine manuelle Navigation zu Batches, Samples oder Assignments nötig — das läuft im Hintergrund
- **Auflösungslogik** (welcher `SampleBatch` → welches `Sample` → welches `SampleAssignment` für diesen Studierenden heute): wird in einer separaten Folge-Spec spezifiziert, insbesondere für Nachkochtage und Wiederholungsversuche

### 2.3 Nach bestandener Analyse

- **Protokoll abhaken**: ein Klick, mit Datum und Assistenz-Kürzel
- Zuweisung zur nächsten Analyse erfolgt automatisch per Rotationslogik, manuell überschreibbar
- Regeln für die nächste Analyse (z.B. Protokoll muss abgehakt sein) werden später spezifiziert

### 2.4 Nachkochtag-Ansicht

- Zeigt welche Studierenden noch Analysen aus dem Block nachholen müssen
- Gleiche Oberfläche wie normaler Tag, aber ohne Rotationslogik

---

## Druckansichten (spätere Erweiterung)

Druckoptimierte HTML-Seiten (keine Word-Templates), aufrufbar per "Drucken"-Button oder `Strg+P`. Geplante Kandidaten:

- Tagesplan mit Rotationsübersicht
- Saaldienstliste
- Probensatz-Übersicht (für Einwaagetag)
- Studentenstatus pro Block

Diese Ansichten werden schrittweise ergänzt — die saubere Struktur dafür wird von Anfang an angelegt.

---

## Technische Änderungen (nicht sichtbar für Nutzer)

### SQLite → PostgreSQL

- **Grund**: Mehrere Assistenten schreiben gleichzeitig während des Praktikums — SQLite-Locking ist dann problematisch
- **Aufwand**: Gering — `config.py` unterstützt bereits `DATABASE_URL`. Die ORM-Modelle bleiben identisch
- **Deployment**: PostgreSQL läuft in einem Docker-Container (`docker-compose.yml`, ~10 Zeilen)

### Alembic für Datenbankmigrationen

- **Ersetzt**: die manuelle `migrate_schema()`-Funktion (~200 Zeilen SQLite-spezifischer PRAGMA-SQL)
- **Vorteil**: Bei Modelländerung einfach `flask db migrate` ausführen — Migrationsdatei wird automatisch generiert
- **Aufwand**: Einmalige Einrichtung

---

## Neue Datenmodell-Konzepte

Folgende Konzepte existieren noch nicht im aktuellen Modell und müssen ergänzt werden:

| Konzept | Beschreibung |
|---|---|
| `PracticalDay` | Ein definierter Praktikumstag mit `semester_id` (FK), Datum, Block-Referenz, Tagestyp (normal/Nachkochtag) |
| `GroupRotation` | Zuordnung Gruppe (String-Enum `A/B/C/D`) → Analyse pro `PracticalDay`; auto-generiert, manuell überschreibbar |
| `group_code` auf `Student` | Einfaches String-Attribut `A`/`B`/`C`/`D` auf dem bestehenden `Student`-Modell — keine separate Group-Tabelle nötig. Spalte ist `nullable=True` (bestehende Studierenden-Zeilen bleiben gültig). Pflichtfeld in der Semesterplanung-UI, bevor der Praktikumsmodus zugänglich ist. Alembic-Migration: `ALTER TABLE student ADD COLUMN group_code VARCHAR(1)` ohne Backfill. |
| `DutyAssignment` | Felder: `practical_day_id` (FK → `PracticalDay.id`), `student_id` (FK → `Student.id`), `duty_type` (String-Enum: `Saaldienst`/`Entsorgungsdienst`) |
| `ProtocolCheck` | Felder: `sample_assignment_id` (FK → `SampleAssignment.id`, **UNIQUE** — ein Eintrag pro Analyseversuch), `checked_date`, `checked_by` (Assistenz-Kürzel). Ergänzt (ersetzt nicht) den `SampleAssignment.status`-Wert `"passed"` — eine Analyse kann bestanden sein, bevor das Protokoll abgehakt ist. |

---

## Bewusst ausgeklammert (für spätere Iteration)

- Genaue Regeln für "darf nächste Analyse beginnen" (z.B. Protokoll muss abgehakt sein)
- Details der automatischen Dienst-Zuweisung (z.B. Fairness-Algorithmus)
- Umfang und Format der Druckansichten
- Authentifizierung / Rollentrennung (TA vs. Assistent)
