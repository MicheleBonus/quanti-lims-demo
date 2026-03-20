"""Tests for MassDeterminationEvaluator."""
from unittest.mock import MagicMock
from calculation_modes import (
    MassDeterminationEvaluator,
    MODE_MASS_DETERMINATION,
    resolve_mode,
    get_evaluator,
)


def _make_sample(m_s_actual_g, tol_min=98.0, tol_max=102.0):
    analysis = MagicMock()
    analysis.tol_min = tol_min
    analysis.tol_max = tol_max
    batch = MagicMock()
    batch.analysis = analysis
    sample = MagicMock()
    sample.batch = batch
    sample.m_s_actual_g = m_s_actual_g
    return sample


def _make_result(m_s_actual_g, ansage_mg, tol_min=98.0, tol_max=102.0):
    sample = _make_sample(m_s_actual_g, tol_min, tol_max)
    result = MagicMock()
    result.assignment = MagicMock()
    result.assignment.sample = sample
    result.ansage_value = ansage_mg
    return result


def test_mode_constant_exists():
    assert MODE_MASS_DETERMINATION == "mass_determination"

def test_resolve_mode_returns_mass_determination():
    assert resolve_mode("mass_determination") == MODE_MASS_DETERMINATION

def test_get_evaluator_returns_mass_determination_evaluator():
    ev = get_evaluator("mass_determination")
    assert isinstance(ev, MassDeterminationEvaluator)

def test_resolve_mode_still_defaults_unknown_to_assay_mass_based():
    from calculation_modes import MODE_ASSAY_MASS_BASED
    assert resolve_mode("unknown_mode") == MODE_ASSAY_MASS_BASED

def test_calculate_sample_g_wahr_is_mass_in_mg():
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(0.1500))
    assert abs(calc.g_wahr - 150.0) < 0.001

def test_calculate_sample_tolerance_bounds():
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(0.1500, tol_min=98.0, tol_max=102.0))
    assert abs(calc.a_min - 147.0) < 0.001
    assert abs(calc.a_max - 153.0) < 0.001

def test_calculate_sample_no_mass_returns_none():
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(None))
    assert calc.g_wahr is None
    assert calc.a_min is None
    assert calc.a_max is None

def test_calculate_sample_v_expected_is_none():
    ev = MassDeterminationEvaluator()
    calc = ev.calculate_sample(_make_sample(0.1500))
    assert calc.v_expected_ml is None
    assert calc.titer_expected is None

def test_evaluate_result_passes_within_tolerance():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=150.5)
    er = ev.evaluate_result(result)
    assert er.passed is True

def test_evaluate_result_fails_below_tolerance():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=145.0)
    er = ev.evaluate_result(result)
    assert er.passed is False

def test_evaluate_result_fails_above_tolerance():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=155.0)
    er = ev.evaluate_result(result)
    assert er.passed is False

def test_evaluate_result_no_mass_passed_is_none():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=None, ansage_mg=150.0)
    er = ev.evaluate_result(result)
    assert er.passed is None
