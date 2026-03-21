# Recursive Reagent Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 1-level composite expansion in the reagent reports with fully recursive expansion, topological sort for the prep list, and density-based unit conversion.

**Architecture:** A new `reagent_expansion.py` module provides three pure functions (`convert_to_base_unit`, `topological_sort`, `expand_reagent`) and one driver (`build_expansion`). Both `reports_order_list()` and `reports_prep_list()` in `app.py` are replaced to call `build_expansion()`. No data model changes.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy, pytest with MagicMock for unit tests. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-21-reagent-calculation-recursive-expansion-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `reagent_expansion.py` | Create | All expansion logic: unit conversion, recursive traversal, topo sort, driver |
| `tests/test_reagent_expansion.py` | Create | Unit tests for `reagent_expansion.py` (pure, uses MagicMock) |
| `app.py` lines 1949–2071 | Modify | Replace `reports_order_list()` and `reports_prep_list()` bodies |
| `tests/test_reagent_demand.py` | Modify | Add integration tests for the two routes with nested composites |
| `templates/reports/order_list.html` | Modify | Add warnings section below the table |

**Note:** `templates/reports/prep_list.html` requires **no changes** — the existing `blocks` structure already supports a "Vorabherstellungen" block with `id=None`.

---

## Task 1: `convert_to_base_unit()` with tests

**Files:**
- Create: `reagent_expansion.py`
- Create: `tests/test_reagent_expansion.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reagent_expansion.py
"""Unit tests for reagent_expansion module."""
from unittest.mock import MagicMock
import pytest


def make_reagent(base_unit, density=None):
    r = MagicMock()
    r.base_unit = base_unit
    r.density_g_ml = density
    r.name = f"TestReagent[{base_unit}]"
    return r


class TestConvertToBaseUnit:
    def test_same_unit_is_noop(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("mL")
        amount, unit, warn = convert_to_base_unit(r, 100.0, "mL")
        assert amount == 100.0
        assert unit == "mL"
        assert warn is None

    def test_mass_to_mass_mg_to_g(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("g")
        amount, unit, warn = convert_to_base_unit(r, 500.0, "mg")
        assert abs(amount - 0.5) < 1e-9
        assert unit == "g"
        assert warn is None

    def test_unknown_unit_returns_warning_not_key_error(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("g")
        # "µg" is not in UNIT_DEFINITIONS and cannot appear via UNIT_ENUM,
        # but we test the defensive guard anyway.
        amount, unit, warn = convert_to_base_unit(r, 1.0, "µg")
        assert warn is not None  # graceful warning, not KeyError

    def test_volume_to_volume_l_to_ml(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("mL")
        amount, unit, warn = convert_to_base_unit(r, 2.0, "L")
        assert abs(amount - 2000.0) < 1e-9
        assert unit == "mL"
        assert warn is None

    def test_mass_to_volume_with_density(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("mL", density=0.91)  # ammonia solution ~0.91 g/mL
        amount, unit, warn = convert_to_base_unit(r, 67.0, "g")
        assert abs(amount - 67.0 / 0.91) < 0.01
        assert unit == "mL"
        assert warn is None

    def test_volume_to_mass_with_density(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("g", density=1.84)  # conc. H2SO4
        amount, unit, warn = convert_to_base_unit(r, 5.7, "mL")
        assert abs(amount - 5.7 * 1.84) < 0.01
        assert unit == "g"
        assert warn is None

    def test_mass_to_volume_without_density_returns_warning(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("mL", density=None)
        amount, unit, warn = convert_to_base_unit(r, 67.0, "g")
        assert amount == 67.0      # unchanged
        assert unit == "g"         # original unit kept
        assert warn is not None
        assert "Dichte" in warn

    def test_incompatible_dimensions_returns_warning(self):
        from reagent_expansion import convert_to_base_unit
        r = make_reagent("pcs")
        amount, unit, warn = convert_to_base_unit(r, 5.0, "mL")
        assert warn is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd C:\Users\Miche\Documents\GitHub\quanti-lims
pytest tests/test_reagent_expansion.py -v
```
Expected: `ModuleNotFoundError: No module named 'reagent_expansion'`

- [ ] **Step 3: Create `reagent_expansion.py` with `convert_to_base_unit()`**

