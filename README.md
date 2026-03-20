# Quanti-LIMS

**Laboratory Information Management System** für das Praktikum
*„Quantitative Analytik von Arznei-, Hilfs- und Schadstoffen"*

Institut für Pharmazeutische und Medizinische Chemie, HHU Düsseldorf

---

## Schnellstart — Docker (empfohlen für Lab-Betrieb)

**Voraussetzung:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installiert.

```bash
docker compose up --build
```

Öffne anschließend [http://localhost:5000](http://localhost:5000).

> Die Datenbank (PostgreSQL) wird automatisch gestartet und mit Referenzdaten befüllt.
> Daten bleiben im Docker-Volume `pgdata` erhalten, auch nach `docker compose down`.

---

## Lokale Entwicklung

### Option A — uv (empfohlen)

```bash
pip install uv          # einmalig — uv global installieren
uv sync                 # legt .venv an, installiert alle Abhängigkeiten
flask db upgrade        # erstellt Datenbanktabellen (Alembic-Migrationen)
flask run               # startet App auf http://localhost:5000
```

### Option B — pip

```bash
python -m venv .venv
# Windows:    .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
flask db upgrade
flask run
```

> **Wichtig:** `flask db upgrade` muss **beim ersten Start** und nach jedem `git pull` mit neuen Migrationen ausgeführt werden. Ohne diesen Schritt startet die App mit leerem Datenbankschema.
>
> `FLASK_APP` muss nicht manuell gesetzt werden — die mitgelieferte `.flaskenv` erledigt das automatisch.
>
> Zusätzliche Spalten-Migrationen (`migrations/legacy_sql/`) werden beim **App-Start automatisch** angewendet — kein manueller Schritt erforderlich.

### Tests ausführen

```bash
# uv:
uv sync --extra dev   # einmalig — installiert pytest und pytest-cov
pytest

# pip:
pip install pytest pytest-cov
pytest
```

---

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `DATABASE_URL` | `sqlite:///quanti_lims.db` | DB-Verbindung (SQLite lokal oder PostgreSQL) |
| `SECRET_KEY` | Auto-generiert, in `.secret_key` gespeichert | Flask Session-Schlüssel |
| `ADMIN_BACKUP_TOKEN` | — | Optionaler Token für die DB-Backup-Route |

Für Produktion `SECRET_KEY` explizit als Umgebungsvariable setzen.

Das Repo enthält `.env.example` mit allen drei Variablen als Vorlage. Für lokale PostgreSQL-Entwicklung:

```bash
cp .env.example .env   # .env mit echten Werten befüllen
```

`.env` ist gitignored und wird nicht eingecheckt.

### Datenbank-Optionen

| Modus | Verwendung | Setup |
|---|---|---|
| SQLite (Standard) | Lokale Entwicklung | Automatisch — Datei `quanti_lims.db` im Projektverzeichnis |
| PostgreSQL | Produktion / Docker | `DATABASE_URL=postgresql://...` setzen; `docker compose up` konfiguriert das automatisch |

---

## Features

- **Referenzdatenbank**: Substanzen, Chargen (CoA + analytische Reinheit), Analysen (I.1–III.4), Methoden, Reagenzien mit hierarchischer Stückliste (BOM)
- **Probenverwaltung**: Automatische Generierung von Erst- und Wiederholungsproben, dynamische Zuweisung
- **Einwaage-Eingabe**: Tabellarische TA-Eingabemaske mit Live-Berechnung von G_wahr, A_min/A_max, V_erwartet
- **Ergebnisbewertung**: Automatischer Abgleich der Ansage mit Toleranzgrenzen (AB oder 98–102 % Override)
- **Drei Berechnungsmodi**: Gehaltsbestimmung (`assay_mass_based`), Titerstandardisierung (`titrant_standardization`), reine Massenbestimmung (`mass_determination`, z. B. Glycerol)
- **Tagesansicht**: Auflösung von Rotations- und Extra-Assignments pro Student und Praktikumstag
- **Praktikumskalender**: Verwaltung von Blocktagen und Nachkochtagen
- **Reagenzienbedarf**: Übersicht mit aufklappbaren Zusammensetzungen, konfigurierbarem Sicherheitsfaktor (pro Batch), Grundbedarf auf Erstanalysen-Basis (k=1); druckbare Bestellliste (Grundsubstanzen aggregiert) und Herstellliste pro Block
- **Berichte**: Fortschritts-Heatmap, Reagenzienbedarf, CSV/JSON-Export
- **Admin-Interface**: CRUD für alle Stammdaten (Substanzen, Chargen, Methoden, Reagenzien, BOM, Semester, Studierende)

---

## Tech-Stack

| Schicht | Technologie |
|---|---|
| Backend | Python 3.12+ / Flask 3 |
| ORM + Migrationen | SQLAlchemy + Flask-Migrate (Alembic) |
| Datenbank | SQLite (Entwicklung) / PostgreSQL 16 (Produktion) |
| Frontend | Jinja2 + Bootstrap 5.3 + Bootstrap Icons |
| Tests | pytest |
| Container | Docker + Docker Compose |

---

## Projektstruktur

```
quanti-lims/
├── app.py               # Flask App-Factory + alle Routes
├── models.py            # SQLAlchemy ORM-Modelle
├── praktikum.py         # Service-Modul: Auflösungslogik Tagesansicht
├── calculation_modes.py # Berechnungslogik (assay_mass_based, titrant_standardization, mass_determination)
├── init_db.py           # Referenz-Seed (wird automatisch aufgerufen)
├── config.py            # Konfiguration (DATABASE_URL, SECRET_KEY)
├── pyproject.toml       # Projektmetadaten + Abhängigkeiten
├── requirements.txt     # Legacy pip-kompatible Abhängigkeitsliste
├── .flaskenv            # FLASK_APP=app (Flask CLI-Konfiguration)
├── .env.example         # Vorlage für lokale Umgebungsvariablen
├── Dockerfile
├── docker-compose.yml   # PostgreSQL + Web (Produktion)
├── migrations/          # Alembic-Migrationen + legacy_sql/ (werden beim Start automatisch angewendet)
├── tests/               # pytest-Testsuite
├── static/
└── templates/
    ├── base.html
    ├── home.html
    ├── macros.html
    ├── admin/           # CRUD: Substanzen, Chargen, Analysen, Studierende, Kalender …
    ├── praktikum/       # Tagesansicht
    ├── ta/              # Einwaage-Workflow
    ├── assignments/     # Zuweisungen + Wiederholungen
    ├── results/         # Ansage-Eingabe + Bewertung
    ├── reports/         # Fortschritt, Reagenzienbedarf
    └── errors/          # 404, 500
```

---

## Business Logic

Die Berechnungen erfolgen modus-spezifisch über `calculation_modes.py` und werden über `Analysis.calculation_mode` ausgewählt:

- **Reinheits-Hierarchie**: `SubstanceLot.p_effective` → analytisch > CoA > 100 %
- **assay_mass_based**: `Sample.g_wahr`, `a_min/a_max`, `v_expected` aus Einwaage- und Methodenparametern
- **titrant_standardization**: `Sample.v_expected` und `titer_expected`; Bewertung über berechneten `titer_result` gegen Titer-Grenzen
- **mass_determination**: TA wiegt reine Substanz ein (`m_s_actual_g`); Student sagt Masse in mg an; Toleranz relativ zur Einwaage (g_ab_min/max_pct); Einwaagebereich aus `Analysis.m_einwaage_min/max_mg`; Aliquotierung wird unterstützt
- **Bewertung**: `Result.evaluate()` delegiert an den jeweiligen Mode-Evaluator und persistiert mode-spezifische Referenzwerte

---

## Wo liegen die Daten / wie sichern?

- SQLite: Datei `quanti_lims.db` im Projektverzeichnis (`DATABASE_URL` in `config.py`).
- PostgreSQL (Docker): Daten im Volume `pgdata`; sichern mit `docker compose exec db pg_dump ...`
- Den aktuell aktiven DB-URI zeigt die Admin-Seite **System** als read-only Hinweis an.
- Fachliche Exporte (CSV/JSON) über die Admin-Seite: Semester, Studierende, Ergebnisse, Reagenzienbedarf.
- DB-Backup (Download der SQLite-Datei) via `/admin/backup/database` (optionaler `ADMIN_BACKUP_TOKEN`).

Empfehlung: Regelmäßig DB-Datei sichern und zusätzlich fachliche Exporte versioniert ablegen.

---

## Lizenz

Intern – AG Gohlke / CPCLab, HHU Düsseldorf
