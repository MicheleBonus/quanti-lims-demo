# Design: README & Installation Setup

**Datum:** 2026-03-18
**Status:** Approved

---

## Überblick

Das README und die Installationsinfrastruktur werden überarbeitet, um zwei Zielgruppen klar zu bedienen:

1. **Lab-Mitarbeiter / TA-Betreuer** — Docker Compose, ein Befehl, kein Python-Wissen nötig
2. **Entwickler** — `uv` (empfohlen) oder `pip`, SQLite lokal, PostgreSQL via Docker

Außerdem wird ein `pyproject.toml` hinzugefügt, das das Projekt korrekt beschreibt und `uv sync` ermöglicht.

---

## 1. Neue Dateien

### `pyproject.toml`

Minimalstruktur nach PEP 517/518. Ersetzt `requirements.txt` als kanonische Abhängigkeitsliste. `requirements.txt` bleibt für Legacy-`pip`-Nutzer erhalten (kann aus `pyproject.toml` generiert werden).

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
build-backend = "setuptools.backends.legacy:build"
```

---

## 2. README-Struktur

Das README bleibt auf Deutsch (interne HHU-Nutzung). Struktur:

### 2.1 Header (kurz)
Projektname, Beschreibung, Institut — wie bisher.

### 2.2 Schnellstart — Docker (primär, für Lab-Betrieb)

Ziel: zwei Befehle, fertig. Erklärt:
- Voraussetzung: Docker Desktop installiert
- `docker compose up --build`
- Öffne `http://localhost:5000`
- Hinweis: Daten bleiben im Docker-Volume `pgdata` erhalten

### 2.3 Lokale Entwicklung (für Entwickler)

Zwei Wege, klar getrennt:

**Option A — uv (empfohlen):**
```bash
pip install uv          # einmalig
uv sync                 # legt .venv an, installiert alle Abhängigkeiten
flask db upgrade        # erstellt Tabellen (Alembic)
flask run               # startet App auf http://localhost:5000
```

**Option B — pip:**
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
flask db upgrade
flask run
```

Wichtiger Hinweis als Info-Box:
> `flask db upgrade` **muss** beim ersten Start (und nach jedem `git pull` mit neuen Migrationen) ausgeführt werden — sonst startet die App mit leerem Schema.

### 2.4 Konfiguration (Umgebungsvariablen)

| Variable | Standard | Bedeutung |
|---|---|---|
| `DATABASE_URL` | `sqlite:///quanti_lims.db` | DB-Verbindung (SQLite oder PostgreSQL) |
| `SECRET_KEY` | Auto-generiert, in `.secret_key` gespeichert | Flask Session-Schlüssel |
| `ADMIN_BACKUP_TOKEN` | — | Optionaler Token für DB-Backup-Route |

Hinweis: Für Produktion `SECRET_KEY` explizit setzen (nicht aus `.secret_key`-Datei).

### 2.5 Datenbank-Optionen

| Modus | Verwendung | Setup |
|---|---|---|
| SQLite (Standard) | Lokale Entwicklung | Nichts extra — Datei `quanti_lims.db` wird automatisch angelegt |
| PostgreSQL | Produktion / Docker | `DATABASE_URL=postgresql://...` setzen; `docker compose up` nutzt PostgreSQL automatisch |

### 2.6 Aktualisierte Projektstruktur

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
├── Dockerfile
├── docker-compose.yml   # PostgreSQL + Web (Produktion)
├── migrations/          # Alembic-Migrationen
├── tests/               # pytest-Testsuite
├── static/
└── templates/
    ├── base.html
    ├── admin/
    ├── praktikum/       # Tagesansicht, Kalender
    ├── ta/
    ├── assignments/
    ├── results/
    └── reports/
```

### 2.7 Tests ausführen

```bash
pytest
```

### 2.8 Tech-Stack (aktualisiert)

| Schicht | Technologie |
|---|---|
| Backend | Python 3.10+ / Flask 3 |
| ORM + Migrationen | SQLAlchemy + Flask-Migrate (Alembic) |
| Datenbank | SQLite (Entwicklung) / PostgreSQL 16 (Produktion) |
| Frontend | Jinja2 + Bootstrap 5.3 + Bootstrap Icons |
| Tests | pytest |
| Container | Docker + Docker Compose |

### 2.9 Datensicherung (wie bisher, leicht aktualisiert)

Bestehenden Abschnitt behalten, ggf. präzisieren dass SQLite-Datei `quanti_lims.db` im Projektverzeichnis liegt.

### 2.10 Lizenz

Wie bisher.

---

## 3. Was NICHT geändert wird

- `requirements.txt` bleibt (wird manuell synchron gehalten mit `pyproject.toml`)
- `Dockerfile` und `docker-compose.yml` bleiben unverändert
- Keine `.env`-Datei wird hinzugefügt (Konfiguration via Umgebungsvariablen ist ausreichend)
- Keine Änderungen an Python-Quellcode

---

## 4. Betroffene Dateien

| Datei | Änderung |
|---|---|
| `README.md` | Vollständig neu geschrieben nach obiger Struktur |
| `pyproject.toml` | Neu erstellt |
