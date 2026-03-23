"""Tests for assignment logic."""
import pytest
from models import db, SampleBatch, Sample, SampleAssignment, Student, Semester, Analysis, Result


def _get_batch_and_unweighed_sample(db_session):
    """Helper: return a batch where sample #1 has no weighing data.
    Clears m_ges_actual_g (required for both modes) to simulate unweighed."""
    batch = SampleBatch.query.first()
    sample = Sample.query.filter_by(batch_id=batch.id, running_number=1).first()
    # Clear m_ges_actual_g — required by is_weighed for both modes
    sample.m_s_actual_g = None
    sample.m_ges_actual_g = None
    db_session.session.flush()
    return batch, sample


def test_assign_initial_skips_unweighed_samples(client, db):
    """Zuweisen soll Proben ohne Einwagedaten überspringen."""
    batch, sample = _get_batch_and_unweighed_sample(db)

    # Cancel any existing assignment for this sample so a new one would
    # normally be created, allowing us to test that the is_weighed guard fires.
    existing = SampleAssignment.query.filter_by(sample_id=sample.id).all()
    for sa in existing:
        sa.status = "cancelled"
    db.session.flush()

    # Count existing non-cancelled assignments before
    before = SampleAssignment.query.filter_by(sample_id=sample.id).filter(
        SampleAssignment.status != "cancelled"
    ).count()

    response = client.post(f"/admin/batches/{batch.id}/assign-initial",
                           follow_redirects=True)
    assert response.status_code == 200

    after = SampleAssignment.query.filter_by(sample_id=sample.id).filter(
        SampleAssignment.status != "cancelled"
    ).count()
    # The unweighed sample should NOT have gained a new assignment
    assert after == before


def test_revoke_result_resets_assignment_to_assigned(client, db):
    """Widerruf eines Ergebnisses setzt Zuweisung zurück auf 'assigned'."""
    from models import SampleAssignment, Result
    # Find an assignment with a result (if none, create one)
    sa = SampleAssignment.query.filter(
        SampleAssignment.status.in_(["passed", "failed", "submitted"])
    ).first()
    if sa is None:
        pytest.skip("No submitted assignment in test data")
    result = sa.active_result or sa.latest_result
    assert result is not None

    response = client.post(f"/results/{result.id}/revoke", follow_redirects=True)
    assert response.status_code == 200

    db.session.refresh(result)
    db.session.refresh(sa)
    assert result.revoked is True
    assert result.revoked_date is not None
    assert sa.status == "assigned"


def test_revoke_idempotent(client, db):
    """Zweifacher Widerruf desselben Ergebnisses ist harmlos."""
    from models import SampleAssignment, Result
    sa = SampleAssignment.query.filter(
        SampleAssignment.status.in_(["passed", "failed", "submitted"])
    ).first()
    if sa is None:
        pytest.skip("No submitted assignment in test data")
    result = sa.active_result or sa.latest_result
    client.post(f"/results/{result.id}/revoke")
    response = client.post(f"/results/{result.id}/revoke", follow_redirects=True)
    assert response.status_code == 200  # no crash


def test_active_result_ignores_revoked(db):
    """active_result gibt None zurück wenn alle Ergebnisse widerrufen sind."""
    from models import SampleAssignment
    sa = SampleAssignment.query.filter(
        SampleAssignment.status.in_(["passed", "failed"])
    ).first()
    if sa is None:
        pytest.skip("No completed assignment in test data")
    for r in sa.results:
        r.revoked = True
    db.session.flush()
    assert sa.active_result is None


def test_expelled_sample_not_free(client, db):
    """Eine Pufferprobe mit expelled-Assignment gilt als belegt."""
    from models import Sample, SampleAssignment, Student
    buffer = Sample.query.filter_by(is_buffer=True).first()
    if buffer is None:
        pytest.skip("Keine Pufferprobe in Testdaten")
    sa = SampleAssignment.query.filter_by(sample_id=buffer.id).first()
    if sa is None:
        # Create a minimal assignment so the expelled-logic can be tested
        student = Student.query.first()
        if student is None:
            pytest.skip("Kein Student in Testdaten")
        sa = SampleAssignment(
            sample_id=buffer.id, student_id=student.id,
            attempt_number=1, attempt_type="main",
            assigned_date="2026-01-01", assigned_by="Test",
            status="assigned",
        )
        db.session.add(sa)
        db.session.flush()
    sa.status = "expelled"
    db.session.flush()
    assert buffer.active_assignment is not None
