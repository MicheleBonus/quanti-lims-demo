"""Mode-specific calculation and evaluation logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MODE_ASSAY_MASS_BASED = "assay_mass_based"
MODE_TITRANT_STANDARDIZATION = "titrant_standardization"


@dataclass
class SampleCalculation:
    g_wahr: float | None = None
    a_min: float | None = None
    a_max: float | None = None
    v_expected_ml: float | None = None
    titer_expected: float | None = None


@dataclass
class EvaluationResult:
    g_wahr: float | None = None
    v_expected_ml: float | None = None
    a_min: float | None = None
    a_max: float | None = None
    titer_expected: float | None = None
    titer_result: float | None = None
    passed: bool | None = None


class ModeEvaluator(Protocol):
    def calculate_sample(self, sample) -> SampleCalculation:
        ...

    def evaluate_result(self, result) -> EvaluationResult:
        ...


class MassBasedEvaluator:
    def _scale_factor(self, sample) -> float:
        method = sample.batch.analysis.method
        if method and method.weighing_basis == "per_determination":
            return float(method.n_aliquots or sample.batch.analysis.k_determinations or 1)
        return 1.0

    def _g_wahr(self, sample) -> float | None:
        if sample.m_s_actual_g is not None and sample.m_ges_actual_g is not None and sample.m_ges_actual_g > 0:
            return (sample.m_s_actual_g / sample.m_ges_actual_g) * sample.batch.p_effective
        return None

    def calculate_sample(self, sample) -> SampleCalculation:
        g_wahr = self._g_wahr(sample)
        tol_min = sample.batch.analysis.tol_min
        tol_max = sample.batch.analysis.tol_max

        scale_factor = self._scale_factor(sample)

        a_min_base = round(g_wahr * tol_min / 100.0, 4) if g_wahr is not None and tol_min is not None else None
        a_max_base = round(g_wahr * tol_max / 100.0, 4) if g_wahr is not None and tol_max is not None else None
        a_min = round(a_min_base * scale_factor, 4) if a_min_base is not None else None
        a_max = round(a_max_base * scale_factor, 4) if a_max_base is not None else None

        method = sample.batch.analysis.method
        v_expected_ml = None
        if g_wahr is not None and method is not None and method.m_eq_mg is not None and method.m_eq_mg > 0:
            m_s_mg = sample.m_s_actual_g * 1000.0
            # Use nominal concentration (Sollkonzentration = 1.000) for theoretical consumption
            t = 1.0
            equiv_vol = (m_s_mg * (g_wahr / 100.0) / (method.m_eq_mg * t)) * scale_factor
            if method.method_type in ("direct", "complexometric", "argentometric", "other"):
                v_expected_ml = round(equiv_vol, 3)
            elif method.method_type == "back" and method.v_vorlage_ml is not None:
                v_expected_ml = round(method.v_vorlage_ml - equiv_vol, 3)

        return SampleCalculation(g_wahr=g_wahr, a_min=a_min, a_max=a_max, v_expected_ml=v_expected_ml)

    def evaluate_result(self, result) -> EvaluationResult:
        sample_calc = self.calculate_sample(result.assignment.sample)
        passed = None
        if sample_calc.a_min is not None and sample_calc.a_max is not None:
            passed = sample_calc.a_min <= result.ansage_value <= sample_calc.a_max
        return EvaluationResult(
            g_wahr=sample_calc.g_wahr,
            v_expected_ml=sample_calc.v_expected_ml,
            a_min=sample_calc.a_min,
            a_max=sample_calc.a_max,
            passed=passed,
        )


class TitrantStandardizationEvaluator:
    def _expected_volume(self, sample) -> float | None:
        method = sample.batch.analysis.method
        if sample.m_s_actual_g is None or method is None or method.m_eq_mg is None:
            return None
        # Use nominal concentration (1.0) for theoretical volume calculation
        denom = method.m_eq_mg * 1.0
        if denom <= 0:
            return None
        return round((sample.m_s_actual_g * 1000.0) / denom, 3)

    def calculate_sample(self, sample) -> SampleCalculation:
        analysis = sample.batch.analysis
        titer_min = round(analysis.tol_min / 100.0, 4) if analysis.tol_min is not None else None
        titer_max = round(analysis.tol_max / 100.0, 4) if analysis.tol_max is not None else None
        return SampleCalculation(
            v_expected_ml=self._expected_volume(sample),
            titer_expected=sample.batch.titer,
            a_min=titer_min,
            a_max=titer_max,
        )

    def evaluate_result(self, result) -> EvaluationResult:
        sample = result.assignment.sample
        analysis = sample.batch.analysis
        method = analysis.method
        sample_calc = self.calculate_sample(sample)

        titer_result = None
        if (
            sample.m_s_actual_g is not None
            and method is not None
            and method.m_eq_mg is not None
            and result.ansage_value is not None
            and result.ansage_value > 0
        ):
            titer_result = round((sample.m_s_actual_g * 1000.0) / (method.m_eq_mg * result.ansage_value), 4)

        titer_min = sample_calc.a_min
        titer_max = sample_calc.a_max

        passed = None
        if titer_result is not None and titer_min is not None and titer_max is not None:
            passed = titer_min <= titer_result <= titer_max

        return EvaluationResult(
            v_expected_ml=sample_calc.v_expected_ml,
            a_min=titer_min,
            a_max=titer_max,
            titer_expected=sample_calc.titer_expected,
            titer_result=titer_result,
            passed=passed,
        )


def resolve_mode(mode: str | None) -> str:
    if mode in {MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION}:
        return mode
    return MODE_ASSAY_MASS_BASED


def get_evaluator(mode: str | None) -> ModeEvaluator:
    resolved = resolve_mode(mode)
    if resolved == MODE_TITRANT_STANDARDIZATION:
        return TitrantStandardizationEvaluator()
    return MassBasedEvaluator()
