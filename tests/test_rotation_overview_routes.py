"""Route-level tests for /vorbereitung/rotation."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, PracticalDay,
    GroupRotation, Substance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def rot_fx(db):
    """Minimal dataset: one active semester, one block, two analyses, two normal days."""
    sem = Semester(code="WS_ROT", name="Rotation Test", is_active=True, active_group_count=2)
    db.session.add(sem)
    db.session.flush()

    sem2 = Semester(code="WS_ROT2", name="Rotation Test 2", is_active=False, active_group_count=2)
    db.session.add(sem2)
    db.session.flush()

    block = Block(code="RB", name="Rotation Block")
    db.session.add(block)
    db.session.flush()

    sub = Substance(name="RotSubstanz", formula="Z", molar_mass_gmol=60.0)
    db.session.add(sub)
    db.session.flush()

    a1 = Analysis(name="Rot Analyse 1", block_id=block.id, code="RB.1",
                  ordinal=1, substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="Rot Analyse 2", block_id=block.id, code="RB.2",
                  ordinal=2, substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()

    day1 = PracticalDay(semester_id=sem.id, block_id=block.id,
                        date="2099-10-15", day_type="normal", block_day_number=1)
    day2 = PracticalDay(semester_id=sem.id, block_id=block.id,
                        date="2099-10-22", day_type="normal", block_day_number=2)
    nk = PracticalDay(semester_id=sem.id, block_id=block.id,
                      date="2099-10-29", day_type="nachkochtag", block_day_number=None)
    db.session.add_all([day1, day2, nk])
    db.session.flush()

    yield {
        "sem": sem, "sem2": sem2, "block": block,
        "a1": a1, "a2": a2, "day1": day1, "day2": day2, "nk": nk,
    }

    db.session.rollback()
    for model, filters in [
        (GroupRotation, {"practical_day_id": day1.id}),
        (GroupRotation, {"practical_day_id": day2.id}),
        (GroupRotation, {"practical_day_id": nk.id}),
        (PracticalDay, {"semester_id": sem.id}),
        (Analysis, {"block_id": block.id}),
        (Block, {"code": "RB"}),
        (Semester, {"code": "WS_ROT"}),
        (Semester, {"code": "WS_ROT2"}),
        (Substance, {"name": "RotSubstanz"}),
    ]:
        db.session.query(model).filter_by(**filters).delete()
    db.session.commit()


@pytest.fixture()
def rot_empty_fx(db):
    """Active semester with no practical days."""
    sem = Semester(code="WS_EMPTY", name="Empty Rotation", is_active=True, active_group_count=2)
    db.session.add(sem)
    db.session.flush()

    yield {"sem": sem}

    db.session.rollback()
    db.session.query(Semester).filter_by(code="WS_EMPTY").delete()
    db.session.commit()


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------

def test_get_rotation_overview_returns_200(client, rot_fx):
    """GET /vorbereitung/rotation returns 200 and shows block heading."""
    sem_id = rot_fx["sem"].id
    resp = client.get(f"/vorbereitung/rotation?semester_id={sem_id}")
    assert resp.status_code == 200
    assert b"RB" in resp.data  # block code present


def test_get_rotation_overview_empty_state(client, rot_empty_fx):
    """GET with no practical days shows empty-state message."""
    sem_id = rot_empty_fx["sem"].id
    resp = client.get(f"/vorbereitung/rotation?semester_id={sem_id}")
    assert resp.status_code == 200
    assert "Praktikumskalender".encode() in resp.data


def test_get_rotation_overview_semester_param(client, rot_fx):
    """GET with ?semester_id= loads the specified semester."""
    sem2_id = rot_fx["sem2"].id
    resp = client.get(f"/vorbereitung/rotation?semester_id={sem2_id}")
    assert resp.status_code == 200
    # sem2 has no days, so empty-state message should appear
    assert "Praktikumskalender".encode() in resp.data
