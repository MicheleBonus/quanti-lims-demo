# reagent_expansion.py
"""Recursive reagent requirement expansion for order list and prep list reports."""
from __future__ import annotations

from models import AMOUNT_UNIT_TYPES, AMOUNT_UNIT_MASS, AMOUNT_UNIT_VOLUME

_MASS_TO_G = {"mg": 0.001, "g": 1.0, "kg": 1000.0}
_VOL_TO_ML = {"µL": 0.001, "mL": 1.0, "L": 1000.0}

FLASK_SIZES_ML = [50, 100, 250, 500, 1000, 2000]


def _suggest_flask_size_ml(total_ml: float) -> float:
    """Return numeric mL value of the smallest standard flask >= total_ml.

    Returns 2000.0 if total_ml exceeds the largest size (caller uses
    count = ceil(total_ml / 2000) to determine how many flasks are needed).
    """
    for s in FLASK_SIZES_ML:
        if s >= total_ml:
            return float(s)
    return 2000.0


def _build_sources(raw: dict) -> list:
    """Group raw sources dict {(analysis_info, via_label): amount} by analysis.

    Returns list of:
        {analysis: str, total: float, parts: [{amount: float, via: str|None}]}
    sorted by analysis name.
    """
    from collections import defaultdict
    by_analysis: dict = defaultdict(list)
    for (analysis_info, via_label), amount in raw.items():
        by_analysis[analysis_info or ""].append({"amount": amount, "via": via_label})

    result = []
    for analysis_name in sorted(by_analysis):
        parts = sorted(
            by_analysis[analysis_name],
            key=lambda p: (p["via"] is not None, p["via"] or ""),
        )
        result.append({
            "analysis": analysis_name or "–",
            "total": sum(p["amount"] for p in parts),
            "parts": parts,
        })
    return result


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
    composite_contrib_acc: dict | None = None,
    top_composite_id: int | None = None,
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
        if composite_contrib_acc is not None and top_composite_id is not None:
            ckey = (reagent.id, unit, top_composite_id, block_info)
            composite_contrib_acc[ckey] = composite_contrib_acc.get(ckey, 0.0) + amount
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
            composite_contrib_acc=composite_contrib_acc,
            top_composite_id=top_composite_id if top_composite_id is not None else reagent.id,
        )


def build_expansion(batches, flask_configs=None) -> dict:
    # flask_configs: dict[(reagent_id, block_id_or_None) -> flask_size_ml] | None
    # When None (default), no flask correction is applied (backward-compatible).
    # Flask correction post-processing is implemented in Task 4 (provenance tracking).
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
    composite_contrib_acc: dict = {}

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
                           block_info=block_info, analysis_info=analysis_info,
                           composite_contrib_acc=composite_contrib_acc if flask_configs else None)

            # Track practical totals for titrants (burette fill size overrides theoretical)
            if mr.is_titrant:
                pract_key = (reagent.id, unit)
                if pract_key in order_acc:
                    order_acc[pract_key]["is_titrant"] = True
                if mr.practical_amount_per_determination is not None:
                    practical_raw = n * mr.practical_amount_per_determination * (k + b) * safety
                    pract_converted, _punit, pract_warn = convert_to_base_unit(
                        reagent, practical_raw, mr.amount_unit
                    )
                    if pract_warn:
                        warnings.append(pract_warn)
                    pract_key2 = (reagent.id, _punit)
                    if pract_key2 in order_acc:
                        entry = order_acc[pract_key2]
                        entry["practical_total"] = round(
                            entry.get("practical_total", 0.0) + pract_converted, 4
                        )
                        entry.setdefault("burette_amount", mr.practical_amount_per_determination)
                        entry.setdefault("burette_unit", mr.amount_unit)

    # Flask correction: scale base-reagent contributions via composites
    if flask_configs and composite_contrib_acc:
        from math import ceil
        for (base_id, unit, composite_id, blk_info) in composite_contrib_acc:
            db_block_id = blk_info[0] if blk_info is not None else None
            flask_size = flask_configs.get((composite_id, db_block_id))
            if flask_size is None:
                continue
            block_data = (prep_acc.get(composite_id) or {}).get(blk_info)
            if block_data is None:
                continue
            theoretical = block_data["total"]
            if theoretical <= 0:
                continue
            count = ceil(theoretical / flask_size)
            effective = flask_size * count
            scale = effective / theoretical  # always >= 1.0
            contrib = composite_contrib_acc[(base_id, unit, composite_id, blk_info)]
            order_acc[(base_id, unit)]["total"] += contrib * (scale - 1.0)

    order_items = sorted(
        [
            {
                "name": v["name"],
                "cas": v["cas"],
                "total": v["total"],
                "unit": v["unit"],
                "sources": _build_sources(v["sources"]),
                "is_titrant": v.get("is_titrant", False),
                "practical_total": v.get("practical_total"),
                "burette_amount": v.get("burette_amount"),
                "burette_unit": v.get("burette_unit"),
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
