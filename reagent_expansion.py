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
    block_info: tuple | None = None,
    analysis_info: str | None = None,
) -> None:
    """Recursively expand reagent into order_acc (base) and prep_acc (composites).

    order_acc key: (reagent_id, unit) → {name, cas, total, unit, sources}
    prep_acc key: reagent_id → {block_info: {name, unit, total, reagent}}
    dep_graph: {parent_id: {child_id, ...}} — used for topological sort of prep list.
    visiting: frozenset of reagent_ids on the current path (cycle detection).
    caller_name: name of the immediate parent composite (for for_composites tracking).
    block_info: (block_id, block_label) tuple from the root MethodReagent, or None.
    analysis_info: "code – name" string of the root analysis (for sources breakdown).
    sources key: (analysis_info, via_label) → float, where via_label is caller_name or None.
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
                "sources": {},
            }
        order_acc[key]["total"] += amount
        src_key = (analysis_info, caller_name)
        order_acc[key]["sources"].setdefault(src_key, 0.0)
        order_acc[key]["sources"][src_key] += amount
        return

    if reagent.id not in prep_acc:
        prep_acc[reagent.id] = {}
    if block_info not in prep_acc[reagent.id]:
        prep_acc[reagent.id][block_info] = {
            "name": reagent.name,
            "unit": unit,
            "total": 0.0,
            "reagent": reagent,
        }
    prep_acc[reagent.id][block_info]["total"] += amount
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
            new_visiting, caller_name=reagent.name, block_info=block_info,
            analysis_info=analysis_info,
        )


def build_expansion(batches) -> dict:
    """Drive expand_reagent for all MethodReagents across all batches.

    Returns dict with:
      order_items: list of {name, cas, total, unit, for_reagents} sorted by name
      prep_items: dict[reagent_id] → {block_info: {name, unit, total, reagent}}
      sorted_prep_ids: topologically sorted reagent_id list (deps first)
      warnings: list of str
    """
    order_acc: dict = {}
    prep_acc: dict = {}
    dep_graph: dict = {}
    warnings: list = []

    for batch in batches:
        analysis = batch.analysis
        method = analysis.method
        if not method:
            continue
        block = getattr(analysis, "block", None)
        # block_info is (block.id, display_label) — int id used for sorting in app.py
        block_info = (block.id, f"{block.code} – {block.name}") if block else None
        analysis_info = f"{analysis.code} – {analysis.name}" if (analysis.code and analysis.name) else None
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
            expand_reagent(reagent, amount, unit, order_acc, prep_acc, dep_graph, warnings,
                           block_info=block_info, analysis_info=analysis_info)

    order_items = sorted(
        [
            {
                "name": v["name"],
                "cas": v["cas"],
                "total": v["total"],
                "unit": v["unit"],
                "sources": [
                    {"analysis": k[0], "amount": amt, "via": k[1]}
                    for k, amt in sorted(
                        v["sources"].items(),
                        key=lambda x: (x[0][0] or "", x[0][1] or ""),
                    )
                ],
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
        "warnings": warnings,
    }
