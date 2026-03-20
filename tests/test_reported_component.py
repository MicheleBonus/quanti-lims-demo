"""Tests for _v_expected_explicit with reported_molar_mass_gmol."""
from unittest.mock import MagicMock
from calculation_modes import MassBasedEvaluator


def _make_sample(molar_mass_gmol, reported_molar_mass=None, reported_stoich=None,
                 method_type="complexometric", c_titrant=0.1, n_eq_titrant=1.0,
                 anhydrous_molar_mass=None):
    """Build a minimal mock sample for _v_expected_explicit tests."""
    substance = MagicMock()
    substance.molar_mass_gmol = molar_mass_gmol
    substance.anhydrous_molar_mass_gmol = anhydrous_molar_mass

    method = MagicMock()
    method.method_type = method_type
    method.c_titrant_mol_l = c_titrant
    method.n_eq_titrant = n_eq_titrant
    method.c_vorlage_mol_l = None
    method.n_eq_vorlage = None
    method.v_vorlage_ml = None

    analysis = MagicMock()
    analysis.substance = substance
    analysis.method = method
    analysis.reported_molar_mass_gmol = reported_molar_mass
    analysis.reported_stoichiometry = reported_stoich

    batch = MagicMock()
    batch.analysis = analysis

    sample = MagicMock()
    sample.batch = batch
    return sample


def test_v_expected_uses_reported_molar_mass_as_mw_effective():
    """
    III.1: 300 mg Na2HPO4·2H2O (MW=177.99), g_wahr=17.40%
    n_Mg = (300 * 17.40/100) / (1.0 * 30.974) = 52.2 / 30.974 = 1.6853 mmol
    V_ZnSO4 = 1.6853 * 1.0 / 0.1 = 16.853 mL
    """
    sample = _make_sample(177.99, reported_molar_mass=30.974, reported_stoich=1.0)
    ev = MassBasedEvaluator()
    result = ev._v_expected_explicit(sample, g_wahr=17.40, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 16.853) < 0.01


def test_v_expected_reported_stoich_none_defaults_to_1():
    """reported_stoichiometry=None defaults to 1.0 in V_erw calculation."""
    sample = _make_sample(177.99, reported_molar_mass=30.974, reported_stoich=None)
    ev = MassBasedEvaluator()
    result = ev._v_expected_explicit(sample, g_wahr=17.40, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 16.853) < 0.01


def test_v_expected_without_reported_molar_mass_uses_substance_mw():
    """Without reported_molar_mass, falls back to substance.molar_mass_gmol (no hydrate)."""
    sample = _make_sample(177.99, reported_molar_mass=None)
    ev = MassBasedEvaluator()
    # g_wahr = 50.0% as if no correction
    # n_analyte = (300 * 50.0/100) / 177.99 = 150 / 177.99 = 0.8428 mmol
    # V = 0.8428 * 1.0 / 0.1 = 8.428 mL
    result = ev._v_expected_explicit(sample, g_wahr=50.0, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 8.428) < 0.01


def test_v_expected_reported_molar_mass_with_stoich_2():
    """Stoichiometry factor 2 halves the mw_effective, doubling n_analyte and V."""
    # mw_effective = 2.0 * 30.974 = 61.948
    # n = (300 * 17.40/100) / 61.948 = 52.2 / 61.948 = 0.8426 mmol
    # V = 0.8426 * 1.0 / 0.1 = 8.426 mL
    sample = _make_sample(177.99, reported_molar_mass=30.974, reported_stoich=2.0)
    ev = MassBasedEvaluator()
    result = ev._v_expected_explicit(sample, g_wahr=17.40, aliquot_fraction=1.0, e_ab_g=0.300)
    assert result is not None
    assert abs(result - 8.426) < 0.01
