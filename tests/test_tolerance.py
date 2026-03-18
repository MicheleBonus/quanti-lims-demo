"""Tests for TitrantStandardizationEvaluator tolerance formula."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import TitrantStandardizationEvaluator


def _make_sample(titer_expected, tol_min, tol_max, m_ges_actual_g=None,
                 v_dilution_ml=None, c_titrant_mol_l=None, c_stock_mol_l=None):
    """Build a mock sample/batch/analysis chain.

    When method parameters are omitted the evaluator falls back to batch.titer.
    Pass v_dilution_ml / c_titrant_mol_l / c_stock_mol_l to test the per-sample
    titer calculation path.
    """
    method = MagicMock()
    method.v_dilution_ml = v_dilution_ml
    method.c_titrant_mol_l = c_titrant_mol_l
    method.c_stock_mol_l = c_stock_mol_l
    analysis = MagicMock()
    analysis.tol_min = tol_min
    analysis.tol_max = tol_max
    analysis.method = method if v_dilution_ml is not None else None
    batch = MagicMock()
    batch.analysis = analysis
    batch.titer = titer_expected
    sample = MagicMock()
    sample.batch = batch
    sample.m_ges_actual_g = m_ges_actual_g
    return sample


def test_per_sample_titer_from_dispensed_volume():
    """titer_expected must reflect the dispensed volume, not the nominal batch titer."""
    # V_theoretical = 100 mL * 0.1 mol/L / 1.0 mol/L = 10.0 mL
    # 9.45 mL dispensed → factor 0.9450
    sample = _make_sample(
        titer_expected=1.0, tol_min=98.0, tol_max=102.0,
        m_ges_actual_g=9.45,
        v_dilution_ml=100.0, c_titrant_mol_l=0.1, c_stock_mol_l=1.0,
    )
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert abs(result.titer_expected - 0.9450) < 0.0001, f"Expected 0.9450, got {result.titer_expected}"
    assert abs(result.a_min - round(0.9450 * 0.98, 4)) < 0.0001
    assert abs(result.a_max - round(0.9450 * 1.02, 4)) < 0.0001


def test_tolerance_relative_to_true_value():
    """Grenzen müssen relativ zum Probenfaktor berechnet werden, nicht absolut."""
    sample = _make_sample(titer_expected=0.9400, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert abs(result.a_min - 0.9212) < 0.0001, f"Expected 0.9212, got {result.a_min}"
    assert abs(result.a_max - 0.9588) < 0.0001, f"Expected 0.9588, got {result.a_max}"


def test_tolerance_with_titer_1_unchanged():
    """Für titer_expected=1.0 ergibt die neue Formel identische Werte wie die alte."""
    sample = _make_sample(titer_expected=1.0000, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert abs(result.a_min - 0.9800) < 0.0001
    assert abs(result.a_max - 1.0200) < 0.0001


def test_tolerance_none_when_tol_missing():
    sample = _make_sample(titer_expected=0.9400, tol_min=None, tol_max=None)
    evaluator = TitrantStandardizationEvaluator()
    result = evaluator.calculate_sample(sample)
    assert result.a_min is None
    assert result.a_max is None


def test_evaluate_result_passes_within_tolerance():
    sample = _make_sample(titer_expected=0.9400, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = MagicMock()
    result.ansage_value = 0.9400  # exactly the expected value → should pass
    result.assignment.sample = sample
    eval_result = evaluator.evaluate_result(result)
    assert eval_result.passed is True


def test_evaluate_result_fails_outside_tolerance():
    sample = _make_sample(titer_expected=0.9400, tol_min=98.0, tol_max=102.0)
    evaluator = TitrantStandardizationEvaluator()
    result = MagicMock()
    result.ansage_value = 0.9800  # outside new bounds [0.9212, 0.9588]
    result.assignment.sample = sample
    eval_result = evaluator.evaluate_result(result)
    assert eval_result.passed is False
