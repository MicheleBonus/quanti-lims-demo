"""Tests for Colloquium model and exclusion logic."""
import pytest
from models import Colloquium, Student, Block, Semester


def _make_fixtures(db):
    """Create self-contained Block + Semester + Student for each test."""
    import uuid
    code = uuid.uuid4().hex[:8]
    block = Block(code=code[:3], name=f"TestBlock-{code}")
    sem = Semester(code=f"T-{code}", name="Test", is_active=False)
    db.session.add_all([block, sem])
    db.session.flush()
    student = Student(semester_id=sem.id, matrikel=code[:8],
                      last_name="Tester", first_name="Test", running_number=1)
    db.session.add(student)
    db.session.flush()
    return block, sem, student


def test_colloquium_status_pending(db):
    """passed=None + scheduled_date → Geplant."""
    block, sem, student = _make_fixtures(db)
    c = Colloquium(student_id=student.id, block_id=block.id, attempt_number=1,
                   scheduled_date="2026-10-14")
    db.session.add(c)
    db.session.commit()
    assert c.passed is None
    assert c.status_label == "Geplant"


def test_colloquium_status_passed(db):
    """passed=True → Bestanden."""
    block, sem, student = _make_fixtures(db)
    c = Colloquium(student_id=student.id, block_id=block.id, attempt_number=1,
                   passed=True, conducted_date="2026-10-14")
    db.session.add(c)
    db.session.commit()
    assert c.status_label == "Bestanden"


def test_colloquium_status_failed(db):
    """passed=False → Nicht bestanden."""
    block, sem, student = _make_fixtures(db)
    c = Colloquium(student_id=student.id, block_id=block.id, attempt_number=2,
                   passed=False, conducted_date="2026-10-21")
    db.session.add(c)
    db.session.commit()
    assert c.status_label == "Nicht bestanden"


def test_student_is_excluded_default_false(db):
    """New students have is_excluded=False."""
    _, sem, student = _make_fixtures(db)
    assert student.is_excluded is False
