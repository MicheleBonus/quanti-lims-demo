# Design: Praktische Reagenzmengen

**Datum:** 2026-03-23
**Status:** Genehmigt

---

## Überblick

Drei zusammenhängende Verbesserungen an der Reagenzplanung:

1. **Bürettengröße konfigurieren** — Maßlösungen erhalten eine konfigurierbare praktische Füllmenge pro Bestimmung (Bürettengröße), gespeichert auf dem `MethodReagent`-Eintrag.
2. **Bestellliste: theoretisch vs. praktisch** — Maßlösungen zeigen beide Werte nebeneinander als Cross-Check.
3. **Herstellliste: Kolbengrößen-Vorschlag** — Zusammengesetzte Reagenzien erhalten automatisch einen Vorschlag für die nächste Standardkolbengröße.
4. **Vollständigkeitsübersicht** — Hinweis, welche Maßlösungen noch keine Bürettengröße hinterlegt haben.

---

## Kontext & Datenmodell

Relevante Modelle:

- `MethodReagent`: `amount_per_determination`, `amount_per_blind`, `amount_unit`, `is_titrant`
- `Reagent`: `is_composite` (True für Herstellreagenzien)
- Formel bisher: `total = n × (k × amount_per_determination + b × amount_per_blind) × safety`

**Kategorien** (keine neuen Felder nötig, aus bestehenden Flags ableitbar):
- `is_titrant=True` → Maßlösung (Bürettenlogik)
- `is_composite=True` → Herstellreagenz (Kolbenlogik)
- Sonst → Verbrauchsstoff (keine Anpassung)

---

## Feature 1 — Bürettengröße konfigurieren

### Datenmodell

**Neues Feld:** `MethodReagent.practical_amount_per_determination` (Float, nullable)

- Speichert die Bürettenfüllmenge in der Einheit des jeweiligen `amount_unit`
- Nur semantisch sinnvoll wenn `is_titrant=True`; wird für andere Reagenzien ignoriert
- Kein Semesterbezug — Bürettengröße ist methodenspezifisch, nicht semesterabhängig
- Migration: neues nullable-Feld, keine Altdaten-Migration nötig

### Admin-UI (`/admin/methods/<id>/reagents`)

**Tabelle (bestehende Einträge):**
- Neue Spalte "Bürettengröße": zeigt Wert + Einheit falls vorhanden; zeigt `<span class="badge bg-warning">nicht konfiguriert</span>` falls `is_titrant=True` und Feld NULL; zeigt "–" für Nicht-Titranten
- Jede Titrant-Zeile bekommt ein kleines Inline-Formular (POST zu neuer Route `POST /admin/method-reagents/<id>/set-practical`) mit Zahleneingabe + Vorschlag-Buttons (10 / 25 / 50 mL)

**Hinzufügen-Formular (neuer Eintrag):**
- Neues Feld "Bürettengröße" erscheint, sobald `is_titrant`-Checkbox aktiviert wird (JavaScript show/hide)
- Vorschlag-Buttons nur wenn `amount_unit == "mL"` (da Standardgrößen in mL): 10 / 25 / 50 mL füllen das Feld vor. Bei anderer Einheit: kein Vorschlag-Button, nur Freitexteingabe.
- Feld ist optional; kein Hard-Block beim Speichern ohne Wert
- **Die bestehende Route `POST /admin/methods/<method_id>/reagents/add` wird erweitert**: liest zusätzlich `practical_amount_per_determination` aus dem Formular und speichert es, wenn `is_titrant=True` und ein Wert übergeben wurde.

**Neue Route für nachträgliche Konfiguration:**
`POST /admin/method-reagents/<id>/set-practical`
- Nimmt `practical_amount` aus dem Inline-Formular der Tabelle entgegen
- Validiert: Float > 0, gehört zu einem `is_titrant=True`-Eintrag
- Redirect zurück zur Methoden-Reagenz-Seite
- Damit ist `practical_amount_per_determination` sowohl beim Erstanlegen als auch nachträglich setzbar.

---

## Feature 2 — Bestellliste: theoretisch vs. praktisch

### Berechnung (`build_expansion` bzw. Route `reports_order_list`)

Für jeden Titrant-Eintrag (`is_titrant=True`) mit gesetztem `practical_amount_per_determination`:

```
practical_total = n × practical_amount × (k + b) × safety
```

Begründung: `practical_amount` ist das Füllvolumen **einer einzelnen Bürettenfüllung**. Die Bürette wird pro Bestimmung *und* pro Blindbestimmung je einmal vollständig befüllt. `(k + b)` ist damit die Gesamtanzahl der Füllvorgänge pro Probe (k Bestimmungen + b Blindbestimmungen). Bei `k=3, b=1` z.B. werden 4 Füllungen berechnet. In den meisten Fällen ist `amount_per_blind = 0`; wenn nicht, gilt dieselbe Logik.

