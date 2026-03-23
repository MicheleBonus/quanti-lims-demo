# Design: Kolbengrößen-Konfiguration für Herstellreagenzien

**Datum:** 2026-03-23
**Status:** Genehmigt

---

## Überblick

Zusammengesetzte Reagenzien werden in Standardkolben hergestellt. Die bisherige Implementierung schlägt bereits eine Kolbengröße vor (nächste Standardgröße ≥ theoretischer Bedarf), berechnet die Zutatenmengen aber weiterhin auf Basis des theoretischen Bedarfs statt der tatsächlichen Kolbengröße. Dadurch stimmen Herstellungsvorschrift, Bestellliste und Reagenzübersicht nicht mit der realen Laborpraxis überein.

Dieses Feature ermöglicht es dem TA, die Kolbengröße pro Reagenz und Block zu bestätigen oder zu überschreiben. Alle nachgelagerten Berechnungen (Zutatenmengen Herstellliste, Basisreagenz-Mengen Bestellliste, Reagenzübersicht) nutzen dann die effektive Kolbengröße.

---

## Kontext & Datenmodell

Relevante Modelle:
- `Reagent`: `is_composite` (True für Herstellreagenzien)
- `ReagentComponent`: `quantity`, `quantity_unit`, `per_parent_volume_ml` — Rezeptur eines zusammengesetzten Reagenz
- `Block`: identifiziert den Praktikumsblock; NULL steht für "Vorabherstellungen"
- `build_expansion(batches)` in `reagent_expansion.py`: liefert `prep_items` (Herstellreagenzien) und `order_items` (Basisreagenzien, rekursiv expandiert)

Bisherige Komponentenformel in `reports_prep_list`:
```
comp_total = theoretical_total / per_parent_volume_ml × quantity
```

---

## Datenmodell — Neue Tabelle `PrepFlaskConfig`

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | Integer PK | |
| `reagent_id` | Integer FK → Reagent | zusammengesetztes Reagenz |
| `block_id` | Integer FK → Block, nullable | Block im Semester; NULL = Vorabherstellungen |
| `flask_size_ml` | Float, not null | gewählte Kolbengröße in mL |

**Unique Constraint**: `(reagent_id, block_id)`

Die Anzahl Kolben und die Effektivmenge werden immer implizit berechnet:
```
count = ceil(theoretical_total / flask_size_ml)
effective_total = flask_size_ml × count
```

Kein Semesterbezug — `block_id` ist bereits block-spezifisch und damit indirekt semesterspezifisch. Migration: neues nullable-Feld, keine Altdaten-Migration nötig.

---

## Feature 1 — Herstellliste: Kolbenauswahl & korrigierte Zutatenmengen

### UI (`/reports/reagents/prep-list`)

Jeder Eintrag eines zusammengesetzten Reagenz zeigt:
- **Effektive Menge**: `N × flask_size mL` (z.B. `2 × 500 mL`), vorausgefüllt mit Override aus `PrepFlaskConfig` falls vorhanden, sonst mit dem bisherigen Vorschlag
- **Theoretischer Bedarf** klein darunter als Referenz: `(Bedarf: 830 mL)`
- **Quick-Select-Buttons**: eine kleine Auswahl passender Standardkolbengrößen (`[50, 100, 250, 500, 1000, 2000]` mL), sinnvoll gefiltert auf Optionen rund um den Bedarf (z.B. die nächst-kleinere und 2–3 größere Standardgrößen)
- **POST** zu `POST /prep-flask-config/<reagent_id>/<block_id>` → speichert in `PrepFlaskConfig` (INSERT OR UPDATE) → Redirect zurück zur Herstellliste

Für `block_id=None` (Vorabherstellungen) wird ein Sentinel-Wert `0` in der URL verwendet.

### Berechnung

```python
# Lookup: Override oder Vorschlag
config = PrepFlaskConfig.query.filter_by(reagent_id=rg_id, block_id=block_id).first()
if config:
    flask_size = config.flask_size_ml
else:
    flask_size = suggested_flask_size(theoretical_total)  # bisherige Logik

count = ceil(theoretical_total / flask_size)
effective_total = flask_size * count

# Zutaten
comp_total = effective_total / comp.per_parent_volume_ml * comp.quantity
```

Die `suggested_flask` Logik aus dem vorherigen Feature (Standardgrößen `[50, 100, 250, 500, 1000, 2000]` mL) wird für die Vorauswahl wiederverwendet.

---

