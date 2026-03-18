"""Tests für den erweiterten live_eval_ctx in results_submit."""
from datetime import date
import pytest
from app import create_app
from models import (db, Block, Substance, SubstanceLot, SampleBatch,
                    Analysis, Method, Sample, SampleAssignment, Student,
                    Semester)

TEST_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "WTF_CSRF_ENABLED": False,
    "SECRET_KEY": "test-secret",
}


@pytest.fixture(scope="module")
def app():
    # Intentionally shadows conftest.py's session-scoped `app` fixture.
    # This module needs its own isolated in-memory DB so its seeded data
    # doesn't interfere with (or depend on) the shared session-scope database.
    return create_app(test_config=TEST_CONFIG)


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def mass_based_aid(app):
    """Seed a mass-based assignment once for all tests in this module."""
    with app.app_context():
        sem = Semester(code="WS2026-ctx", name="WS2026-ctx", is_active=True)
        db.session.add(sem)
        db.session.flush()

        block = Block(code="BLK-CTX", name="Block A")
        db.session.add(block)
        db.session.flush()

        sub = Substance(name="NaOH", formula="NaOH",
                        g_ab_min_pct=98.0, g_ab_max_pct=102.0)
        db.session.add(sub)
        db.session.flush()

        lot = SubstanceLot(substance_id=sub.id, lot_number="L1-ctx",
                           g_coa_pct=99.5)
        db.session.add(lot)
        db.session.flush()

        ana = Analysis(code="NA01-CTX", name="NaOH-Gehalt-ctx",
                       block_id=block.id, substance_id=sub.id,
                       ordinal=1,
                       calculation_mode="assay_mass_based",
                       result_unit="%", result_label="Gehalt",
                       tolerance_override_min_pct=98.0,
                       tolerance_override_max_pct=102.0)
        db.session.add(ana)
        db.session.flush()

        meth = Method(analysis_id=ana.id, method_type="direct",
                      m_eq_mg=40.0, v_solution_ml=100.0,
                      v_aliquot_ml=20.0, c_titrant_mol_l=0.1,
                      n_eq_titrant=1)
        db.session.add(meth)
        db.session.flush()

        batch = SampleBatch(semester_id=sem.id, analysis_id=ana.id,
                            substance_lot_id=lot.id,
                            total_samples_prepared=1)
        db.session.add(batch)
        db.session.flush()

        sample = Sample(batch_id=batch.id, running_number=1,
                        m_s_actual_g=0.5000, m_ges_actual_g=50.0)
        db.session.add(sample)
        db.session.flush()

        student = Student(running_number=99, matrikel="9999999",
                          first_name="Max", last_name="Muster-ctx",
                          semester_id=sem.id)
        db.session.add(student)
        db.session.flush()

        assign = SampleAssignment(
            sample_id=sample.id,
            student_id=student.id,
            attempt_number=1,
            status="assigned",
            assigned_date=date.today().isoformat(),
            assigned_by="System",
        )
        db.session.add(assign)
        db.session.commit()
        return assign.id


def test_live_eval_ctx_has_new_fields(app, client, mass_based_aid):
    """GET /results/submit/<id> renders template with extended live_eval_ctx."""
    resp = client.get(f"/results/submit/{mass_based_aid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # All new fields must appear in the tojson-serialised ctx
    assert '"a_min"' in body
    assert '"a_max"' in body
    assert '"result_unit"' in body
    assert '"result_label"' in body
    assert '"true_value_label"' in body


def test_live_eval_ctx_v_expected_present_for_mass_based(app, client, mass_based_aid):
    resp = client.get(f"/results/submit/{mass_based_aid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # v_expected_ml key must be present (value may be null if not calculable)
    assert '"v_expected_ml"' in body
