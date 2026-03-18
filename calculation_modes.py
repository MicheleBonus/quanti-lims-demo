"""Mode-specific calculation and evaluation logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MODE_ASSAY_MASS_BASED = "assay_mass_based"
MODE_TITRANT_STANDARDIZATION = "titrant_standardization"


def attempt_type_for(attempt_number: int) -> str:
    """Map attempt_number to the correct attempt_type label.

    attempt_number=1 → 'Erstanalyse' (the initial analysis, no repeat letter)
    attempt_number=2 → 'A'  (first repeat)
    attempt_number=3 → 'B'  (second repeat)
    attempt_number=n → chr(ord('A') + n - 2) for n in [2..27]
    attempt_number>27 → '#N' fallback (edge case, not expected in practice)
    """
    if attempt_number == 1:
        return "Erstanalyse"
    n = attempt_number - 2
    if 0 <= n <= 25:
        return chr(ord("A") + n)
    return f"#{attempt_number}"


def _next_attempt_label(attempt_type: str) -> str:
    """Return the label of the next repeat analysis after a failure."""
    if attempt_type == "Erstanalyse":
        return "A"
    # Current is a letter (A, B, C...); next is the following letter
    if len(attempt_type) == 1 and attempt_type.isalpha():
        return chr(ord(attempt_type) + 1)
    return "?"


def compute_evaluation_label(
    ansage_value: float,
    true_value: float,
    tol_min_pct: float | None,
    tol_max_pct: float | None,
    attempt_type: str,
) -> str | None:
    """Compute the evaluation label for a result (e.g. 'f↑ → A' or '✓').

    Uses the same δ-based formula as the live JS in submit.html.

    Args:
        ansage_value: The submitted result value.
        true_value:   The expected true value (titer_expected or g_wahr).
        tol_min_pct:  Lower tolerance bound as % of true value (e.g. 98.0).
        tol_max_pct:  Upper tolerance bound as % of true value (e.g. 102.0).
        attempt_type: Current attempt type ('Erstanalyse', 'A', 'B', ...).

    Returns:
        Label string like 'f↑ → A', '✓', 'f↓↓ → B', or None if undetermined.
    """
    if tol_min_pct is None or tol_max_pct is None:
        return None
    if not true_value:  # zero or None
        return None

    delta = (ansage_value - true_value) / true_value * 100.0
    T_min = 100.0 - tol_min_pct   # e.g. 100 - 98 = 2.0
    T_max = tol_max_pct - 100.0   # e.g. 102 - 100 = 2.0

    if -T_min <= delta <= T_max:
        return "✓"

    # Determine magnitude symbol
    if delta > 0:
        if delta > 4 * T_max:
            symbol = "f↑↑↑"
        elif delta > 2 * T_max:
            symbol = "f↑↑"
        else:
            symbol = "f↑"
    else:
        if delta < -4 * T_min:
            symbol = "f↓↓↓"
        elif delta < -2 * T_min:
            symbol = "f↓↓"
        else:
            symbol = "f↓"

    next_label = _next_attempt_label(attempt_type)
    return f"{symbol} → {next_label}"


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
    def _aliquot_fraction(self, sample) -> float:
        method = sample.batch.analysis.method
        if method and method.v_solution_ml and method.v_aliquot_ml and method.v_solution_ml > 0:
            return method.v_aliquot_ml / method.v_solution_ml
        return 1.0

    def _g_wahr(self, sample) -> float | None:
        if sample.m_s_actual_g is not None and sample.m_ges_actual_g is not None and sample.m_ges_actual_g > 0:
            return (sample.m_s_actual_g / sample.m_ges_actual_g) * sample.batch.p_effective
        return None

    def _v_expected_explicit(self, sample, g_wahr: float, aliquot_fraction: float, e_ab_g: float | None) -> float | None:
        """Calculate V_expected using explicit titration parameters (preferred)."""
        method = sample.batch.analysis.method
        if method is None or g_wahr is None or e_ab_g is None:
            return None
        substance = sample.batch.analysis.substance
        if substance is None or substance.molar_mass_gmol is None or substance.molar_mass_gmol <= 0:
            return None
        if method.c_titrant_mol_l is None or method.c_titrant_mol_l <= 0:
            return None

        mw = substance.molar_mass_gmol
        e_ab_mg = e_ab_g * 1000.0
        n_analyte_mmol = (e_ab_mg * g_wahr / 100.0) / mw

        if method.method_type in ("direct", "complexometric", "argentometric", "other"):
            n_eq = method.n_eq_titrant if method.n_eq_titrant is not None else 1.0
            v_titrant = n_analyte_mmol * n_eq / method.c_titrant_mol_l * aliquot_fraction
            return round(v_titrant, 3)
        elif method.method_type == "back":
            if (method.v_vorlage_ml is None or method.c_vorlage_mol_l is None
                    or method.n_eq_vorlage is None):
                return None
            n_eq_titrant = method.n_eq_titrant if method.n_eq_titrant is not None else 1.0
            n_vorlage_consumed = n_analyte_mmol * method.n_eq_vorlage
            n_vorlage_total = method.v_vorlage_ml * method.c_vorlage_mol_l
            n_vorlage_excess = n_vorlage_total - n_vorlage_consumed
            v_titrant = n_vorlage_excess * n_eq_titrant / method.c_titrant_mol_l * aliquot_fraction
            return round(v_titrant, 3)
        return None

    def _v_expected_legacy(self, sample, g_wahr: float, aliquot_fraction: float, e_ab_g: float | None) -> float | None:
        """Fallback: calculate V_expected using legacy m_eq_mg parameter."""
        method = sample.batch.analysis.method
        if method is None or method.m_eq_mg is None or method.m_eq_mg <= 0:
            return None
        if g_wahr is None or e_ab_g is None:
            return None
        e_ab_mg = e_ab_g * 1000.0
        t = 1.0  # Nominal concentration (Sollkonzentration = 1.000)
        equiv_vol = (e_ab_mg * (g_wahr / 100.0) / (method.m_eq_mg * t)) * aliquot_fraction
        if method.method_type in ("direct", "complexometric", "argentometric", "other"):
            return round(equiv_vol, 3)
        elif method.method_type == "back" and method.v_vorlage_ml is not None:
            return round(method.v_vorlage_ml - equiv_vol, 3)
        return None

    def calculate_sample(self, sample) -> SampleCalculation:
        g_wahr = self._g_wahr(sample)
        tol_min = sample.batch.analysis.tol_min
        tol_max = sample.batch.analysis.tol_max

        aliquot_fraction = self._aliquot_fraction(sample)

        a_min = round(g_wahr * tol_min / 100.0, 4) if g_wahr is not None and tol_min is not None else None
        a_max = round(g_wahr * tol_max / 100.0, 4) if g_wahr is not None and tol_max is not None else None

        # Resolve per-determination mass: prefer analysis.e_ab_g, fall back to m_s_actual_g
        e_ab_g = sample.batch.analysis.e_ab_g if sample.batch and sample.batch.analysis else None
        if e_ab_g is None:
            e_ab_g = sample.m_s_actual_g

        # Prefer explicit titration parameters, fall back to legacy m_eq_mg
        v_expected_ml = self._v_expected_explicit(sample, g_wahr, aliquot_fraction, e_ab_g)
        if v_expected_ml is None:
            v_expected_ml = self._v_expected_legacy(sample, g_wahr, aliquot_fraction, e_ab_g)

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
    """Evaluator for titrant standardization (Titereinstellung).

    The student weighs the primary standard (Urtitersubstanz), titrates,
    calculates the titer/factor, and reports it directly as ``ansage_value``.
    The system only validates whether the reported titer falls within the
    configured tolerance bounds.  No weighing data (m_s) from the TA is
    needed – the TA merely dispenses a volume of titrant solution.
    """

    def calculate_sample(self, sample) -> SampleCalculation:
        analysis = sample.batch.analysis
        titer_expected = sample.batch.titer
        titer_min = (
            round(titer_expected * analysis.tol_min / 100.0, 4)
            if titer_expected is not None and analysis.tol_min is not None
            else None
        )
        titer_max = (
            round(titer_expected * analysis.tol_max / 100.0, 4)
            if titer_expected is not None and analysis.tol_max is not None
            else None
        )
        return SampleCalculation(
            titer_expected=titer_expected,
            a_min=titer_min,
            a_max=titer_max,
        )

    def evaluate_result(self, result) -> EvaluationResult:
        sample_calc = self.calculate_sample(result.assignment.sample)

        # The student reports the calculated titer directly as ansage_value.
        titer_result = result.ansage_value

        titer_min = sample_calc.a_min
        titer_max = sample_calc.a_max

        passed = None
        if titer_result is not None and titer_min is not None and titer_max is not None:
            passed = titer_min <= titer_result <= titer_max

        return EvaluationResult(
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