```python
# reagent_expansion.py
"""Recursive reagent requirement expansion for order list and prep list reports."""
from __future__ import annotations

from collections import defaultdict

from models import AMOUNT_UNIT_TYPES, AMOUNT_UNIT_MASS, AMOUNT_UNIT_VOLUME

_MASS_TO_G = {"mg": 0.001, "g": 1.0, "kg": 1000.0}
_VOL_TO_ML = {"µL": 0.001, "mL": 1.0, "L": 1000.0}


def convert_to_base_unit(
    reagent, amount: float, from_unit: str
) -> tuple[float, str, str | None]:
    """Convert amount/from_unit to reagent.base_unit via scaling or density.

    Returns (converted_amount, target_unit, warning_or_None).
    On failure, returns (original_amount, original_unit, warning_message).
    """
    target = reagent.base_unit
    if from_unit == target:
        return amount, target, None

    fd = AMOUNT_UNIT_TYPES.get(from_unit)
    td = AMOUNT_UNIT_TYPES.get(target)

    if fd == AMOUNT_UNIT_MASS and td == AMOUNT_UNIT_MASS:
        if from_unit not in _MASS_TO_G or target not in _MASS_TO_G:
            return amount, from_unit, f"Unbekannte Masseeinheit: {from_unit}→{target}"
        return amount * _MASS_TO_G[from_unit] / _MASS_TO_G[target], target, None

    if fd == AMOUNT_UNIT_VOLUME and td == AMOUNT_UNIT_VOLUME:
        if from_unit not in _VOL_TO_ML or target not in _VOL_TO_ML:
            return amount, from_unit, f"Unbekannte Volumeneinheit: {from_unit}→{target}"
        return amount * _VOL_TO_ML[from_unit] / _VOL_TO_ML[target], target, None

    if fd == AMOUNT_UNIT_MASS and td == AMOUNT_UNIT_VOLUME:
        if not reagent.density_g_ml:
            return amount, from_unit, f"Dichte fehlt für '{reagent.name}' (g→mL)"
        ml = amount * _MASS_TO_G[from_unit] / reagent.density_g_ml
        return ml / _VOL_TO_ML[target], target, None

    if fd == AMOUNT_UNIT_VOLUME and td == AMOUNT_UNIT_MASS:
        if not reagent.density_g_ml:
            return amount, from_unit, f"Dichte fehlt für '{reagent.name}' (mL→g)"
        g = amount * _VOL_TO_ML[from_unit] * reagent.density_g_ml
        return g / _MASS_TO_G[target], target, None

    return (
        amount,
        from_unit,
        f"Einheitenkonvertierung nicht möglich: {from_unit}→{target} für '{reagent.name}'",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_reagent_expansion.py::TestConvertToBaseUnit -v
```
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add reagent_expansion.py tests/test_reagent_expansion.py
git commit -m "feat: add convert_to_base_unit with tests"
```

---

## Task 2: `topological_sort()` with tests

**Files:**
- Modify: `reagent_expansion.py`
- Modify: `tests/test_reagent_expansion.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_reagent_expansion.py`:

```python
class TestTopologicalSort:
    def test_empty_graph(self):
        from reagent_expansion import topological_sort
        assert topological_sort({}) == []

    def test_single_node_no_deps(self):
        from reagent_expansion import topological_sort
        result = topological_sort({1: set()})
        assert result == [1]

    def test_linear_chain(self):
        from reagent_expansion import topological_sort
        # A(1) depends on B(2) depends on C(3)
        result = topological_sort({1: {2}, 2: {3}, 3: set()})
        assert result.index(3) < result.index(2) < result.index(1)

    def test_diamond_dependency(self):
        from reagent_expansion import topological_sort
        # D(4) needed by B(2) and C(3), both needed by A(1)
        result = topological_sort({1: {2, 3}, 2: {4}, 3: {4}, 4: set()})
        assert result.count(4) == 1  # appears exactly once
        assert result.index(4) < result.index(2)
        assert result.index(4) < result.index(3)
        assert result.index(2) < result.index(1) or result.index(3) < result.index(1)

    def test_cycle_raises_value_error(self):
        from reagent_expansion import topological_sort
        with pytest.raises(ValueError, match="Zyklische"):
            topological_sort({1: {2}, 2: {1}})
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_reagent_expansion.py::TestTopologicalSort -v
```
Expected: FAIL — `topological_sort` not defined

- [ ] **Step 3: Add `topological_sort()` to `reagent_expansion.py`**

Append to `reagent_expansion.py`:

```python
def topological_sort(dep_graph: dict) -> list:
    """DFS topological sort. dep_graph[parent_id] = {child_id, ...}.

    Returns list with children (dependencies) before parents.
    Raises ValueError on cycle.
    """
    result: list = []
    visited: set = set()
    in_stack: set = set()

    def _dfs(node: int) -> None:
        if node in in_stack:
            raise ValueError(f"Zyklische Abhängigkeit bei Reagenz id={node}")
        if node in visited:
            return
        in_stack.add(node)
        for child in sorted(dep_graph.get(node, set())):
            _dfs(child)
        in_stack.discard(node)
        visited.add(node)
        result.append(node)

    for node in sorted(dep_graph):
        _dfs(node)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_reagent_expansion.py::TestTopologicalSort -v
