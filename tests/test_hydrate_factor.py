"""Tests for hydrate correction factor in MassBasedEvaluator."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample(m_s, m_ges, p_effective, molar_mass, anhydrous_molar_mass=None,
                 reported_molar_mass=None, reported_stoich=None):
    """Build minimal mock sample chain for g_wahr tests."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass
    substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass

    analysis = MagicMock()
    analysis.substance = substance
    analysis.e_ab_g = None
    analysis.method = None
    analysis.reported_molar_mass_gmol = reported_molar_mass
    analysis.reported_stoichiometry = reported_stoich

    batch = MagicMock()
    batch.p_effective = p_effective
    batch.analysis = analysis

    sample = MagicMock()
    sample.m_s_actual_g = m_s
    sample.m_ges_actual_g = m_ges
    sample.batch = batch
    return sample


def test_g_wahr_no_hydrate_factor():
    """Without anhydrous_molar_mass, result is unchanged."""
    sample = _make_sample(2.0, 4.0, 100.0, 282.1, anhydrous_molar_mass=None)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    assert abs(result - 50.0) < 0.001


def test_g_wahr_with_hydrate_factor():
    """Li citrate tetrahydrate: factor = 210.1/282.1 ≈ 0.7448."""
    # Raw g_wahr = (2.0/4.0)*100 = 50.0 %
    # With factor: 50.0 * (210.1/282.1) = 37.24 %
    sample = _make_sample(2.0, 4.0, 100.0, 282.1, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 50.0 * (210.1 / 282.1)
    assert abs(result - expected) < 0.001


def test_g_wahr_hydrate_factor_with_purity():
    """Hydrate factor is applied after p_effective."""
    sample = _make_sample(2.0, 4.0, 99.5, 282.1, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = (2.0 / 4.0) * 99.5 * (210.1 / 282.1)
    assert abs(result - expected) < 0.001


def test_g_wahr_zero_molar_mass_guard():
    """Guard against division by zero when molar_mass_gmol is 0."""
    sample = _make_sample(2.0, 4.0, 100.0, 0.0, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    # Should fall back to factor=1.0 (no hydrate correction)
    assert abs(result - 50.0) < 0.001


def test_g_wahr_none_molar_mass_guard():
    """Guard against None molar_mass_gmol."""
    sample = _make_sample(2.0, 4.0, 100.0, None, anhydrous_molar_mass=210.1)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    assert abs(result - 50.0) < 0.001


def test_g_wahr_reported_molar_mass_replaces_hydrate_correction():
    """reported_molar_mass_gmol takes priority; hydrate correction is skipped.

    300 mg Na2HPO4·2H2O (MW=177.99), anhydrous MW=141.96, p=100%.
    Reported: P (MW=30.974, stoich=1.0).
    Expected g_wahr = 100% * (1.0 * 30.974) / 177.99 = 17.40%
    (NOT the hydrate-corrected 79.76%)
    """
    sample = _make_sample(0.3, 0.3, 100.0, 177.99, anhydrous_molar_mass=141.96,
                          reported_molar_mass=30.974, reported_stoich=1.0)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 100.0 * (1.0 * 30.974) / 177.99
    assert abs(result - expected) < 0.001


def test_g_wahr_reported_stoichiometry_none_defaults_to_1():
    """reported_stoichiometry=None is treated as 1.0."""
    sample = _make_sample(0.3, 0.3, 100.0, 177.99, anhydrous_molar_mass=None,
                          reported_molar_mass=30.974, reported_stoich=None)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 100.0 * (1.0 * 30.974) / 177.99
    assert abs(result - expected) < 0.001


def test_g_wahr_reported_stoichiometry_2():
    """Stoichiometry factor 2 is applied correctly."""
    # raw = (1.0/2.0)*100 = 50%, correction = (2.0 * 50.0) / 200.0 = 0.5
    # result = 50.0 * 0.5 = 25.0%
    sample = _make_sample(1.0, 2.0, 100.0, 200.0, anhydrous_molar_mass=None,
                          reported_molar_mass=50.0, reported_stoich=2.0)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 50.0 * (2.0 * 50.0) / 200.0
    assert abs(result - expected) < 0.001


def test_g_wahr_reported_molar_mass_with_purity():
    """Purity is applied before the reported-component correction."""
    sample = _make_sample(0.3, 0.3, 99.0, 177.99, anhydrous_molar_mass=None,
                          reported_molar_mass=30.974, reported_stoich=1.0)
    ev = MassBasedEvaluator()
    result = ev._g_wahr(sample)
    expected = 99.0 * (1.0 * 30.974) / 177.99
    assert abs(result - expected) < 0.001
