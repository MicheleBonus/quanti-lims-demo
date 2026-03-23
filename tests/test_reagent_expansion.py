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


class TestExpandReagent:
    def test_base_reagent_goes_to_order_acc(self):
        from reagent_expansion import expand_reagent
        r = make_base_reagent(1, "NaOH")
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(r, 100.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        assert (1, "mL") in order_acc
        assert abs(order_acc[(1, "mL")]["total"] - 100.0) < 1e-9
        assert (None, None) in order_acc[(1, "mL")]["sources"]
        assert prep_acc == {}

    def test_composite_goes_to_prep_acc(self):
        from reagent_expansion import expand_reagent
        base = make_base_reagent(2, "Water")
        comp = make_composite(1, "Buffer", [(base, 90.0, "mL", 100.0)])
        order_acc, prep_acc, dep_graph, warnings = {}, {}, {}, []
        expand_reagent(comp, 200.0, "mL", order_acc, prep_acc, dep_graph, warnings)
        assert 1 in prep_acc
        assert None in prep_acc[1]  # no block_info passed → None key
        assert abs(prep_acc[1][None]["total"] - 200.0) < 1e-9
        assert (2, "mL") in order_acc
        assert abs(order_acc[(2, "mL")]["total"] - 180.0) < 1e-9  # 200/100 * 90
        assert (None, "Buffer") in order_acc[(2, "mL")]["sources"]

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
        assert None in prep_acc[1]
        assert 2 in prep_acc
        assert None in prep_acc[2]
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
        analysis.code = "BUF1"
        analysis.name = "Buffer Test"
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

        # Both composites in prep_items (analysis.block = None → None key)
        assert 200 in result["prep_items"]
        assert None in result["prep_items"][200]
        assert 201 in result["prep_items"]
        assert None in result["prep_items"][201]

        # Topo sort: nh3_lsg (200) before buffer (201)
        prep_ids = result["sorted_prep_ids"]
        assert prep_ids.index(200) < prep_ids.index(201)

        # Sources breakdown: base reagents have analysis + via info
        ammonia_item = next(k for k in result["order_items"] if k["name"] == "Ammoniak konz.")
        assert len(ammonia_item["sources"]) == 1  # 1 unique analysis
        src = ammonia_item["sources"][0]
        assert src["analysis"] == "BUF1 – Buffer Test"
        assert len(src["parts"]) == 1
        assert src["parts"][0]["via"] == "Ammoniaklösung R"

    def test_shared_composite_across_two_blocks(self):
        """Composite used by two blocks appears separately in each block's prep entry."""
        from reagent_expansion import build_expansion

        water = make_base_reagent(300, "Wasser R")
        sol = make_composite(400, "Stammlösung", [(water, 50.0, "mL", 100.0)])

        def make_mr(reagent, amount):
            mr = MagicMock()
            mr.reagent = reagent
            mr.amount_per_determination = amount
            mr.amount_per_blind = 0.0
            mr.amount_unit = "mL"
            return mr

        def make_block(bid, code, name):
            b = MagicMock()
            b.id = bid
            b.code = code
            b.name = name
            return b

        def make_batch(sol, amount, block):
            method = MagicMock()
            method.blind_required = False
            method.b_blind_determinations = 0
            method.reagent_usages = [make_mr(sol, amount)]
            analysis = MagicMock()
            analysis.code = block.code
            analysis.name = block.name
            analysis.k_determinations = 1
            analysis.method = method
            analysis.block = block
            sample = MagicMock()
            sample.is_buffer = False
            batch = MagicMock()
            batch.analysis = analysis
            batch.samples = [sample]  # n=1
            batch.safety_factor = 1.0
            return batch

        block_a = make_block(1, "A", "Block A")
        block_b = make_block(2, "B", "Block B")
        batch_a = make_batch(sol, 200.0, block_a)  # needs 200mL sol
        batch_b = make_batch(sol, 300.0, block_b)  # needs 300mL sol

        result = build_expansion([batch_a, batch_b])
        prep = result["prep_items"]

        # Composite appears in prep_items
        assert 400 in prep

        # Two separate block entries
        block_info_a = (1, "A – Block A")
        block_info_b = (2, "B – Block B")
        assert block_info_a in prep[400]
        assert block_info_b in prep[400]

        # Amounts are independent, not summed together
        assert abs(prep[400][block_info_a]["total"] - 200.0) < 1e-9
        assert abs(prep[400][block_info_b]["total"] - 300.0) < 1e-9


class TestSuggestFlaskSizeMl:
    def test_exact_match(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(500.0) == 500.0

    def test_rounds_up_to_next_size(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(501.0) == 1000.0

    def test_small_value(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(30.0) == 50.0

    def test_over_max_returns_2000(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(2001.0) == 2000.0

    def test_zero_returns_50(self):
        from reagent_expansion import _suggest_flask_size_ml
        assert _suggest_flask_size_ml(0.0) == 50.0
