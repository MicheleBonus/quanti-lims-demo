# Design: Kolbengrößen-Konfiguration für Herstellreagenzien

**Datum:** 2026-03-23
**Status:** Genehmigt

---

## Überblick

Zusammengesetzte Reagenzien werden in Standardkolben hergestellt. Die bisherige Implementierung schlägt bereits eine Kolbengröße vor (nächste Standardgröße ≥ theoretischer Bedarf), berechnet die Zutatenmengen aber weiterhin auf Basis des theoretischen Bedarfs statt der tatsächlichen Kolbengröße. Dadurch stimmen Herstellungsvorschrift, Bestellliste und Reagenzübersicht nicht mit der realen Laborpraxis überein.

Dieses Feature ermöglicht es dem TA, die Kolbengröße pro Reagenz und Block zu bestätigen oder zu überschreiben. Alle nachgelagerten Berechnungen (Zutatenmengen Herstellliste, Basisreagenz-Mengen Bestellliste, Reagenzübersicht) nutzen dann die effektive Kolbengröße.

---

## Kontext & Datenmodell

Relevante Modelle und Strukturen:

- `Reagent`: `is_composite` (True für Herstellreagenzien)
- `ReagentComponent`: `quantity`, `quantity_unit`, `per_parent_volume_ml`
- `SampleBatch`: hat `block` (Relationship → `Block`); `batch.block.id` und `batch.block.name` sofern ein Block zugeordnet ist; `batch.block` kann None sein (Vorabherstellungen)
- `build_expansion(batches)` in `reagent_expansion.py`:
  - `prep_acc` / `prep_items`: keyed `reagent_id → {block_info → {name, unit, total, reagent}}`
    - `block_info` ist `None` für Vorabherstellungen oder Tuple `(block_id: int, block_name: str)`
  - `order_acc`: keyed `(reagent_id, unit)`
  - `order_items`: Liste von Dicts mit `{name, cas, total, unit, sources, is_titrant, practical_total, burette_amount, burette_unit}`
- `reports_reagents` (app.py ~2294): baut `demand`-Liste mit einem Dict pro `(batch, MethodReagent)`-Paar. Felder: `analysis`, `analysis_name`, `reagent` (Name als String), `reagent_obj` (ORM-Objekt), `unit`, `total`, `is_composite`, `components` (Liste von `ReagentComponent`), u.a. Enthält **kein** `block_info`-Feld bisher.

Standardkolbengrößen (hardcoded): `FLASK_SIZES_ML = [50, 100, 250, 500, 1000, 2000]`

Neue Hilfsfunktion (muss erstellt werden, in `reagent_expansion.py` oder `app.py`):
```python
def _suggest_flask_size_ml(total_ml: float) -> float:
    """Gibt den numerischen mL-Wert der nächsten Standardgröße ≥ total_ml zurück.
    Für total_ml > 2000: gibt 2000.0 zurück (mehrere Kolben werden durch count abgedeckt).
    """
    for s in FLASK_SIZES_ML:
        if s >= total_ml:
            return float(s)
    return 2000.0
```
Die bisherige `suggested_flask`-Logik in `reports_prep_list` (gibt einen Anzeigestring zurück) bleibt unverändert; `_suggest_flask_size_ml` ist die neue numerische Variante.

---

## Datenmodell — Neue Tabelle `PrepFlaskConfig`

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | Integer PK | |
| `reagent_id` | Integer FK → Reagent, not null | zusammengesetztes Reagenz |
| `block_id` | Integer, nullable | Block-ID; NULL = Vorabherstellungen |
| `flask_size_ml` | Float, not null | gewählte Kolbengröße in mL |

**Hinweis zu `block_id`**: Kein FK auf `Block` (da NULL semantisch "kein Block" bedeutet und kein `Block` mit id=0 existiert — SQLAlchemy-PKs starten bei 1). Kein DB-Level UNIQUE-Constraint, da SQLite NULL-Werte in UNIQUE-Constraints als distinkt behandelt (mehrere NULLs wären erlaubt). Eindeutigkeit wird **auf Anwendungsebene** sichergestellt: Upsert prüft `filter_by(reagent_id=X, block_id=Y).first()`, dann UPDATE oder INSERT.

Effektivmenge wird immer implizit berechnet:
```python
from math import ceil
count = ceil(theoretical_total / flask_size_ml)
effective_total = flask_size_ml * count
```

Migration: neue Tabelle via Alembic (`flask db migrate` + `flask db upgrade`), keine Altdaten-Migration nötig.

---

## Feature 1 — Herstellliste: Kolbenauswahl & korrigierte Zutatenmengen

### UI (`/reports/reagents/prep-list`)

