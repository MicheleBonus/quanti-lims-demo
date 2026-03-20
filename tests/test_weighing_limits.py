"""Tests for weighing limit validation — specifically the new max m_ges constraint."""
import pytest
from unittest.mock import MagicMock
from calculation_modes import MODE_ASSAY_MASS_BASED


def _make_batch(target_m_s_min_g, target_m_ges_g, p_effective, gehalt_min_pct,
                molar_mass=None, anhydrous_molar_mass=None):
    batch = MagicMock()
    batch.target_m_s_min_g = target_m_s_min_g
    batch.target_m_ges_g = target_m_ges_g
    batch.analysis.calculation_mode = MODE_ASSAY_MASS_BASED
    # p_effective from lot
    batch.p_effective = p_effective
    # gehalt_min_pct stored on batch
    batch.gehalt_min_pct = gehalt_min_pct
    # molar mass fields for hydrate correction
    batch.analysis.substance.molar_mass_gmol = molar_mass
    batch.analysis.substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass
    return batch


def test_valid_weighing_no_violation(app):
    """m_s = 2.5 g, m_ges = 4.0 g, p_eff=100, p_min=50 → max_ges = 5.0 → ok"""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.0, 4.0, 100.0, 50.0)
        result = evaluate_weighing_limits(batch, 2.5, 4.0)
        assert not result["out_of_range"]
        assert not result["m_ges_max_violation"]


def test_m_s_below_minimum(app):
    """m_s < m_s_min → violation."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.0, 100.0, 50.0)
        result = evaluate_weighing_limits(batch, 2.0, 4.0)
        assert result["out_of_range"]
        assert result["m_s_min_violation"]


def test_m_ges_exceeds_max(app):
    """m_s=2.2, m_ges=7.8, p_eff=100, p_min=50 → max_ges=4.4 → violation"""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, 50.0)
        result = evaluate_weighing_limits(batch, 2.2, 7.8)
        assert result["out_of_range"]
        assert result["m_ges_max_violation"]


def test_m_ges_exactly_at_max(app):
    """m_ges exactly equal to max → no violation."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, 50.0)
        # max = 2.2 * 100.0 / 50.0 = 4.4
        result = evaluate_weighing_limits(batch, 2.2, 4.4)
        assert not result["m_ges_max_violation"]


def test_no_gehalt_min_skips_max_check(app):
    """If gehalt_min_pct is None, skip the max m_ges check."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, None)
        result = evaluate_weighing_limits(batch, 2.2, 99.0)
        assert not result["m_ges_max_violation"]


def test_hydrate_correction_applied_to_m_ges_max(app):
    """Hydrate: m_ges_max must use HYDRATE_FACTOR = MW_anhydrous / MW_hydrated.

    Li-Citrat: MW=282.1, MW_anhydrous=210.0 → factor≈0.744.
    m_s=2.2, p_eff=100, p_min=50, hydrate_factor=0.744
    → m_ges_max = 2.2 * 100 * 0.744 / 50 ≈ 3.273 g
    m_ges=3.5 should violate; m_ges=3.2 should NOT violate.
    Without fix: m_ges_max = 2.2*100/50 = 4.4 → neither value triggers, bug confirmed.
    """
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.0, 3.3, 100.0, 50.0,
                            molar_mass=282.1, anhydrous_molar_mass=210.0)
        hydrate_factor = 210.0 / 282.1  # ≈ 0.7443
        m_ges_max = 2.2 * 100.0 * hydrate_factor / 50.0  # ≈ 3.275

        # Just above the corrected threshold → violation expected
        result_over = evaluate_weighing_limits(batch, 2.2, m_ges_max + 0.1)
        assert result_over["m_ges_max_violation"], \
            "Expected violation when m_ges exceeds hydrate-corrected max"

        # Just below → no violation
        result_under = evaluate_weighing_limits(batch, 2.2, m_ges_max - 0.1)
        assert not result_under["m_ges_max_violation"], \
            "Expected no violation when m_ges is within hydrate-corrected max"


def test_no_hydrate_correction_without_anhydrous_mass(app):
    """When anhydrous_molar_mass is None, hydrate_factor defaults to 1.0 (unchanged behavior)."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 4.4, 100.0, 50.0, molar_mass=282.1, anhydrous_molar_mass=None)
        # max = 2.2 * 100 * 1.0 / 50 = 4.4 → 4.5 violates
        result = evaluate_weighing_limits(batch, 2.2, 4.5)
        assert result["m_ges_max_violation"]
        # 4.4 exactly → no violation
        result_exact = evaluate_weighing_limits(batch, 2.2, 4.4)
        assert not result_exact["m_ges_max_violation"]


def test_old_m_ges_minimum_check_removed(app):
    """m_ges below target_m_ges_g is no longer a violation (orientation only)."""
    from app import evaluate_weighing_limits
    with app.app_context():
        batch = _make_batch(2.2, 5.0, 100.0, 50.0)
        # m_ges=3.0 < target_m_ges_g=5.0, but m_ges < m_s*p_eff/p_min would be 4.4
        # 3.0 < 4.4, so NOT a max violation either
        result = evaluate_weighing_limits(batch, 2.2, 3.0)
        assert not result.get("m_ges_target_violation", False), \
            "Old minimum check must be removed"