```
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add reagent_expansion.py tests/test_reagent_expansion.py
git commit -m "feat: add topological_sort with tests"
```

---

## Task 3: `expand_reagent()` with tests

**Files:**
- Modify: `reagent_expansion.py`
- Modify: `tests/test_reagent_expansion.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_reagent_expansion.py`:

```python
def make_base_reagent(rid, name, base_unit="mL", density=None):
    r = MagicMock()
    r.id = rid
    r.name = name
    r.base_unit = base_unit
    r.density_g_ml = density
    r.cas_number = None
    r.is_composite = False
    r.components = []
    return r


def make_composite(rid, name, components_spec, base_unit="mL"):
    """components_spec: list of (child_reagent, quantity, quantity_unit, per_parent_volume_ml)"""
    r = MagicMock()
    r.id = rid
    r.name = name
    r.base_unit = base_unit
    r.density_g_ml = None
    r.cas_number = None
    r.is_composite = True
    comps = []
    for child, qty, qty_unit, ppv in components_spec:
        c = MagicMock()
        c.child = child
        c.child_reagent_id = child.id
        c.quantity = qty
        c.quantity_unit = qty_unit
        c.per_parent_volume_ml = ppv
        comps.append(c)
    r.components = comps
    return r


class TestExpandReagent:
    def test_base_reagent_goes_to_order_acc(self):
        from reagent_expansion import expand_reagent
        r = make_base_reagent(1, "NaOH")
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(r, 100.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        assert (1, "mL") in order_acc
        assert abs(order_acc[(1, "mL")]["total"] - 100.0) < 1e-9
        assert prep_acc == {}

    def test_composite_goes_to_prep_acc(self):
        from reagent_expansion import expand_reagent
        base = make_base_reagent(2, "Water")
        comp = make_composite(1, "Buffer", [(base, 90.0, "mL", 100.0)])
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(comp, 200.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        assert 1 in prep_acc
        assert abs(prep_acc[1]["total"] - 200.0) < 1e-9
        assert (2, "mL") in order_acc
        assert abs(order_acc[(2, "mL")]["total"] - 180.0) < 1e-9  # 200/100 * 90

    def test_three_level_expansion(self):
        from reagent_expansion import expand_reagent
        ammonia = make_base_reagent(3, "Ammoniak konz.", base_unit="mL", density=0.91)
        water = make_base_reagent(4, "Wasser R")
        # Ammoniaklösung: 67g ammonia + 26mL water per 93mL
        nh3_lsg = make_composite(2, "Ammoniaklösung R", [
            (ammonia, 67.0, "g", 93.0),
            (water, 26.0, "mL", 93.0),
        ])
        # Pufferlösung: 100mL nh3_lsg per 1000mL
        buffer = make_composite(1, "Pufferlösung", [(nh3_lsg, 100.0, "mL", 1000.0)])
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(buffer, 1000.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        # Buffer and nh3_lsg both in prep_acc
        assert 1 in prep_acc
        assert 2 in prep_acc
        # Base reagents in order_acc (NOT nh3_lsg)
        assert 2 not in [k[0] for k in order_acc]
        assert (3, "mL") in order_acc or any(k[0] == 3 for k in order_acc)
        assert any(k[0] == 4 for k in order_acc)

    def test_amounts_summed_for_same_base_reagent(self):
        from reagent_expansion import expand_reagent
        water = make_base_reagent(5, "Wasser R")
        comp_a = make_composite(10, "Solution A", [(water, 50.0, "mL", 100.0)])
        comp_b = make_composite(11, "Solution B", [(water, 80.0, "mL", 100.0)])
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(comp_a, 100.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        expand_reagent(comp_b, 100.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        water_key = (5, "mL")
        assert abs(order_acc[water_key]["total"] - 130.0) < 1e-9  # 50 + 80

    def test_cycle_raises_value_error(self):
        from reagent_expansion import expand_reagent
        # A contains B, B contains A (cycle)
        a = MagicMock()
        a.id = 20
        a.name = "CycleA"
        a.base_unit = "mL"
        a.density_g_ml = None
        a.is_composite = True
        b = MagicMock()
        b.id = 21
        b.name = "CycleB"
        b.base_unit = "mL"
        b.density_g_ml = None
        b.is_composite = True
        comp_ab = MagicMock()
        comp_ab.child = b
        comp_ab.child_reagent_id = 21
        comp_ab.quantity = 50.0
        comp_ab.quantity_unit = "mL"
        comp_ab.per_parent_volume_ml = 100.0
        a.components = [comp_ab]
        comp_ba = MagicMock()
        comp_ba.child = a
        comp_ba.child_reagent_id = 20
        comp_ba.quantity = 50.0
        comp_ba.quantity_unit = "mL"
        comp_ba.per_parent_volume_ml = 100.0
        b.components = [comp_ba]
        with pytest.raises(ValueError, match="Zyklische"):
            expand_reagent(a, 100.0, "mL", {}, {}, {}, [])

    def test_missing_per_parent_volume_ml_skipped(self):
        from reagent_expansion import expand_reagent
        base = make_base_reagent(30, "SomeBase")
        comp = make_composite(31, "SomeComp", [(base, 50.0, "mL", None)])
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(comp, 100.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        assert order_acc == {}  # skipped, no ZeroDivisionError
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_reagent_expansion.py::TestExpandReagent -v
```
Expected: FAIL — `expand_reagent` not defined

