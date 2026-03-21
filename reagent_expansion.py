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
