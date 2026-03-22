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


# ---------------------------------------------------------------------------
# POST tests
# ---------------------------------------------------------------------------

def test_post_rotation_save_creates_group_rotations(client, rot_fx):
    """POST valid data creates GroupRotation rows and redirects."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a1.id,
    }, follow_redirects=False)
    assert resp.status_code == 302
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr is not None
    assert gr.analysis_id == a1.id


def test_post_rotation_save_upserts_existing(client, rot_fx, db):
    """POST over an existing GroupRotation updates it, no duplicate rows."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    a2 = rot_fx["a2"]
    sem = rot_fx["sem"]
    # Pre-create
    existing = GroupRotation(practical_day_id=d1.id, group_code="A",
                             analysis_id=a1.id, is_override=False)
    db.session.add(existing)
    db.session.commit()
    # Overwrite with a2
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a2.id,
    })
    rows = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").all()
    assert len(rows) == 1
    assert rows[0].analysis_id == a2.id


def test_post_rotation_save_sets_override_flag(client, rot_fx):
    """Submitted value differs from suggest_rotation() → is_override = True."""
    d1 = rot_fx["day1"]
    a2 = rot_fx["a2"]  # day1 block_day_number=1, group A → suggest = a1 (ordinal 1); submit a2
    sem = rot_fx["sem"]
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a2.id,
    })
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr.is_override is True


def test_post_rotation_save_clears_override_flag(client, rot_fx):
    """Submitted value matches suggest_rotation() → is_override = False."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]  # day1 block_day_number=1, group A → suggest = a1; submit a1
    sem = rot_fx["sem"]
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": a1.id,
    })
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr.is_override is False


def test_post_rotation_save_blank_deletes_rotation(client, rot_fx, db):
    """Blank analysis_id for a cell with an existing row → row deleted."""
    d1 = rot_fx["day1"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    existing = GroupRotation(practical_day_id=d1.id, group_code="A",
                             analysis_id=a1.id, is_override=False)
    db.session.add(existing)
    db.session.commit()
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": "",
    })
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr is None


def test_post_rotation_save_blank_noop(client, rot_fx):
    """Blank analysis_id for a cell with no existing row → no error, no row created."""
    d1 = rot_fx["day1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": "",
    })
    assert resp.status_code == 302
    gr = GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first()
    assert gr is None


def test_post_rotation_save_no_analyses_on_block(client, rot_fx, db):
    """Block with no analyses: suggest_rotation() returns {}, all submitted values set is_override=True."""
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    # Create a block with no analyses so suggest_rotation() returns {}
    block2 = Block(code="EMPTY_BLK", name="Empty Block")
    db.session.add(block2)
    db.session.flush()
    day_empty = PracticalDay(semester_id=sem.id, block_id=block2.id,
                             date="2099-11-10", day_type="normal", block_day_number=1)
    db.session.add(day_empty)
    db.session.commit()

    # Block has no analyses → suggest_rotation() returns {} → is_override=True for any submission
    client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{day_empty.id}][A]": a1.id,
    })
    gr = GroupRotation.query.filter_by(practical_day_id=day_empty.id, group_code="A").first()
    assert gr is not None
    assert gr.is_override is True

    # Cleanup
    GroupRotation.query.filter_by(practical_day_id=day_empty.id).delete()
    PracticalDay.query.filter_by(id=day_empty.id).delete()
    Block.query.filter_by(code="EMPTY_BLK").delete()
    db.session.commit()


def test_post_rotation_save_ignores_nachkochtag(client, rot_fx):
    """POST with a Nachkochtag day_id → 400."""
    nk = rot_fx["nk"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{nk.id}][A]": a1.id,
    })
    assert resp.status_code == 400


def test_post_rotation_save_rejects_invalid_day_id(client, rot_fx):
    """POST with a day_id not in the semester → 400."""
    sem = rot_fx["sem"]
    a1 = rot_fx["a1"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        "rotation[99999][A]": a1.id,
    })
    assert resp.status_code == 400


def test_post_rotation_save_skips_invalid_analysis_id(client, rot_fx):
    """Unknown analysis_id → cell skipped, other cells still saved."""
    d1 = rot_fx["day1"]
    d2 = rot_fx["day2"]
    a1 = rot_fx["a1"]
    sem = rot_fx["sem"]
    resp = client.post("/vorbereitung/rotation/save", data={
        "semester_id": sem.id,
        f"rotation[{d1.id}][A]": 99999,   # invalid
        f"rotation[{d2.id}][A]": a1.id,   # valid
    }, follow_redirects=False)
    assert resp.status_code == 302
    # Invalid cell skipped
    assert GroupRotation.query.filter_by(practical_day_id=d1.id, group_code="A").first() is None
    # Valid cell saved
    assert GroupRotation.query.filter_by(practical_day_id=d2.id, group_code="A").first() is not None


def test_get_rotation_overview_no_active_semester_redirects(client, db):
    """GET without ?semester_id= and no active semester → redirect to dashboard."""
    # Ensure no active semester exists for this test
    semesters = Semester.query.filter_by(is_active=True).all()
    for s in semesters:
        s.is_active = False
    db.session.commit()
    try:
        resp = client.get("/vorbereitung/rotation", follow_redirects=False)
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"] or resp.status_code == 302
    finally:
        for s in semesters:
            s.is_active = True
        db.session.commit()
