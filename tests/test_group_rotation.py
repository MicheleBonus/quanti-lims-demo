# tests/test_group_rotation.py
import pytest

@pytest.fixture
def seeded_day(db):
    """Create a PracticalDay with all required FK objects."""
    from models import PracticalDay, Semester, Block, Analysis
    sem = Semester.query.first()
    block = Block.query.first()
    analysis = Analysis.query.first()
    if sem is None or block is None or analysis is None:
        pytest.skip("Seed data (Semester/Block/Analysis) not available")
    pd = PracticalDay(semester_id=sem.id, block_id=block.id,
                      date="2026-10-07", day_type="normal", block_day_number=2)
    db.session.add(pd)
    db.session.flush()
    return {"pd": pd, "analysis": analysis, "sem": sem}

def test_group_rotation_creation(db, seeded_day):
    from models import GroupRotation
    gr = GroupRotation(practical_day_id=seeded_day["pd"].id, group_code="B",
                       analysis_id=seeded_day["analysis"].id, is_override=False)
    db.session.add(gr)
    db.session.flush()
    assert gr.group_code == "B"
    assert gr.is_override is False

def test_duty_assignment_creation(db, seeded_day):
    from models import DutyAssignment, Student
    student = Student.query.first()
    if student is None:
        pytest.skip("Seed data (Student) not available")
    da = DutyAssignment(practical_day_id=seeded_day["pd"].id,
                        student_id=student.id, duty_type="Saaldienst")
    db.session.add(da)
    db.session.flush()
    assert da.duty_type == "Saaldienst"
