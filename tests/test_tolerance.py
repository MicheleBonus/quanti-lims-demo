"""Tests for TitrantStandardizationEvaluator tolerance formula."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import TitrantStandardizationEvaluator


def _make_sample(titer_expected, tol_min, tol_max):
    """Build a mock sample/batch/analysis chain."""
    analysis = MagicMock()
    analysis.tol_min = tol_min
    analysis.tol_max = tol_max
    batch = MagicMock()
    batch.analysis = analysis
    batch.titer = titer_expected
    sample = MagicMock()
    sample.batch = batch
    return sample


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