- [ ] **Step 3: Add `expand_reagent()` to `reagent_expansion.py`**

Append to `reagent_expansion.py`:

```python
def expand_reagent(
    reagent,
    amount: float,
    unit: str,
    order_acc: dict,
    prep_acc: dict,
    dep_graph: dict,
    warnings: list,
    visiting: frozenset | None = None,
    caller_name: str | None = None,
) -> None:
    """Recursively expand reagent into order_acc (base) and prep_acc (composites).

    order_acc key: (reagent_id, unit) → {name, cas, total, unit, for_composites, warning}
    prep_acc key: reagent_id → {name, unit, total, reagent}
    dep_graph: {parent_id: {child_id, ...}} — used for topological sort of prep list.
    visiting: frozenset of reagent_ids on the current path (cycle detection).
    caller_name: name of the immediate parent composite (for for_composites tracking).
    """
    if visiting is None:
        visiting = frozenset()

    if reagent.id in visiting:
        raise ValueError(
            f"Zyklische Abhängigkeit bei Reagenz '{reagent.name}' (id={reagent.id})"
        )

    if not reagent.is_composite:
        key = (reagent.id, unit)
        if key not in order_acc:
            order_acc[key] = {
                "name": reagent.name,
                "cas": reagent.cas_number or "–",
                "total": 0.0,
                "unit": unit,
                "for_composites": set(),
            }
        order_acc[key]["total"] += amount
        if caller_name:
            order_acc[key]["for_composites"].add(caller_name)
        return

    # Composite
    if reagent.id not in prep_acc:
        prep_acc[reagent.id] = {
            "name": reagent.name,
            "unit": unit,
            "total": 0.0,
            "reagent": reagent,
        }
    prep_acc[reagent.id]["total"] += amount
    dep_graph.setdefault(reagent.id, set())

    new_visiting = visiting | {reagent.id}
    for comp in reagent.components:
        if not comp.child or not comp.per_parent_volume_ml or comp.per_parent_volume_ml <= 0:
            continue
        comp_amount = amount / comp.per_parent_volume_ml * comp.quantity
        comp_amount, comp_unit, warning = convert_to_base_unit(
            comp.child, comp_amount, comp.quantity_unit
        )
        if warning:
            warnings.append(warning)
        if comp.child.is_composite:
            dep_graph[reagent.id].add(comp.child_reagent_id)
        expand_reagent(
            comp.child, comp_amount, comp_unit,
            order_acc, prep_acc, dep_graph, warnings,
            new_visiting, caller_name=reagent.name,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_reagent_expansion.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add reagent_expansion.py tests/test_reagent_expansion.py
git commit -m "feat: add expand_reagent with recursive composite expansion and tests"
```

---

## Task 4: `build_expansion()` driver with integration test

**Files:**
- Modify: `reagent_expansion.py`
- Modify: `tests/test_reagent_expansion.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_reagent_expansion.py`:

