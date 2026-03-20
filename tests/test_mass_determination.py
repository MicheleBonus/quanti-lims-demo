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


def test_evaluate_result_no_ansage_passed_is_none():
    ev = MassDeterminationEvaluator()
    result = _make_result(m_s_actual_g=0.1500, ansage_mg=None)
    er = ev.evaluate_result(result)
    assert er.passed is None


def test_analysis_form_saves_mass_determination_fields(client, db):
    """POST to analysis form with mass_determination mode saves new fields."""
    from models import Block, Substance, Analysis
    with client.application.app_context():
        block = Block(code="T", name="Test", max_days=4)
        substance = Substance(name="Glycerol Test", molar_mass_gmol=92.09)
        db.session.add_all([block, substance])
        db.session.flush()
        resp = client.post("/admin/analyses/new", data={
            "block_id": block.id,
            "code": "GLYC",
            "ordinal": 99,
            "name": "Glycerol-Bestimmung",
            "substance_id": substance.id,
            "calculation_mode": "mass_determination",
            "k_determinations": 3,
            "result_unit": "mg",
            "result_label": "Masse",
            "m_einwaage_min_mg": "120.0",
            "m_einwaage_max_mg": "180.0",
            "g_ab_min_pct": "98.0",
            "g_ab_max_pct": "102.0",
        }, follow_redirects=True)
        assert resp.status_code == 200
        a = Analysis.query.filter_by(code="GLYC").first()
        assert a is not None
        assert a.calculation_mode == "mass_determination"
        assert abs(a.m_einwaage_min_mg - 120.0) < 0.001
        assert abs(a.m_einwaage_max_mg - 180.0) < 0.001


def test_batch_form_mass_determination_skips_mass_validation(client, db):
    """POST batch form with mass_determination analysis does not require target_m_ges_g."""
    from models import Block, Substance, Analysis, Method, Semester
    with client.application.app_context():
        sem = Semester(code="TS26", name="Test 26", is_active=True)
        block = Block(code="TB", name="Test Block", max_days=4)
        substance = Substance(name="Glycerol Batch Test", molar_mass_gmol=92.09)
        db.session.add_all([sem, block, substance])
        db.session.flush()
        analysis = Analysis(
            block_id=block.id, code="GB1", ordinal=98, name="Glycerol Batch",
            substance_id=substance.id, calculation_mode="mass_determination",
            m_einwaage_min_mg=120.0, m_einwaage_max_mg=180.0,
            g_ab_min_pct=98.0, g_ab_max_pct=102.0,
        )
        db.session.add(analysis)
        db.session.flush()
        method = Method(analysis_id=analysis.id, method_type="back",
                        blind_required=True, b_blind_determinations=1,
                        v_solution_ml=100.0, v_aliquot_ml=20.0, aliquot_enabled=True)
        db.session.add(method)
        db.session.commit()

        resp = client.post(f"/admin/batches/new", data={
            "analysis_id": analysis.id,
            "total_samples_prepared": "5",
            "safety_factor": "1.3",
            "titer": "1.000",
        }, follow_redirects=True)
        assert resp.status_code == 200
        from models import SampleBatch
        batch = SampleBatch.query.filter_by(analysis_id=analysis.id).first()
        assert batch is not None
        assert abs(batch.safety_factor - 1.3) < 0.001
        assert batch.target_m_s_min_g is None
        assert batch.target_m_ges_g is None
