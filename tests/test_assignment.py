"""Tests for assignment logic."""
import pytest
from models import db, SampleBatch, Sample, SampleAssignment, Student, Semester, Analysis


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
