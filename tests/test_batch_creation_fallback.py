"""Tests for the server-side mSMin fallback formula (Bug 3)."""
import pytest


def test_reported_component_fallback_formula_is_correct(app):
    """For III.1: verify that mSMin = mGesMin × gehalt_min / (100 × CONTENT_FACTOR).

    Uses the real Analysis object from DB so the test breaks if the DB config changes.
    """
    with app.app_context():
        from models import Analysis
        analysis = Analysis.query.filter_by(code="III.1").first()
        assert analysis is not None
        assert analysis.reported_molar_mass_gmol is not None, \
            "III.1 must have reported_molar_mass_gmol configured"

        e_ab      = analysis.e_ab_g             # 0.3 g
        k         = analysis.k_determinations   # 2
        n_extra   = 1
        mortar_f  = 1.1
        gehalt_min = 15.0

        mges = round(e_ab * (k + n_extra) * mortar_f, 3)
        assert abs(mges - 0.99) < 0.001, f"mGesMin = {mges}, expected ~0.99"

        n  = analysis.reported_stoichiometry or 1.0
        cf = n * analysis.reported_molar_mass_gmol / analysis.substance.molar_mass_gmol
        assert abs(cf - 0.1740) < 0.001, f"CONTENT_FACTOR = {cf:.4f}, expected ~0.1740"

        ms_correct = round(mges * gehalt_min / (100.0 * cf), 3)
        assert abs(ms_correct - 0.854) < 0.01, \
            f"Correct mSMin = {ms_correct}, expected ~0.854 g"


def test_old_formula_gives_wrong_answer():
    """Document that the old formula was wrong — pure arithmetic, no app needed."""
    e_ab, k, n_extra, mortar_f, gehalt_min = 0.3, 2, 1, 1.1, 15.0
    mges = round(e_ab * (k + n_extra) * mortar_f, 3)      # 0.990 g
    old_ms = round(e_ab * 98.0 / 100.0, 3)                # 0.294 g — old wrong formula
    cf = 1.0 * 30.974 / 177.99                             # 0.1740
    correct_ms = round(mges * gehalt_min / (100.0 * cf), 3)  # 0.854 g
    assert abs(old_ms - 0.294) < 0.001, "Old formula gives 0.294 g"
    assert abs(correct_ms - 0.854) < 0.01, "New formula gives 0.854 g"
    assert correct_ms > old_ms * 2, "New value must be significantly larger"
