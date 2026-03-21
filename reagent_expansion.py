# reagent_expansion.py
"""Recursive reagent requirement expansion for order list and prep list reports."""
from __future__ import annotations

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
        if reagent.density_g_ml is None:
            return amount, from_unit, f"Dichte fehlt für '{reagent.name}' (g→mL)"
        ml = amount * _MASS_TO_G[from_unit] / reagent.density_g_ml
        return ml / _VOL_TO_ML[target], target, None

    if fd == AMOUNT_UNIT_VOLUME and td == AMOUNT_UNIT_MASS:
        if reagent.density_g_ml is None:
            return amount, from_unit, f"Dichte fehlt für '{reagent.name}' (mL→g)"
        g = amount * _VOL_TO_ML[from_unit] * reagent.density_g_ml
        return g / _MASS_TO_G[target], target, None

    return (
        amount,
        from_unit,
        f"Einheitenkonvertierung nicht möglich: {from_unit}→{target} für '{reagent.name}'",
    )


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

    order_acc key: (reagent_id, unit) → {name, cas, total, unit, for_composites}
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
