# Design: Rekursive Reagenzienbedarfs-Berechnung

**Datum:** 2026-03-21
**Status:** Genehmigt
**Bereich:** Reagenzienberichte (Herstellliste, Bestellliste)

---

## Problem

Die aktuelle Reagenzienbedarfs-Berechnung expandiert Composite-Reagenzien nur eine Ebene tief. Composite-Reagenzien, die selbst als Komponenten anderer Composites eingesetzt werden (Zwischen-Composites), werden:

1. nicht in ihre Basisbestandteile aufgelöst → falscher Bestellbedarf
2. nicht auf der Herstellliste angezeigt → fehlende Herstellungsanweisung
3. nicht korrekt nach Abhängigkeiten sortiert

Zusätzlich: BOM-Einträge können Mengen in einer anderen Einheit (z.B. g) angeben als die Basiseinheit des Reagenzes (z.B. mL). Das Feld `density_g_ml` existiert im Modell, wird aber nicht für die Konversion genutzt.

**Beispiel:**
Methode → "Ammoniumchlorid-Pufferlösung pH 10,0 R" (Composite)
→ enthält "Ammoniaklösung R" (Composite, Zwischen-Composite)
→ enthält "Ammoniak-Lösung, konzentrierte R" (67 g) + "Wasser R" (26,0 mL)

Aktuell: "Ammoniak-Lösung, konzentrierte R" und "Wasser R" tauchen weder in der Bestell- noch in der Herstellliste auf.

---

## Lösung: Ansatz A — Rekursive Python-Expansion zur Laufzeit

### Einheiten-Konversion

```python
def convert_to_base_unit(reagent, amount, from_unit):
    """
    Konvertiert amount/from_unit in die base_unit des Reagenzes.

    Returns: (converted_amount, base_unit, warning_message_or_None)
    """
```

**Dimensionen:**

- Masse-Dimension: µg, mg, g, kg (Basiseinheit für Aggregation: g)
- Volumen-Dimension: µL, mL, L (Basiseinheit für Aggregation: mL)

**Fälle:**

| from_unit Dimension | base_unit Dimension | Aktion |
|---|---|---|
| Masse → Masse (z.B. mg → g) | Masse | Skalierungsfaktor (mg÷1000, kg×1000 usw.) |
| Volumen → Volumen (z.B. µL → mL) | Volumen | Skalierungsfaktor (µL÷1000, L×1000 usw.) |
| Masse → Volumen (g → mL) | Volumen | `amount_mL = amount_g / density_g_ml` |
| Volumen → Masse (mL → g) | Masse | `amount_g = amount_mL × density_g_ml` |
| inkompatibel / Dichte fehlt | — | Originaleinheit beibehalten + Warning |

Warnungen werden in der Bestellliste als Badge angezeigt — kein stiller Fehler.

`convert_to_base_unit()` wird an **zwei Stellen** eingesetzt:
1. **Einstiegspunkt** (Aufruf-Site): `mr.amount_unit` → `reagent.base_unit` umrechnen, bevor `expand_reagent()` aufgerufen wird.
2. **Innerhalb der Expansion**: für jede BOM-Komponente `comp.quantity_unit` → `comp.child.base_unit`.

So ist garantiert, dass alle Mengen in `order_acc` und `prep_acc` immer in der `base_unit` des jeweiligen Reagenzes vorliegen.

---

### Kernalgorithmus

Neue Hilfsfunktionen in `reagent_expansion.py` (neues Modul):

```python
def expand_reagent(reagent, amount, unit, order_acc, prep_acc, dep_graph, visiting=None):
    """
    Rekursiv den Reagenzien-Baum traversieren.

    Args:
        reagent:    Reagent-Objekt (amount bereits in reagent.base_unit)
        amount:     benötigte Menge (float, in base_unit)
        unit:       base_unit des Reagenzes (str)
        order_acc:  defaultdict[(reagent_id, unit)] -> float  — Bestellliste
        prep_acc:   defaultdict[(reagent_id, unit)] -> float  — Herstellliste
        dep_graph:  dict[reagent_id] -> set[reagent_id]       — Abhängigkeitsgraph
        visiting:   set[reagent_id]  — Zyklus-Guard für laufende Rekursion
    """
```

**Logik:**

- `visiting` wird bei jedem Aufruf initialisiert (falls None: leeres Set) und innerhalb eines Pfades weitergereicht.
- **Zyklus-Guard**: falls `reagent.id in visiting` → `raise ValueError(f"Zyklische Abhängigkeit bei Reagenz {reagent.id}")`.
- Kein Composite → `order_acc[(reagent.id, unit)] += amount`, return.
- Composite:
  1. `visiting.add(reagent.id)`
  2. `prep_acc[(reagent.id, unit)] += amount` (unit = reagent.base_unit)
  3. `dep_graph.setdefault(reagent.id, set())`
  4. Für jede BOM-Komponente (`ReagentComponent`):
     - Falls `comp.per_parent_volume_ml` None oder ≤ 0: überspringen (ungültige BOM-Zeile).
     - `comp_amount = amount / comp.per_parent_volume_ml * comp.quantity`
     - `comp_amount, comp_unit, warning = convert_to_base_unit(comp.child, comp_amount, comp.quantity_unit)`
     - Falls `comp.child.is_composite`: `dep_graph[reagent.id].add(comp.child_reagent_id)`
     - Rekursiver Aufruf: `expand_reagent(comp.child, comp_amount, comp_unit, ..., visiting=set(visiting))`
       *(Kopie des visiting-Sets pro Pfad, damit Diamant-Abhängigkeiten erlaubt bleiben; das Original-visiting bleibt unverändert)*

