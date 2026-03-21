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
