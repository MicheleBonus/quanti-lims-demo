"""Tests for MODE_LOSS_ON_DRYING (Trocknungsverlust) evaluator."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import (
    LossOnDryingEvaluator,
    MODE_LOSS_ON_DRYING,
    SampleCalculation,
    resolve_mode,
    get_evaluator,
    MW_WATER,
)


def _make_sample(m_s_g, m_ges_g, p_effective=100.0, n_crystal_water=1,
                 molar_mass_gmol=198.17, tol_min=98.0, tol_max=102.0):
    """Build a mock sample for Glucose Monohydrate (default)."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass_gmol

    analysis = MagicMock()
    analysis.n_crystal_water = n_crystal_water
    analysis.substance = substance
    analysis.tol_min = tol_min
    analysis.tol_max = tol_max

    batch = MagicMock()
    batch.p_effective = p_effective
    batch.analysis = analysis

    sample = MagicMock()
    sample.m_s_actual_g = m_s_g
    sample.m_ges_actual_g = m_ges_g
    sample.batch = batch
    return sample


class TestLossOnDryingEvaluator:
    def test_hydrate_factor_glucose_monohydrate(self):
        """HYDRATE_FACTOR = 1 * 18.015 / 198.17"""
        ev = LossOnDryingEvaluator()
        sample = _make_sample(0.5, 1.0)
        factor = ev._hydrate_factor(sample)
        expected = 1 * MW_WATER / 198.17
        assert abs(factor - expected) < 1e-6

    def test_g_wahr_glucose_monohydrate_pure(self):
        """m_s=0.5g, m_ges=1.0g, p_eff=100 → g_wahr = 0.5/1.0 * 100 * (18.015/198.17) ≈ 4.547%"""
        ev = LossOnDryingEvaluator()
        sample = _make_sample(m_s_g=0.5, m_ges_g=1.0)
        calc = ev.calculate_sample(sample)
        expected = (0.5 / 1.0) * 100.0 * (MW_WATER / 198.17)
        assert abs(calc.g_wahr - expected) < 1e-4

    def test_g_wahr_half_dilution(self):
        """50% hydrate in mixture → same ratio different numbers, same result"""
        ev = LossOnDryingEvaluator()
        sample = _make_sample(m_s_g=0.3, m_ges_g=0.6, p_effective=100.0)
        calc = ev.calculate_sample(sample)
        expected = (0.3 / 0.6) * 100.0 * (MW_WATER / 198.17)
        assert abs(calc.g_wahr - expected) < 1e-4

    def test_g_wahr_with_purity(self):
        """p_effective=99.5 scales result proportionally"""
        ev = LossOnDryingEvaluator()
        sample = _make_sample(m_s_g=0.5, m_ges_g=1.0, p_effective=99.5)
        calc = ev.calculate_sample(sample)
        expected = (0.5 / 1.0) * 99.5 * (MW_WATER / 198.17)
        assert abs(calc.g_wahr - expected) < 1e-4

    def test_g_wahr_dihydrate(self):
        """Dihydrate with n=2: HYDRATE_FACTOR = 2 * 18.015 / MW"""
        mw_dihydrate = 250.0
        ev = LossOnDryingEvaluator()
        sample = _make_sample(m_s_g=0.5, m_ges_g=1.0, n_crystal_water=2,
                              molar_mass_gmol=mw_dihydrate)
        calc = ev.calculate_sample(sample)
        expected = (0.5 / 1.0) * 100.0 * (2 * MW_WATER / mw_dihydrate)
        assert abs(calc.g_wahr - expected) < 1e-4

    def test_g_wahr_none_when_m_s_missing(self):
        sample = _make_sample(m_s_g=None, m_ges_g=1.0)
        ev = LossOnDryingEvaluator()
        calc = ev.calculate_sample(sample)
        assert calc.g_wahr is None
        assert calc.a_min is None
        assert calc.a_max is None

    def test_g_wahr_none_when_m_ges_zero(self):
        sample = _make_sample(m_s_g=0.5, m_ges_g=0.0)
        ev = LossOnDryingEvaluator()
        calc = ev.calculate_sample(sample)
        assert calc.g_wahr is None

    def test_tolerance_bounds(self):
        """a_min = g_wahr * 98/100, a_max = g_wahr * 102/100"""
        ev = LossOnDryingEvaluator()
        sample = _make_sample(m_s_g=0.5, m_ges_g=1.0)
        calc = ev.calculate_sample(sample)
        g = calc.g_wahr
        assert abs(calc.a_min - round(g * 98.0 / 100.0, 4)) < 1e-8
        assert abs(calc.a_max - round(g * 102.0 / 100.0, 4)) < 1e-8

    def test_v_expected_is_none(self):
        """Gravimetric method: no V_expected"""
        ev = LossOnDryingEvaluator()
        sample = _make_sample(0.5, 1.0)
        calc = ev.calculate_sample(sample)
        assert calc.v_expected_ml is None

    def test_evaluate_result_pass(self):
        ev = LossOnDryingEvaluator()
        sample = _make_sample(0.5, 1.0)
        g_wahr = (0.5 / 1.0) * 100.0 * (MW_WATER / 198.17)
        result = MagicMock()
        result.ansage_value = g_wahr  # exactly correct
        result.assignment.sample = sample
        er = ev.evaluate_result(result)
        assert er.passed is True
        assert abs(er.g_wahr - g_wahr) < 1e-4

    def test_evaluate_result_fail_high(self):
        ev = LossOnDryingEvaluator()
        sample = _make_sample(0.5, 1.0)
        g_wahr = (0.5 / 1.0) * 100.0 * (MW_WATER / 198.17)
        result = MagicMock()
        result.ansage_value = g_wahr * 1.05  # 5% too high
        result.assignment.sample = sample
        er = ev.evaluate_result(result)
        assert er.passed is False

    def test_resolve_mode_loss_on_drying(self):
        assert resolve_mode(MODE_LOSS_ON_DRYING) == MODE_LOSS_ON_DRYING

    def test_get_evaluator_returns_loss_on_drying(self):
        ev = get_evaluator(MODE_LOSS_ON_DRYING)
        assert isinstance(ev, LossOnDryingEvaluator)


