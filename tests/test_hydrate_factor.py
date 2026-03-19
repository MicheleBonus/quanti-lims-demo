"""Tests for hydrate correction factor in MassBasedEvaluator."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample(m_s, m_ges, p_effective, molar_mass, anhydrous_molar_mass=None):
    """Build minimal mock sample chain for g_wahr tests."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass
    substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass

    analysis = MagicMock()
    analysis.substance = substance
    analysis.e_ab_g = None
    analysis.method = None

    lot = MagicMock()
    lot.p_effective = p_effective

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
