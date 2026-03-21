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
