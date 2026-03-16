# Quanti-LIMS

**Laboratory Information Management System** für das Praktikum  
*„Quantitative Analytik von Arznei-, Hilfs- und Schadstoffen"*

Institut für Pharmazeutische und Medizinische Chemie, HHU Düsseldorf

## Features

- **Referenzdatenbank**: Substanzen, Chargen (CoA + analytische Reinheit), Analysen (I.1–III.4), Methoden, Reagenzien mit hierarchischer Stückliste (BOM)
- **Probenverwaltung**: Automatische Generierung von Erst- und Pufferproben, dynamische Zuweisung
- **Einwaage-Eingabe**: Tabellarische TA-Eingabemaske mit Live-Berechnung von G_wahr, A_min/A_max, V_erwartet
- **Ergebnisbewertung**: Automatischer Abgleich der Ansage mit Toleranzgrenzen (AB oder 98–102 % Override)
- **Wiederholungsanalysen**: Dynamische Pufferproben-Zuweisung per Klick
- **Berichte**: Fortschritts-Heatmap, Reagenzienbedarf
- **Admin-Interface**: CRUD für alle Stammdaten (Substanzen, Chargen, Methoden, Reagenzien, BOM, Semester, Studierende)

## Schnellstart

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# Starten (DB wird automatisch erstellt + mit Demo-Daten befüllt)
python app.py

# Öffne http://localhost:5000
```

## Tech-Stack

| Schicht | Technologie |
|---------|-------------|
| Backend | Python 3.10+ / Flask |
| ORM | SQLAlchemy |
| Datenbank | SQLite (single file) |
| Frontend | Jinja2 + Bootstrap 5 |
| Icons | Bootstrap Icons |

## Projektstruktur

```
quanti-lims/
├── app.py              # Flask App + alle Routes
├── models.py           # SQLAlchemy ORM-Modelle
├── init_db.py          # Datenbank-Seed (Referenz- + Demo-Daten)
├── config.py           # Konfiguration
├── requirements.txt
├── static/
│   └── style.css       # Custom CSS
└── templates/
    ├── base.html       # Base-Layout + Navigation
    ├── macros.html     # Wiederverwendbare Form-Macros
    ├── dashboard.html
    ├── admin/          # Admin-CRUD (Substanzen, Chargen, Analysen, ...)
    ├── ta/             # TA-Workflows (Einwaage)
    ├── assignments/    # Zuweisungen + Wiederholungen
    ├── results/        # Ansage-Eingabe + Bewertung
    └── reports/        # Fortschritt, Reagenzienbedarf
```

## Business Logic

Die Berechnungen erfolgen modus-spezifisch über `calculation_modes.py` und werden über `Analysis.calculation_mode` ausgewählt:

- **Reinheits-Hierarchie**: `SubstanceLot.p_effective` → analytisch > CoA > 100 %
- **assay_mass_based**: `Sample.g_wahr`, `a_min/a_max`, `v_expected` aus Einwaage- und Methodenparametern.
- **titrant_standardization**: `Sample.v_expected` und `titer_expected`; Bewertung über berechneten `titer_result` gegen Titer-Grenzen.
- **Bewertung**: `Result.evaluate()` delegiert an den jeweiligen Mode-Evaluator und persistiert mode-spezifische Referenzwerte.


## Wo liegen die Daten / wie sichern?

- Standardmäßig nutzt die App SQLite mit der Datei `quanti_lims.db` im Projektverzeichnis (`Config.SQLALCHEMY_DATABASE_URI` in `config.py`).
- Den aktuell aktiven DB-URI/Pfad zeigt die Admin-Seite **System** als read-only Hinweis an.
- Zentrale Tabellen lassen sich als CSV/JSON exportieren:
  - Semester
  - Studierende
  - Ergebnisse
  - Reagenzienbedarf
- Optional kann ein DB-Backup (Download der SQLite-Datei) über `/admin/backup/database` erfolgen.
  - Zugriff nur mit Admin-Rolle vorgesehen (Session-Flag oder optionaler `ADMIN_BACKUP_TOKEN` via URL-Parameter `?token=...`).

Empfehlung: Regelmäßig DB-Datei sichern und zusätzlich fachliche Exporte (CSV/JSON) versioniert ablegen.

## Lizenz

Intern – AG Gohlke / CPCLab, HHU Düsseldorf