# ── Weighing limits tests ──────────────────────────────────────────────────

from app import evaluate_weighing_limits


def _make_batch_lod(n_crystal_water=1, molar_mass_gmol=198.17,
                    p_effective=100.0, gehalt_min_pct=98.0,
                    target_m_s_min_g=0.5):
    """Mock SampleBatch for a loss_on_drying analysis."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass_gmol
    substance.anhydrous_molar_mass_gmol = None

    analysis = MagicMock()
    analysis.calculation_mode = MODE_LOSS_ON_DRYING
    analysis.n_crystal_water = n_crystal_water
    analysis.substance = substance
    analysis.reported_molar_mass_gmol = None

    batch = MagicMock()
    batch.analysis = analysis
    batch.p_effective = p_effective
    batch.gehalt_min_pct = gehalt_min_pct
    batch.target_m_s_min_g = target_m_s_min_g
    return batch


class TestLossOnDryingWeighingLimits:
    def test_m_s_below_minimum(self):
        batch = _make_batch_lod(target_m_s_min_g=0.5)
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.4, m_ges_actual_g=0.04)
        assert result["m_s_min_violation"] is True
        assert result["out_of_range"] is True

    def test_m_s_at_minimum_no_violation(self):
        batch = _make_batch_lod(target_m_s_min_g=0.5)
        # m_ges small enough to satisfy the max constraint
        # m_ges_max = 0.5 * 100 * (18.015/198.17) / 98 = 0.04641 g
        m_ges_max = 0.5 * 100.0 * (MW_WATER / 198.17) / 98.0
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.5, m_ges_actual_g=m_ges_max - 0.001)
        assert result["m_s_min_violation"] is False

    def test_m_ges_too_large(self):
        """m_ges > m_s * p_eff * hydrate_factor / p_min → violation"""
        batch = _make_batch_lod()
        # m_ges_max = 0.6 * 100 * (18.015/198.17) / 98 ≈ 0.05569 g
        # m_ges=1.0 >> 0.056 → definite violation
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.6, m_ges_actual_g=1.0)
        assert result["m_ges_max_violation"] is True

    def test_m_ges_within_limit(self):
        """m_ges just below max: no violation"""
        batch = _make_batch_lod()
        m_ges_max = 0.6 * 100.0 * (MW_WATER / 198.17) / 98.0
        result = evaluate_weighing_limits(batch, m_s_actual_g=0.6,
                                          m_ges_actual_g=m_ges_max - 0.0001)
        assert result["m_ges_max_violation"] is False
        assert result["out_of_range"] is False
