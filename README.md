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

Die Berechnungen erfolgen im ORM (model properties):

- **Reinheits-Hierarchie**: `SubstanceLot.p_effective` → analytisch > CoA > 100 %
- **Wahrer Gehalt**: `Sample.g_wahr` = (m_S,ist / m_ges,ist) × p
- **Toleranzgrenzen**: `Sample.a_min/a_max` = G_wahr × (tol_min|max / 100)
- **Titration**: `Sample.v_expected` → Direkt- oder Rücktitration
- **Bewertung**: `Result.evaluate()` → passed = (A_min ≤ Ansage ≤ A_max)

## Lizenz

Intern – AG Gohlke / CPCLab, HHU Düsseldorf
