# V_disp-Berechnung bei Titereinstellungen — Korrektur & Erweiterung

## Ziel

Die automatische Berechnung von `V_disp,min`/`V_disp,max` im Ansatzbogen und der `Zielfaktor` in der Einwaagemaske sind für Titereinstellungs-Analysen falsch. Beide verwenden bisher die Formel `(e_ab_ps_g × 1000) / m_eq_primary_mg`, die den Verbrauch des Studierenden in der Titration gegen den Primärstandard berechnet — nicht das Volumen, das die TA aus der Stammlösung dispensieren soll. Dieses Spec beschreibt die Korrekturen.

## Hintergrund

Bei Titereinstellungen (z.B. „Einstellung Salzsäure 0,1 mol/L") dispensiert die TA ein Volumen einer konzentrierten Stammlösung (z.B. 1 M HCl), das die Studierenden anschließend auf ein definiertes Volumen (z.B. 100 mL) auffüllen. Der Faktor der daraus resultierenden Lösung ergibt sich direkt aus dem dispensierten Volumen:

```
Zielfaktor = V_dispensiert / V_disp_theo
V_disp_theo = V_Verdünnung × c_Soll / c_Stamm
```

Beispiel: c_Stamm=1.0 M, V_Verdünnung=100 mL, c_Soll=0.1 M → V_disp_theo=10.000 mL.
Bei V_dispensiert=9.46 mL → Zielfaktor=0.9460.

Die Felder `e_ab_ps_g` und `m_eq_primary_mg` beschreiben dagegen die Titration gegen den Primärstandard (Methoden-Vorschau) und bleiben unverändert.

## Neue Felder (Method-Modell)

| Feld | Typ | Bedeutung |
|---|---|---|
| `c_stock_mol_l` | Float, nullable | Stammkonzentration der Ausgangslösung (mol/L), z.B. 1.0 |
| `v_dilution_ml` | Float, nullable | Volumen auf das Studierende auffüllen (mL), z.B. 100.0 |

Beide Felder sind nur relevant im Modus `titrant_standardization` und nullable (keine Breaking Change).

## Kernformel

```
V_disp_theo = v_dilution_ml × c_titrant_mol_l / c_stock_mol_l
```

## V_disp-Bereich (Vorschlag im Ansatzbogen)

```
V_disp,min = V_disp_theo × 0.9000
V_disp,max = V_disp_theo × 1.1000
```

Diese ±10%-Spanne gilt für alle Titereinstellungs-Analysen als fester Standardwert. Sie lässt sich im Ansatzbogen manuell überschreiben.

## Betroffene Komponenten

### 1. `models.py`
- Zwei neue Spalten auf `Method`: `c_stock_mol_l FLOAT`, `v_dilution_ml FLOAT`
- Schema-Migration in `_migrate_schema()` (ALTER TABLE, wie bestehende Migrationsmuster)

### 2. `app.py` — Methoden-Route (`admin_method_form`)
- Liest und speichert `c_stock_mol_l` und `v_dilution_ml` aus dem Formular (nur im Standardisierungs-Modus)

### 3. `app.py` — API `/api/analysis/<id>/defaults`
- Gibt `v_disp_theoretical_ml` zurück wenn `c_stock_mol_l`, `v_dilution_ml` und `c_titrant_mol_l` gesetzt sind:
  ```python
  v_disp_theoretical_ml = round(method.v_dilution_ml * method.c_titrant_mol_l / method.c_stock_mol_l, 4)
  ```
- `v_theoretical_ml` (Titrations-Volumen) bleibt im API-Response erhalten (wird in method_form-Vorschau benötigt)

### 4. `templates/admin/method_form.html`
- Zwei neue Eingabefelder im Standardisierungs-Block (neben `e_ab_ps_g`):
  - `c_stock_mol_l`: "c_Stamm (mol/L)" mit Hilfstext
  - `v_dilution_ml`: "V_Verdünnung (mL)" mit Hilfstext
- Berechnungsvorschau (`updateCalcPreview`): Die bestehende Zeile `V_theoretisch = (e_ab_ps × 1000) / m_eq` (Verbrauch des Studierenden bei der Titration) bleibt erhalten — sie ist korrekt. Zusätzlich wird darunter eine neue Zeile ausgegeben:
  ```
  V_disp,theo = V_Verdünnung × c_Soll / c_Stamm = X.XXX mL
  ```
  Diese zeigt dem Methodenersteller, welches Volumen die TA dispensieren sollte.

### 5. `templates/admin/batch_form.html`
- `recalcVolumeFields()` verwendet `v_disp_theoretical_ml` statt `v_theoretical_ml`. Die Guard-Bedingung (`if (!currentDefaults.v_theoretical_ml)`) wird auf `v_disp_theoretical_ml` umgestellt:
  ```javascript
  if (!currentDefaults || !currentDefaults.v_disp_theoretical_ml) return;
  const vDisp = currentDefaults.v_disp_theoretical_ml;
  vMin = +(vDisp * 0.9).toFixed(3)
  vMax = +(vDisp * 1.1).toFixed(3)
  ```
- Hinweistext im Alert `hint-standardization` aktualisiert: „V_min und V_max werden aus Stammkonzentration und Verdünnungsvolumen berechnet (V_theo × 0.9 / 1.1)."
- Help-Text der Felder `target_v_min_ml` und `target_v_max_ml` aktualisiert

### 6. `templates/ta/weighing.html`
- `V_THEORETICAL_ML` JS-Konstante verwendet die neue Formel:
  ```jinja2
  const V_THEORETICAL_ML = {{ (m.v_dilution_ml * m.c_titrant_mol_l / m.c_stock_mol_l) | round(4)
    if m and m.v_dilution_ml and m.c_titrant_mol_l and m.c_stock_mol_l and m.c_stock_mol_l > 0
    else 'null' }};
  ```
- Server-seitige Zielfaktor-Zelle (`id="factor-{{ s.id }}"`) verwendet dieselbe neue Formel
- Guard-Bedingungen prüfen die neuen Felder

### 7. `init_db.py`
- Methode I.1 erhält `c_stock_mol_l=1.0` und `v_dilution_ml=100.0`
- Hinweis: Die Migration fügt die Spalten als NULL hinzu. Bestehende Methoden in produktiven Datenbanken müssen die neuen Felder manuell über „Methode bearbeiten" nachtragen. Das ist kein Blocker — AC#4 stellt sicher, dass fehlende Felder keinen Fehler verursachen.

## Was sich NICHT ändert

- `e_ab_ps_g`, `m_eq_primary_mg`, `primary_standard_id` — weiterhin für Methoden-Vorschau
- `v_theoretical_ml` im API-Response — weiterhin für die Vorschau im `method_form`
- `TitrantStandardizationEvaluator` — keine Änderung der Validierungslogik
- Massenbasierte Analysen — vollständig unberührt

## Akzeptanzkriterien

1. Methode I.1 mit c_stock=1.0, v_dilution=100.0 → API gibt `v_disp_theoretical_ml=10.000` zurück
2. Ansatzbogen schlägt V_min=9.000, V_max=11.000 vor
3. Einwaagemaske zeigt Zielfaktor=0.9460 wenn V_dispensiert=9.46 mL (statt ~0.167)
4. Methode mit fehlenden neuen Feldern → kein Fehler, Felder bleiben leer/null
5. Massenbasierte Analysen funktionieren unverändert