Jeder Eintrag eines zusammengesetzten Reagenz zeigt:
- **Effektive Menge**: `N × flask_size mL` (z.B. `2 × 500 mL`), vorausgefüllt mit dem Override aus `PrepFlaskConfig` falls vorhanden, sonst mit dem bisherigen Vorschlag (`_suggest_flask`)
- **Theoretischer Bedarf** klein darunter als Referenz: `(Bedarf: 830 mL)`
- **Quick-Select-Buttons**: alle S aus `FLASK_SIZES_ML` für die `1 ≤ ceil(theoretical / S) ≤ 5` gilt. Fallback wenn kein S diese Bedingung erfüllt: alle S mit `ceil(theoretical / S) ≤ 10`.
- **POST** zu `POST /prep-flask-config/<reagent_id>/<block_id>`, wobei Vorabherstellungen mit `block_id=0` in der URL codiert werden. Route konvertiert `0 → None` für DB-Lookup. `Block`-PKs starten bei 1, 0 ist sicherer Sentinel.
- Route führt Upsert durch:
  ```python
  db_block_id = None if block_id_url == 0 else block_id_url
  cfg = PrepFlaskConfig.query.filter_by(reagent_id=reagent_id, block_id=db_block_id).first()
  if cfg:
      cfg.flask_size_ml = new_size
  else:
      db.session.add(PrepFlaskConfig(reagent_id=reagent_id, block_id=db_block_id, flask_size_ml=new_size))
  db.session.commit()
  ```

### Berechnung in `reports_prep_list`

```python
# flask_configs laden (für gesamte Route, einmalig):
from math import ceil
flask_configs = {(c.reagent_id, c.block_id): c.flask_size_ml
                 for c in PrepFlaskConfig.query.all()}

# Pro Herstellreagenz-Eintrag (rg_id, block_key, item):
# block_key ist None oder (block_id, block_name)
db_block_id = block_key[0] if block_key is not None else None
flask_size = flask_configs.get((rg_id, db_block_id))
theoretical = item["total"]
if flask_size is None:
    flask_size = _suggest_flask_size_ml(theoretical)  # numerischer Wert in mL
count = ceil(theoretical / flask_size) if flask_size > 0 else 1
effective_total = flask_size * count

# Zutatenmengen (in quantity_unit, direkte Anzeige ohne convert_to_base_unit):
comp_total = round(effective_total / comp.per_parent_volume_ml * comp.quantity, 2)

# effective_total für Feature 2/3 speichern:
item["effective_total"] = effective_total
item["flask_size"] = flask_size
item["flask_count"] = count
```

`_suggest_flask_size_ml` gibt den numerischen mL-Wert der nächsten Standardgröße zurück (analog zur bestehenden Logik in `reports_prep_list`, extrahiert als Hilfsfunktion).

---

## Feature 2 — Bestellliste: kolbenkorrigierte Basisreagenz-Mengen

### Erweiterung von `expand_reagent` — Provenienz-Tracking

`expand_reagent` erhält zwei neue optionale Parameter:

```python
def expand_reagent(
    reagent, amount, unit,
    order_acc, prep_acc, dep_graph, warnings,
    visiting=None, caller_name=None, block_info=None, analysis_info=None,
    composite_contrib_acc=None,   # NEU
    top_composite_id=None,        # NEU
) -> None:
```

Die neuen Parameter werden als Keyword-Argumente an alle bestehenden rekursiven Aufrufe weitergegeben. Bestehende Call-Sites in `build_expansion` sind nicht betroffen (sie nutzen bereits Keyword-Argumente).

- `top_composite_id`: ID des obersten Herstellreagenz in der aktuellen Rekursionskette, oder `None` wenn das Reagenz direkt (nicht über ein Composite) verwendet wird.
- `composite_contrib_acc`: Dict, in das Beiträge von Basisreagenzien über Composites akkumuliert werden.

Verhalten:
- Wenn `reagent.is_composite == True` und `top_composite_id is None`: setze `top_composite_id = reagent.id` für alle rekursiven Aufrufe dieser Kette.
- Wenn `reagent.is_composite == True` und `top_composite_id is not None`: behalte `top_composite_id` (oberster Parent bleibt erhalten — korrekt bei verschachtelten Composites).
- Wenn `reagent.is_composite == False` und `top_composite_id is not None` und `composite_contrib_acc is not None`: akkumuliere den Beitrag:
  ```python
  key = (reagent.id, unit, top_composite_id, block_info)
  composite_contrib_acc[key] = composite_contrib_acc.get(key, 0.0) + amount
  ```
  `unit` und `amount` sind die Parameter im aktuellen Aufruf-Frame — d.h. derselbe `unit`-Wert, der auch für `order_acc[(reagent.id, unit)]` verwendet wird (nach der Konvertierungskette, oder im Fallback die Originaleinheit). Die Keys beider Dicts sind damit konsistent.

### Post-Processing in `build_expansion`

Neue Signatur:
```python
def build_expansion(batches, flask_configs=None) -> dict:
    # flask_configs: dict[(reagent_id, block_id_or_None) → flask_size_ml] | None
```

Nach dem Durchlauf aller Batches, vor dem Bauen von `order_items` — innerhalb von `build_expansion`, mit Zugriff auf die lokalen `prep_acc` und `order_acc`:

