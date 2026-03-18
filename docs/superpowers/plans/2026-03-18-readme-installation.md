# README & Installation Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pyproject.toml` and `.flaskenv`, then rewrite `README.md` to serve two audiences — Docker for lab staff, uv/pip for developers.

**Architecture:** Three files only. No Python source changes. `pyproject.toml` is the new canonical dependency list; `requirements.txt` stays for pip compatibility. `.flaskenv` makes `flask run` / `flask db upgrade` work without manual env var setup. README is rewritten in German around the two-path install model.

**Tech Stack:** TOML (pyproject.toml), Markdown (README.md), Flask CLI conventions (.flaskenv)

---

### Task 1: Infrastructure — `pyproject.toml` and `.flaskenv`

**Files:**
- Create: `pyproject.toml`
- Create: `.flaskenv`

> No unit tests for config files. Verification is manual: parse the TOML with Python's standard library, confirm `.flaskenv` is not gitignored.

- [ ] **Step 1: Create `pyproject.toml`**

  Create the file at the project root with this exact content:

  ```toml
  [project]
  name = "quanti-lims"
  version = "0.1.0"
  requires-python = ">=3.10"
  dependencies = [
      "flask>=3.0",
      "flask-sqlalchemy>=3.1",
      "flask-migrate>=4.0",
      "flask-wtf>=1.2",
      "wtforms>=3.1",
      "psycopg2-binary>=2.9",
  ]

  [project.optional-dependencies]
  dev = ["pytest", "pytest-cov"]

  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.build_meta"
  ```

- [ ] **Step 2: Verify `pyproject.toml` is valid TOML**

  Run:
  ```bash
  python -c "import tomllib; tomllib.loads(open('pyproject.toml', 'rb').read()); print('OK')"
  ```
  Expected output: `OK`

  (Note: `tomllib` is in the Python 3.11+ standard library. On Python 3.10, use `pip install tomli` first and `import tomli as tomllib`.)

- [ ] **Step 3: Create `.flaskenv`**

  Create the file at the project root with this exact content (no blank lines, no comments):

  ```
  FLASK_APP=app
  ```

- [ ] **Step 4: Verify `.flaskenv` is not gitignored**

  Run:
  ```bash
  git check-ignore -v .flaskenv
  ```
  Expected: no output (meaning the file is NOT ignored — this is correct, `.flaskenv` should be tracked).

  Also confirm `.env` IS ignored:
  ```bash
  git check-ignore -v .env
  ```
  Expected output: `.gitignore:6:.env    .env`

- [ ] **Step 5: Stage and commit**

  ```bash
  git add pyproject.toml .flaskenv
  git commit -m "chore: add pyproject.toml and .flaskenv for uv compatibility"
  ```

---

### Task 2: Rewrite `README.md`

**Files:**
- Modify: `README.md`

The existing README.md has outdated project structure, missing Docker docs, a broken quick start (missing `flask db upgrade`), and no uv instructions. Replace it entirely with the content below.

- [ ] **Step 1: Write the new README.md**

  Replace the entire content of `README.md` with:

  ````markdown
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

  ### Tests ausführen

  ```bash
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
  - **Tagesansicht**: Auflösung von Rotations- und Extra-Assignments pro Student und Praktikumstag
  - **Praktikumskalender**: Verwaltung von Blocktagen und Nachkochtagen
  - **Berichte**: Fortschritts-Heatmap, Reagenzienbedarf
  - **Admin-Interface**: CRUD für alle Stammdaten (Substanzen, Chargen, Methoden, Reagenzien, BOM, Semester, Studierende)

  ---

  ## Tech-Stack

  | Schicht | Technologie |
  |---|---|
  | Backend | Python 3.10+ / Flask 3 |
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
  ├── calculation_modes.py # Berechnungslogik (assay_mass_based, titrant_standardization)
  ├── init_db.py           # Referenz-Seed (wird automatisch aufgerufen)
  ├── config.py            # Konfiguration (DATABASE_URL, SECRET_KEY)
  ├── pyproject.toml       # Projektmetadaten + Abhängigkeiten
  ├── requirements.txt     # Legacy pip-kompatible Abhängigkeitsliste
  ├── .flaskenv            # FLASK_APP=app (Flask CLI-Konfiguration)
  ├── .env.example         # Vorlage für lokale Umgebungsvariablen
  ├── Dockerfile
  ├── docker-compose.yml   # PostgreSQL + Web (Produktion)
  ├── migrations/          # Alembic-Migrationen
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
  ````

- [ ] **Step 2: Verify README content against spec checklist**

  Confirm each section exists in the written file:
  - [ ] Docker Schnellstart mit `docker compose up --build`
  - [ ] `flask db upgrade` Pflichthinweis vorhanden
  - [ ] uv-Installationspfad vorhanden
  - [ ] pip-Installationspfad vorhanden (mit venv-Aktivierung für Windows + Unix)
  - [ ] Konfigurationstabelle: DATABASE_URL, SECRET_KEY, ADMIN_BACKUP_TOKEN
  - [ ] `.env.example` erwähnt mit `cp`-Befehl
  - [ ] Datenbank-Optionen-Tabelle (SQLite vs. PostgreSQL)
  - [ ] Projektstruktur enthält `praktikum.py`, `.flaskenv`, `.env.example`, `errors/`
  - [ ] Tech-Stack-Tabelle mit pytest und Docker
  - [ ] Features-Liste enthält Tagesansicht + Praktikumskalender

- [ ] **Step 3: Run tests to confirm nothing broken**

  ```bash
  pytest --tb=short -q
  ```
  Expected: all tests pass (README changes cannot break tests, but verify anyway).

- [ ] **Step 4: Commit**

  ```bash
  git add README.md
  git commit -m "docs: rewrite README with Docker/uv install paths and updated project structure"
  ```

---
