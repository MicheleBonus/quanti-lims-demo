# tests/test_protocol_check.py
import pytest

def test_protocol_check_creation(db):
    from models import ProtocolCheck, SampleAssignment
    sa = SampleAssignment.query.first()
    if sa is None:
        pytest.skip("No SampleAssignment in test DB")
    pc = ProtocolCheck(sample_assignment_id=sa.id,
                       checked_date="2026-10-06", checked_by="TA Demo")
    db.session.add(pc)
    db.session.flush()
    assert pc.id is not None

def test_protocol_check_unique_per_assignment(db):
    from models import ProtocolCheck, SampleAssignment
    sa = SampleAssignment.query.first()
    if sa is None:
        pytest.skip("No SampleAssignment in test DB")
    pc1 = ProtocolCheck(sample_assignment_id=sa.id,
                        checked_date="2026-10-06", checked_by="TA1")
    pc2 = ProtocolCheck(sample_assignment_id=sa.id,
                        checked_date="2026-10-07", checked_by="TA2")
    db.session.add(pc1)
    db.session.flush()
    db.session.add(pc2)
    with pytest.raises(Exception):
        db.session.flush()