```python
class TestBuildExpansion:
    def test_build_expansion_with_nested_composite(self):
        """build_expansion returns order_items (base only) and prep_items (composites)."""
        from reagent_expansion import build_expansion

        ammonia = make_base_reagent(100, "Ammoniak konz.", base_unit="mL", density=0.91)
        water = make_base_reagent(101, "Wasser R")
        nh3_lsg = make_composite(200, "Ammoniaklösung R", [
            (ammonia, 67.0, "g", 93.0),
            (water, 26.0, "mL", 93.0),
        ])
        buffer = make_composite(201, "Pufferlösung pH 10", [(nh3_lsg, 100.0, "mL", 1000.0)])

        mr = MagicMock()
        mr.reagent = buffer
        mr.amount_per_determination = 100.0
        mr.amount_per_blind = 0.0
        mr.amount_unit = "mL"

        method = MagicMock()
        method.blind_required = False
        method.b_blind_determinations = 0
        method.reagent_usages = [mr]

        analysis = MagicMock()
        analysis.k_determinations = 1
        analysis.method = method
        analysis.block = None

        sample = MagicMock()
        sample.is_buffer = False
        batch = MagicMock()
        batch.analysis = analysis
        batch.samples = [sample, sample, sample]  # n=3
        batch.safety_factor = 1.0

        result = build_expansion([batch])

        # Base reagents in order_items, not intermediate composite
        order_names = [i["name"] for i in result["order_items"]]
        assert "Ammoniak konz." in order_names
        assert "Wasser R" in order_names
        assert "Ammoniaklösung R" not in order_names

        # Both composites in prep_items
        assert 200 in result["prep_items"]
        assert 201 in result["prep_items"]

        # Topo sort: nh3_lsg (200) before buffer (201)
        prep_ids = result["sorted_prep_ids"]
        assert prep_ids.index(200) < prep_ids.index(201)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_reagent_expansion.py::TestBuildExpansion -v
```
Expected: FAIL — `build_expansion` not defined

- [ ] **Step 3: Add `build_expansion()` to `reagent_expansion.py`**

Append to `reagent_expansion.py`:

