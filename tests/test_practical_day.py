# tests/test_practical_day.py
import pytest

@pytest.fixture
def seeded(db):
    """Ensure a Semester and Block exist for these tests."""
    from models import Semester, Block
    sem = Semester.query.first()
    block = Block.query.first()
    if sem is None or block is None:
        pytest.skip("Seed data (Semester/Block) not available in test DB")
    return {"sem": sem, "block": block}

def test_practical_day_creation(db, seeded):
    from models import PracticalDay
    pd = PracticalDay(
        semester_id=seeded["sem"].id,
        block_id=seeded["block"].id,
        date="2026-10-06",
        day_type="normal",
        block_day_number=1,
    )
    db.session.add(pd)
    db.session.flush()
    assert pd.id is not None
    assert pd.day_type == "normal"

def test_practical_day_nachkochtag(db, seeded):
    from models import PracticalDay
    pd = PracticalDay(
        semester_id=seeded["sem"].id,
        block_id=seeded["block"].id,
        date="2026-10-11",
        day_type="nachkochtag",
        block_day_number=None,
    )
    db.session.add(pd)
    db.session.flush()
    assert pd.day_type == "nachkochtag"
    assert pd.block_day_number is None