## Feature 2 — Bestellliste: kolbenkorrigierte Basisreagenz-Mengen

### Problem

`build_expansion` expandiert zusammengesetzte Reagenzien rekursiv und akkumuliert Basisreagenz-Mengen in `order_acc`. Diese Mengen basieren auf dem theoretischen Bedarf. Nach der Kolbenkorrektur weicht der `effective_total` vom `theoretical_total` ab — alle Basisreagenzien, die über ein Herstellreagenz bezogen werden, müssen entsprechend skaliert werden.

### Lösung: Provenienz-Tracking + Post-Processing in `build_expansion`

`expand_reagent` wird erweitert: beim Akkumulieren in `order_acc` wird zusätzlich ein `composite_contrib_acc` befüllt, das aufzeichnet, welcher Anteil jedes Basisreagenz über welches Herstellreagenz (identifiziert durch `reagent_id`) und welchen Block kam:

```python
composite_contrib_acc[(base_reagent_id, composite_reagent_id, block_info)] += amount_in_base_unit
```

Nach dem Durchlauf aller Batches (bevor `order_items` gebaut wird):

```python
for (base_id, composite_id, block_info), contrib in composite_contrib_acc.items():
    config = flask_configs.get((composite_id, block_info[0] if block_info else None))
    theoretical = prep_acc[composite_id][block_info]["total"]
    effective = compute_effective_total(theoretical, config)
    scale = effective / theoretical if theoretical > 0 else 1.0
    # Skalierung des Beitrags in order_acc
    order_acc[base_id]["total"] += contrib * (scale - 1.0)
    # (contrib * scale - contrib = delta; bestehender Wert += delta)
```

`flask_configs` ist ein Dict `{(reagent_id, block_id): flask_size_ml}`, das aus der DB geladen und in `build_expansion` übergeben wird.

Die Signatur von `build_expansion` wird erweitert:
```python
def build_expansion(batches, flask_configs=None) -> dict:
```

`flask_configs=None` bedeutet: keine Korrekturen (bisheriges Verhalten bleibt rückwärtskompatibel).

### Ergebnis

Die Bestellliste zeigt für alle Basisreagenzien die kolbenkorrigierten Mengen. Für direkt verwendete Basisreagenzien (nicht über Herstellreagenz) ändert sich nichts.

---

## Feature 3 — Reagenzübersicht: kolbenkorrigierte Anzeige & Vollständigkeitswarnung

### Korrigierte Komponentenanzeige (`/reports/reagents`)

Die Übersicht berechnet Komponentenmengen aktuell inline im Template:
```
(d.total / comp.per_parent_volume_ml * comp.quantity)|round(1)
```

`d.total` wird durch `d.effective_total` ersetzt — die Summe der kolbenkorrigierten Effektivmengen über alle Blöcke des Semesters. Dieser Wert wird von `build_expansion` (das ihn für die Bestellliste berechnet) als zusätzlicher Key `effective_total` im `prep_items`-Dict mitgeliefert.

### Vollständigkeitswarnung

Analog zur Bürettengrößen-Warnung erscheint ein Alert, wenn zusammengesetzte Reagenzien ohne `PrepFlaskConfig`-Eintrag existieren (und im aktiven Semester mindestens einen Batch haben):

```html
<div class="alert alert-warning">
  <strong>X Herstellreagenzien ohne bestätigte Kolbengröße:</strong>
  <ul>
    <li>Ammoniumpuffer — Block 1 → <a href="/reports/reagents/prep-list">konfigurieren</a></li>
    ...
  </ul>
</div>
```

- Alert nur wenn fehlende Einträge vorhanden
- Link führt zur Herstellliste (wo die Kolbengröße gesetzt werden kann)

---

## Abhängigkeiten & Reihenfolge

1. **Feature 1** (DB-Tabelle + Herstellliste-UI + korrigierte Zutaten) — Grundlage
2. **Feature 2** (Bestellliste-Korrektur) — baut auf Feature 1 auf (braucht `flask_configs` aus DB)
3. **Feature 3** (Reagenzübersicht) — unabhängig von Feature 2, baut nur auf Feature 1 auf

## Standardkolbengrößen

```python
FLASK_SIZES_ML = [50, 100, 250, 500, 1000, 2000]
```

Für die Quick-Select-Buttons werden nur Größen angezeigt, bei denen `count × size` sinnvoll ist: konkret die nächst-kleinere Standardgröße (die mehrfach benötigt würde) und bis zu 3 größere Optionen.
