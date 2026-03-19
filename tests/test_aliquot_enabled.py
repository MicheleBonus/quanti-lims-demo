"""Tests for aliquot_enabled flag on Method."""
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample_with_method(aliquot_enabled, v_solution_ml, v_aliquot_ml):
    method = MagicMock()
    method.aliquot_enabled = aliquot_enabled
    method.v_solution_ml = v_solution_ml
    method.v_aliquot_ml = v_aliquot_ml
    analysis = MagicMock()
    analysis.method = method
    analysis.substance = MagicMock()
    analysis.substance.molar_mass_gmol = 100.0
    analysis.substance.anhydrous_molar_mass_gmol = None
    analysis.e_ab_g = None
    batch = MagicMock()
    batch.analysis = analysis
    batch.p_effective = 100.0
    sample = MagicMock()
    sample.batch = batch
    sample.m_s_actual_g = 2.0
    sample.m_ges_actual_g = 4.0
    return sample


def test_aliquot_fraction_when_enabled():
    """aliquot_enabled=True uses v_aliquot_ml / v_solution_ml."""
    sample = _make_sample_with_method(True, 100.0, 20.0)
    ev = MassBasedEvaluator()
    assert abs(ev._aliquot_fraction(sample) - 0.2) < 0.0001


def test_aliquot_fraction_when_disabled():
    """aliquot_enabled=False returns 1.0 even if volumes are set."""
    sample = _make_sample_with_method(False, 100.0, 20.0)
    ev = MassBasedEvaluator()
    assert ev._aliquot_fraction(sample) == 1.0


def test_aliquot_fraction_when_none():
    """aliquot_enabled=None (old data) falls back to volume-based check."""
    sample = _make_sample_with_method(None, 100.0, 20.0)
    ev = MassBasedEvaluator()
    # None should behave like old code: use volumes if set
    assert abs(ev._aliquot_fraction(sample) - 0.2) < 0.0001