```python
def build_expansion(batches) -> dict:
    """Drive expand_reagent for all MethodReagents across all batches.

    Returns dict with:
      order_items: list of {name, cas, total, unit, for_reagents} sorted by name
      prep_items: dict[reagent_id] → {name, unit, total, reagent}
      sorted_prep_ids: topologically sorted reagent_id list (deps first)
      block_assignments: dict[reagent_id] → (block_id, block_name) for direct composites
      warnings: list of str
    """
    order_acc: dict = {}
    prep_acc: dict = {}
    dep_graph: dict = {}
    warnings: list = []
    block_assignments: dict = {}

    for batch in batches:
        analysis = batch.analysis
        method = analysis.method
        if not method:
            continue
        block = getattr(analysis, "block", None)
        block_info = (block.id, f"{block.code} – {block.name}") if block else None
        k = analysis.k_determinations or 1
        b = method.b_blind_determinations if method.blind_required else 0
        n = sum(1 for s in batch.samples if not s.is_buffer)
        safety = getattr(batch, "safety_factor", 1.2) or 1.2

        for mr in method.reagent_usages:
            reagent = mr.reagent
            if not reagent:
                continue
            total_amount = (
                n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
            )
            amount, unit, warning = convert_to_base_unit(reagent, total_amount, mr.amount_unit)
            if warning:
                warnings.append(warning)
            if reagent.is_composite and block_info and reagent.id not in block_assignments:
                block_assignments[reagent.id] = block_info
            expand_reagent(reagent, amount, unit, order_acc, prep_acc, dep_graph, warnings)

    order_items = sorted(
        [
            {
                "name": v["name"],
                "cas": v["cas"],
                "total": v["total"],
                "unit": v["unit"],
                "for_reagents": sorted(v["for_composites"]),
            }
            for v in order_acc.values()
        ],
        key=lambda x: x["name"],
    )
    sorted_prep_ids = topological_sort(dep_graph)

    return {
        "order_items": order_items,
        "prep_items": prep_acc,
        "sorted_prep_ids": sorted_prep_ids,
        "block_assignments": block_assignments,
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run all unit tests to verify they pass**

```
pytest tests/test_reagent_expansion.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add reagent_expansion.py tests/test_reagent_expansion.py
git commit -m "feat: add build_expansion driver with tests"
```

---

## Task 5: Replace `reports_order_list()` in `app.py`

**Files:**
- Modify: `app.py` (lines 1949–2004)
- Modify: `tests/test_reagent_demand.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_reagent_demand.py`:

```python
def test_order_list_expands_nested_composites(client, db):
    """Integration: /reports/reagents/order-list expands 3-level composites correctly."""
    from models import (
        Block, Substance, Analysis, Method, Semester, SampleBatch,
        Reagent, MethodReagent, ReagentComponent,
    )
    with client.application.app_context():
        Semester.query.update({"is_active": False})
        db.session.flush()
        sem = Semester(code="OL01", name="Order List Nested Test", is_active=True)
        block = Block(code="OL", name="Order List Block", max_days=4)
        substance = Substance(name="OL Substance", molar_mass_gmol=100.0)
        db.session.add_all([sem, block, substance])
        db.session.flush()

        analysis = Analysis(
            block_id=block.id, code="OL1", ordinal=90, name="OL Analysis",
            substance_id=substance.id, calculation_mode="assay_mass_based",
            k_determinations=1, result_unit="%", result_label="Gehalt",
            g_ab_min_pct=98.0, g_ab_max_pct=102.0, e_ab_g=0.5,
        )
        db.session.add(analysis)
        db.session.flush()

        # 3-level: ammonia (base) → ammoniak_lsg (composite) → buffer (composite)
        ammonia = Reagent(name="OL Ammoniak konz.", is_composite=False, base_unit="mL", density_g_ml=0.91)
        water = Reagent(name="OL Wasser R", is_composite=False, base_unit="mL")
        nh3_lsg = Reagent(name="OL Ammoniaklösung R", is_composite=True, base_unit="mL")
        buffer = Reagent(name="OL Pufferlösung R", is_composite=True, base_unit="mL")
        db.session.add_all([ammonia, water, nh3_lsg, buffer])
        db.session.flush()

        # nh3_lsg: 67g ammonia + 26mL water per 93mL
        db.session.add_all([
            ReagentComponent(parent_reagent_id=nh3_lsg.id, child_reagent_id=ammonia.id,
                             quantity=67.0, quantity_unit="g", per_parent_volume_ml=93.0),
            ReagentComponent(parent_reagent_id=nh3_lsg.id, child_reagent_id=water.id,
                             quantity=26.0, quantity_unit="mL", per_parent_volume_ml=93.0),
            # buffer: 100mL nh3_lsg per 1000mL
            ReagentComponent(parent_reagent_id=buffer.id, child_reagent_id=nh3_lsg.id,
                             quantity=100.0, quantity_unit="mL", per_parent_volume_ml=1000.0),
        ])

        method = Method(
            analysis_id=analysis.id, method_type="direct",
            blind_required=False, b_blind_determinations=0,
            v_solution_ml=100.0, aliquot_enabled=False,
        )
        db.session.add(method)
        db.session.flush()

        usage = MethodReagent(
            method_id=method.id, reagent_id=buffer.id,
            amount_per_determination=100.0, amount_per_blind=0.0,
            amount_unit="mL", is_titrant=False,
        )
        db.session.add(usage)
        batch = SampleBatch(
            analysis_id=analysis.id, semester_id=sem.id,
            total_samples_prepared=1, titer=1.0, safety_factor=1.0,
        )
        db.session.add(batch)
        db.session.commit()

        # NOTE: No Sample rows added → batch.samples is empty → n=0 → all totals are 0.
        # The test checks name presence only (items are inserted into order_acc even with
        # amount=0 because expand_reagent runs regardless). This is a structural smoke test.
        resp = client.get("/reports/reagents/order-list")
        assert resp.status_code == 200
        text = resp.data.decode()
        # Base reagents appear (name present in table)
        assert "OL Ammoniak konz." in text
        assert "OL Wasser R" in text
        # Intermediate composite does NOT appear in order list
        assert "OL Ammoniaklösung R" not in text
        # Top composite does NOT appear in order list
        assert "OL Pufferlösung R" not in text
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_reagent_demand.py::test_order_list_expands_nested_composites -v
```
Expected: FAIL (intermediate composite currently appears or base reagents missing)

- [ ] **Step 3: Replace `reports_order_list()` body in `app.py`**

Replace lines 1949–2004 in `app.py` with:

```python
    @app.route("/reports/reagents/order-list")
    def reports_order_list():
        sem = active_semester()
        if not sem:
            return render_template(
                "reports/order_list.html", semester=None, items=[], generated=None, warnings=[]
            )
        from reagent_expansion import build_expansion
        from datetime import date as _date

        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        result = build_expansion(batches)
        return render_template(
            "reports/order_list.html",
            semester=sem,
            items=result["order_items"],
            warnings=result["warnings"],
            generated=_date.today().isoformat(),
        )