Theoretischer Wert bleibt unverändert. Beide Werte werden als separate Felder weitergegeben:
- `item.total` — theoretisch (wie bisher)
- `item.practical_total` — praktisch (nur für Titranten mit konfiguriertem Wert, sonst None)
- `item.burette_size` — Bürettengröße + Einheit als Anzeigehilfe (z.B. "50 mL")

### Template (`order_list.html`)

Kein neues Tabellenspalte — der praktische Wert erscheint **inline in der bestehenden "Menge"-Zelle**, um die Tabellenbreite nicht zu vergrößern:

- Für Titranten mit `practical_total`: Zelle zeigt `<praktisch>` fett + `(<theoretisch> theoret.)` klein/gedimmt darunter
- Für Titranten ohne `practical_total`: zeigt theoretischen Wert + kleines Badge "Bürettengröße fehlt"
- Für Nicht-Titranten: wie bisher, kein zweiter Wert

---

## Feature 3 — Herstellliste: Kolbengrößen-Vorschlag

### Berechnung (Route `reports_prep_list`)

Standardkolbengrößen (hardcoded): `[50, 100, 250, 500, 1000, 2000]` mL

Nach Berechnung des Gesamtvolumens pro zusammengesetztem Reagenz pro Block (die Route baut Eintrags-Dicts; `rg` steht hier für einen solchen Dict-Eintrag mit Keys `"total"` und `"unit"`):

```python
FLASK_SIZES = [50, 100, 250, 500, 1000, 2000]  # mL

# Konvertierung: rg["total"] ist in rg["unit"]; muss in mL umgerechnet werden
# using existing _VOL_TO_ML table from reagent_expansion.py
factor = _VOL_TO_ML.get(rg["unit"])
if factor is None:
    rg["suggested_flask"] = None  # Nicht-Volumen-Einheit → kein Vorschlag
else:
    total_ml = rg["total"] * factor
    suggested = next((s for s in FLASK_SIZES if s >= total_ml), None)
    if suggested is None:
        batches = ceil(total_ml / 2000)
        rg["suggested_flask"] = f"{batches}× 2000 mL"
    else:
        rg["suggested_flask"] = f"{suggested} mL"
```

`rg["suggested_flask"]` wird als neuer Dict-Key übergeben und im Template via `{{ rg.suggested_flask }}` (Jinja dict-access) ausgelesen. Die Konvertierung ist nötig, da `rg["unit"]` je nach `reagent.base_unit` auch "L" o.ä. sein kann.

### Template (`prep_list.html`)

- Das bestehende Badge `{{ rg.total }} {{ rg.unit }}` wird ergänzt:
  - Falls `rg.suggested_flask` vorhanden: Badge zeigt "→ {{ rg.suggested_flask }}" als zweiten Hinweis (kleiner, gedimmt)
  - Beispiel: `847 mL  →  1000 mL`
- Kein gespeicherter Override — rein informativer Vorschlag
- Wenn `rg.unit` nicht "mL" ist, wird kein Kolbenvorschlag angezeigt (Grenzfall, z.B. Gramm-Reagenzien)

---

## Feature 4 — Vollständigkeitsübersicht

### Abfrage

Alle `MethodReagent`-Einträge mit `is_titrant=True` und `practical_amount_per_determination IS NULL`, beschränkt auf Methoden, deren Analyse im aktiven Semester mindestens einen Batch hat (konsistent mit dem Rest der `/reports/reagents`-Seite). Geordnet nach Analyse-Code.

### Anzeige (`/reports/reagents`)

Wenn fehlende Einträge vorhanden:

Jeder Listeneintrag entspricht einem `MethodReagent`-Eintrag (nicht einem Reagenz), da dasselbe Reagenz in mehreren Methoden als Titrant auftauchen kann — jede Methode braucht ihre eigene Bürettengröße.

```html
<div class="alert alert-warning">
  <strong>X Maßlösungen ohne Bürettengröße:</strong>
  <ul>
    <li>I.1 Titration (Methode: Standardtitration) — HCl (0,1 mol/L) → <a href="/admin/methods/3/reagents">konfigurieren</a></li>
    <li>II.3 Komplexometrie (Methode: EDTA-Titration) — EDTA (0,1 mol/L) → <a href="/admin/methods/7/reagents">konfigurieren</a></li>
    ...
  </ul>
</div>
```

- Link führt direkt zur jeweiligen `admin/methods/<id>/reagents`-Seite
- Alert nur sichtbar wenn fehlende Einträge vorhanden
- Wenn alle konfiguriert: kein Alert (kein "alles ok"-Banner nötig)

---

## Abhängigkeiten

- Feature 2 baut auf Feature 1 auf (braucht das neue Feld)
- Feature 3 und 4 sind unabhängig

## Reihenfolge

1. Feature 1 (DB-Feld + Admin-UI)
2. Feature 2 (Bestellliste)
3. Feature 3 (Herstellliste)
4. Feature 4 (Vollständigkeitsübersicht)