```python
if flask_configs and composite_contrib_acc:
    for (base_id, unit, composite_id, block_info) in composite_contrib_acc:
        db_block_id = block_info[0] if block_info is not None else None
        flask_size = flask_configs.get((composite_id, db_block_id))
        if flask_size is None:
            continue  # kein Override, kein Post-Processing für diesen Eintrag
        theoretical = prep_acc[composite_id][block_info]["total"]
        if theoretical <= 0:
            continue
        count = ceil(theoretical / flask_size)
        effective = flask_size * count
        scale = effective / theoretical
        contrib = composite_contrib_acc[(base_id, unit, composite_id, block_info)]
        order_acc[(base_id, unit)]["total"] += contrib * (scale - 1.0)
        # delta = contrib * (scale-1): addiert den Unterschied zwischen
        # flask-korrigiertem Beitrag und theoretischem Beitrag.
        # Da scale >= 1.0 immer gilt (effective >= theoretical), ist delta >= 0.
```

`flask_configs=None` → `composite_contrib_acc` wird nicht befüllt, kein Post-Processing → Rückwärtskompatibilität bleibt erhalten.

---

## Feature 3 — Reagenzübersicht: kolbenkorrigierte Anzeige & Vollständigkeitswarnung

### Problem

`reports_reagents` baut `demand` als eine Liste mit einem Dict pro `(batch, MethodReagent)`-Paar. Für zusammengesetzte Reagenzien berechnet das Template Komponentenmengen aus `d.total` (pro-Analyse-Beitrag). Für die Kolbenkorrektur muss `d.total` durch einen kolbenkorrigierten Wert ersetzt werden.

### Lösung: block_info pro Demand-Eintrag + Skalierung

In `reports_reagents` wird pro Demand-Eintrag `block_info` ergänzt:

```python
# In der demand-Schleife (for batch in batches: for mr in method.reagent_usages:):
block_info = (batch.block.id, batch.block.name) if batch.block else None
demand.append({
    ...  # alle bisherigen Felder
    "block_info": block_info,   # NEU
})
```

Nach der Schleife wird `build_expansion(batches, flask_configs)` aufgerufen, um `prep_items` mit per-Block-Totals zu erhalten:

```python
flask_configs = {(c.reagent_id, c.block_id): c.flask_size_ml
                 for c in PrepFlaskConfig.query.all()}
expansion = build_expansion(batches, flask_configs)
prep_items = expansion["prep_items"]

for d in demand:
    if not d["is_composite"]:
        d["effective_total"] = d["total"]
        continue
    rg_id = d["reagent_obj"].id
    block_info = d["block_info"]
    block_data = (prep_items.get(rg_id) or {}).get(block_info)
    if block_data and block_data["total"] > 0:
        theoretical_block = block_data["total"]
        db_block_id = block_info[0] if block_info is not None else None
        flask_size = flask_configs.get((rg_id, db_block_id))
        if flask_size:
            count = ceil(theoretical_block / flask_size)
            effective_block = flask_size * count
            scale = effective_block / theoretical_block
        else:
            scale = 1.0  # kein Override, kein Skalierung
        d["effective_total"] = round(d["total"] * scale, 4)
    else:
        d["effective_total"] = d["total"]
```

Im Template (`reagents.html`) wird `d.effective_total` statt `d.total` für die Komponentenberechnung verwendet:

```jinja
{{ (d.effective_total / comp.per_parent_volume_ml * comp.quantity)|round(1) }}
```

### Vollständigkeitswarnung

Für jedes Herstellreagenz in `prep_items` (alle `block_info`-Einträge, inklusive `None` für Vorabherstellungen) wird geprüft, ob ein `PrepFlaskConfig`-Eintrag vorhanden ist:

```python
missing = []
for rg_id, blocks in prep_items.items():
    for block_info, item in blocks.items():
        db_block_id = block_info[0] if block_info is not None else None
        if (rg_id, db_block_id) not in flask_configs:
            block_label = block_info[1] if block_info else "Vorabherstellung"
            missing.append({
                "reagent_name": item["reagent"].name,
                "block_label": block_label,
            })
```

Alert (analog zur Bürettengrößen-Warnung) mit Link zur Herstellliste:

```html
<div class="alert alert-warning">
  <strong>X Herstellreagenzien ohne bestätigte Kolbengröße:</strong>
  <ul>
    <li>Ammoniumpuffer — Block 1 → <a href="/reports/reagents/prep-list">konfigurieren</a></li>
    <li>Pufferlösung pH 4 — Vorabherstellung → <a href="/reports/reagents/prep-list">konfigurieren</a></li>
    ...
  </ul>
</div>
```

Alert nur wenn `missing` nicht leer. Gilt für alle `block_info`-Einträge (benannte Blöcke und Vorabherstellungen).

---

## Abhängigkeiten & Reihenfolge

1. **Feature 1** — DB-Tabelle + Herstellliste-UI + korrigierte Zutaten + `effective_total` in `prep_items`
2. **Feature 2** — `build_expansion`-Erweiterung (baut auf Feature 1 auf: braucht `flask_configs` aus DB und `effective_total`-Logik)
3. **Feature 3** — Reagenzübersicht (baut auf Feature 1 auf: braucht `build_expansion` mit `flask_configs` und `prep_items`)