```

- [ ] **Step 4: Run all reagent tests to verify they pass**

```
pytest tests/test_reagent_demand.py tests/test_reagent_expansion.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_reagent_demand.py
git commit -m "feat: replace order list with recursive expansion via build_expansion"
```

---

## Task 6: Replace `reports_prep_list()` in `app.py`

**Files:**
- Modify: `app.py` (lines 2006–2071)
- Modify: `tests/test_reagent_demand.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_reagent_demand.py` (reuse the OL01 database setup from Task 5 if possible, otherwise add a new test using the same pattern with code "PL01"):

```python
def test_prep_list_includes_intermediate_composites(client, db):
    """Integration: /reports/reagents/prep-list shows all composites in topo order."""
    from models import (
        Block, Substance, Analysis, Method, Semester, SampleBatch,
        Reagent, MethodReagent, ReagentComponent,
    )
    with client.application.app_context():
        Semester.query.update({"is_active": False})
        db.session.flush()
        sem = Semester(code="PL01", name="Prep List Nested Test", is_active=True)
        block = Block(code="PL", name="Prep List Block", max_days=4)
        substance = Substance(name="PL Substance", molar_mass_gmol=100.0)
        db.session.add_all([sem, block, substance])
        db.session.flush()
        analysis = Analysis(
            block_id=block.id, code="PL1", ordinal=89, name="PL Analysis",
            substance_id=substance.id, calculation_mode="assay_mass_based",
            k_determinations=1, result_unit="%", result_label="Gehalt",
            g_ab_min_pct=98.0, g_ab_max_pct=102.0, e_ab_g=0.5,
        )
        db.session.add(analysis)
        db.session.flush()
        water = Reagent(name="PL Wasser R", is_composite=False, base_unit="mL")
        nh3_lsg = Reagent(name="PL Ammoniaklösung R", is_composite=True, base_unit="mL")
        buffer = Reagent(name="PL Pufferlösung R", is_composite=True, base_unit="mL")
        db.session.add_all([water, nh3_lsg, buffer])
        db.session.flush()
        db.session.add_all([
            ReagentComponent(parent_reagent_id=nh3_lsg.id, child_reagent_id=water.id,
                             quantity=26.0, quantity_unit="mL", per_parent_volume_ml=93.0),
            ReagentComponent(parent_reagent_id=buffer.id, child_reagent_id=nh3_lsg.id,
                             quantity=100.0, quantity_unit="mL", per_parent_volume_ml=1000.0),
        ])
        method = Method(
            analysis_id=analysis.id, method_type="direct",
            blind_required=False, b_blind_determinations=0,
            v_solution_ml=100.0, aliquot_enabled=False,
        )
        db.session.add(method)
        db.session.flush()
        usage = MethodReagent(
            method_id=method.id, reagent_id=buffer.id,
            amount_per_determination=100.0, amount_per_blind=0.0,
            amount_unit="mL", is_titrant=False,
        )
        db.session.add(usage)
        db.session.add(SampleBatch(
            analysis_id=analysis.id, semester_id=sem.id,
            total_samples_prepared=1, titer=1.0, safety_factor=1.0,
        ))
        db.session.commit()

        resp = client.get("/reports/reagents/prep-list")
        assert resp.status_code == 200
        text = resp.data.decode()
        # Both composites appear
        assert "PL Ammoniaklösung R" in text
        assert "PL Pufferlösung R" in text
        # Intermediate composite appears BEFORE the top-level composite (topo order)
        assert text.index("PL Ammoniaklösung R") < text.index("PL Pufferlösung R")
        # Intermediate composite is in "Vorabherstellungen" section
        assert "Vorabherstellungen" in text
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_reagent_demand.py::test_prep_list_includes_intermediate_composites -v
```
Expected: FAIL — intermediate composite missing

- [ ] **Step 3: Replace `reports_prep_list()` body in `app.py`**

Replace lines 2006–2071 in `app.py` with:

```python
    @app.route("/reports/reagents/prep-list")
    def reports_prep_list():
        sem = active_semester()
        if not sem:
            return render_template("reports/prep_list.html", semester=None, blocks=[], generated=None)
        from reagent_expansion import build_expansion
        from datetime import date as _date
        from collections import defaultdict

        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        result = build_expansion(batches)

        prep_items = result["prep_items"]
        sorted_prep_ids = result["sorted_prep_ids"]
        block_assignments = result["block_assignments"]

        # Group by block. Intermediate composites (not in block_assignments) → None key.
        block_reagents: dict = defaultdict(list)
        for rg_id in sorted_prep_ids:
            if rg_id not in prep_items:
                continue
            item = prep_items[rg_id]
            reagent = item["reagent"]
            total = item["total"]
            components = []
            for comp in reagent.components:
                if comp.child and comp.per_parent_volume_ml and comp.per_parent_volume_ml > 0:
                    comp_total = round(total / comp.per_parent_volume_ml * comp.quantity, 2)
                    components.append({
                        "name": comp.child.name,
                        "amount": comp_total,
                        "unit": canonical_unit_label(comp.quantity_unit),
                    })
            block_key = block_assignments.get(rg_id)  # None for intermediate composites
            block_reagents[block_key].append({
                "name": item["name"],
                "total": round(total, 1),
                "unit": item["unit"],
                "components": components,
                "prep_notes": reagent.notes or "",
            })

        # Build blocks list: "Vorabherstellungen" (None key) first, then sorted by block id.
        blocks = []
        if None in block_reagents:
            blocks.append({
                "id": None,
                "name": "Vorabherstellungen",
                "reagents": block_reagents[None],
            })
        for block_key, reagents in sorted(
            ((k, v) for k, v in block_reagents.items() if k is not None),
            key=lambda x: x[0][0],
        ):
            blocks.append({"id": block_key[0], "name": block_key[1], "reagents": reagents})

        return render_template(
            "reports/prep_list.html",
            semester=sem,
            blocks=blocks,
            generated=_date.today().isoformat(),
        )