**Hinweis zum prep_acc-Schlüssel**: Der Schlüssel ist `(reagent_id, reagent.base_unit)`. Da `amount` vor dem Aufruf immer in `base_unit` konvertiert wird, entsteht für dasselbe Reagenz immer derselbe Schlüssel — auch wenn es aus verschiedenen Pfaden erreicht wird. Keine Duplizierung.

---

### Topologischer Sort

```python
def topological_sort(dep_graph):
    """
    DFS-basierter Topo-Sort.
    dep_graph[parent_id] = {child_id, ...}  (parent hängt von children ab)
    Liefert Liste: Unter-Composites (children) zuerst, übergeordnete (parents) zuletzt.
    Wirft ValueError bei zyklischer Abhängigkeit (zweite Absicherung nach expand_reagent).
    """
```

Kantendefinition: `dep_graph[parent] → {children}` bedeutet "parent braucht children". Der Topo-Sort gibt children vor parents aus — d.h. "Ammoniaklösung R" erscheint vor "Ammoniumchlorid-Pufferlösung pH 10,0 R". Das entspricht der gewünschten Herstellreihenfolge.

Implementierung via DFS mit `visited` / `in_stack` Sets — Standard-Algorithmus, keine externe Bibliothek nötig.

---

## Geänderte Endpunkte

### `reports_order_list()` (`/reports/reagents/order-list`)

**Vorher:** 1-Ebenen-Expansion in der Endpunkt-Funktion selbst.
**Nachher:**
1. `order_acc`, `prep_acc`, `dep_graph` initialisieren.
2. Für jeden MethodReagent: `mr.amount_unit` → `reagent.base_unit` konvertieren, dann `expand_reagent()` aufrufen.
3. `order_acc` liefert die aggregierten Basisreagenzien für die Bestellliste.
4. Zwischen-Composites erscheinen **nicht** auf der Bestellliste.

### `reports_prep_list()` (`/reports/reagents/prep-list`)

**Vorher:** Zeigt nur Composites, die direkt als `MethodReagent` eingetragen sind; gruppiert nach Block.
**Nachher:**
1. Gleiche Expansion wie in `reports_order_list()` (gemeinsame Hilfsfunktion).
2. Alle Composites aus `prep_acc` werden topologisch sortiert.
3. Block-Gruppierung bleibt erhalten: jedes Composite behält seinen Block aus `analysis.block`. Zwischen-Composites, die zu keiner Analyse direkt gehören, werden in einem eigenen Abschnitt "Vorabherstellungen" o.ä. gruppiert (oder dem Block der Analyse zugeordnet, die sie indirekt benötigt).

---

## Unveränderte Bereiche

- Datenmodell: keine neuen Tabellen, keine neuen Felder (`density_g_ml` existiert bereits)
- Admin-Formulare: unverändert
- Grundformel: `n × (k × menge_per_best + b × menge_per_blind) × safety_factor`
- `reports_reagents()` (Reagenzienbedarf-Report): unverändert
- Export-Endpunkte (CSV/JSON): unverändert gelassen; nach der Umstellung der Endpunkte werden sie vorerst fehlerhafte/unvollständige Daten liefern → TODO-Kommentar im Code, Folgeschritt

---

## Templates

### `prep_list.html`
- Bestehende Kartenstruktur pro Composite bleibt erhalten
- Reihenfolge folgt topologischem Sort (Unter-Composites zuerst)
- Block-Gruppierung bleibt; Zwischen-Composites ohne direkten Block-Bezug erhalten eigene Gruppe
- Kein visuelles Redesign nötig

### `order_list.html`
- Keine strukturellen Änderungen
- Warnhinweis bei fehlender Dichte (inkompatible Einheiten): kleines Badge/Icon neben der betroffenen Zeile

---

## Neue Tests

- Rekursive Expansion über 3 Ebenen (Methode → Composite → Composite → Basis)
- Zwischen-Composite erscheint auf Herstellliste, nicht auf Bestellliste
- Zyklus-Erkennung während Traversal: `ValueError` bei zyklischer BOM
- Diamant-Abhängigkeit: Reagenz A wird von B und C benötigt, beide von D — A erscheint einmal mit summierter Menge
- Einheiten-Konversion: g → mL mit Dichte, mL → g mit Dichte, fehlende Dichte → Warning
- Einheiten-Konversion am Einstiegspunkt: `mr.amount_unit != reagent.base_unit`
- `per_parent_volume_ml` = None oder 0: BOM-Zeile wird übersprungen, kein ZeroDivisionError
- Topologischer Sort: korrekte Reihenfolge bei mehreren Abhängigkeiten
- Bedarfs-Aggregation: gleicher Basisreagenz aus zwei verschiedenen Composites wird summiert

---

## Offene Punkte

- Dichte-Werte müssen für betroffene Reagenzien manuell im Admin nachgepflegt werden (z.B. "Ammoniak-Lösung, konzentrierte R")
- Block-Zuordnung für Zwischen-Composites: genaue Gruppenbezeichnung im Template mit Benutzer abstimmen
- Export-Endpunkte (CSV/JSON) werden in einem Folgeschritt angepasst