```

- [ ] **Step 4: Run all reagent tests to verify they pass**

```
pytest tests/test_reagent_demand.py tests/test_reagent_expansion.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_reagent_demand.py
git commit -m "feat: replace prep list with recursive expansion, add Vorabherstellungen group"
```

---

## Task 7: Add warnings display to `order_list.html`

**Files:**
- Modify: `templates/reports/order_list.html`

- [ ] **Step 1: Write failing test**

Add to `tests/test_reagent_demand.py`:

```python
def test_order_list_renders_without_error(client, db):
    """Smoke test: /reports/reagents/order-list renders with no active semester."""
    # Deactivate all semesters to trigger the no-semester path (warnings=[] required)
    from models import Semester
    with client.application.app_context():
        Semester.query.update({"is_active": False})
        db.session.commit()
    resp = client.get("/reports/reagents/order-list")
    assert resp.status_code == 200
    # "warnings" variable must be defined in template (no Jinja UndefinedError)
    assert b"Kein aktives Semester" in resp.data
```

- [ ] **Step 2: Run test to verify it fails (or passes — see note)**

```
pytest tests/test_reagent_demand.py::test_order_list_renders_without_error -v
```
Note: This test may PASS already if the current endpoint doesn't crash. That is fine — it will catch regressions after the template edit.

- [ ] **Step 3: Add warnings section to the template**

In `templates/reports/order_list.html`, insert the warnings block at **line 23** — inside the `{% else %}` block (line 18), immediately after the `<p class="text-body-secondary...">` paragraph (currently ending at line 22). The insertion is INSIDE `{% else %}`, NOT above `{% if not semester %}`.

Replace line 22–23 (the closing `</p>` line and the start of the card) with:

```html
</p>

{% if warnings %}
<div class="alert alert-warning mt-2 mb-3">
  <strong><i class="bi bi-exclamation-triangle"></i> Einheiten-Hinweise:</strong>
  <ul class="mb-0 mt-1 small">
    {% for w in warnings %}<li>{{ w }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

<div class="card">
```

The `{% if warnings %}` block is safe to add here because:
- When semester exists: `warnings` is always passed (either a non-empty list or `[]`).
- When no semester: the `{% else %}` block is not reached, so `warnings` is never evaluated.

Verify `warnings=[]` is passed in the no-semester path of `reports_order_list()` (done in Task 5).

- [ ] **Step 4: Run all tests to verify they pass**

```
pytest tests/test_reagent_demand.py tests/test_reagent_expansion.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add templates/reports/order_list.html tests/test_reagent_demand.py
git commit -m "feat: show unit-conversion warnings in order list"
```

---

## Final Check

- [ ] **Run full test suite**

```
pytest -v
```
Expected: All existing tests still PASS, all new tests PASS

- [ ] **Manual smoke test**
  1. Start the app: `python app.py` (or `flask run`)
  2. Open `/reports/reagents/order-list` — verify base reagents appear, not composites
  3. Open `/reports/reagents/prep-list` — verify "Vorabherstellungen" section appears with intermediate composites listed before block-specific ones

- [ ] **Final commit if clean**

```bash
git commit -m "chore: verify all tests pass after recursive reagent expansion"
```
(Skip if no changes — tests already committed.)
