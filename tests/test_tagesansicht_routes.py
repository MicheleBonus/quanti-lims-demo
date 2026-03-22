"""Route-level tests for the Tagesansicht."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, SampleBatch, Sample,
    SampleAssignment, Student, PracticalDay, GroupRotation, Substance,
)


@pytest.fixture()
def tages_fx(db):
    """Minimal dataset for Tagesansicht route tests."""
    sem = Semester(code="WS_TAGES", name="Tages-Test", is_active=True, active_group_count=2)
    db.session.add(sem)
    db.session.flush()

    block = Block(code="RT", name="Route Test Block")
    db.session.add(block)
    db.session.flush()

    sub = Substance(name="TagesSubstanz", formula="Y", molar_mass_gmol=50.0)
    db.session.add(sub)
    db.session.flush()

    a1 = Analysis(name="Route Analyse 1", block_id=block.id, code="RT.1",
                  ordinal=1, substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="Route Analyse 2", block_id=block.id, code="RT.2",
                  ordinal=2, substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()

    day = PracticalDay(semester_id=sem.id, block_id=block.id,
                       date="2099-11-01", day_type="normal", block_day_number=1)
    db.session.add(day)
    db.session.flush()

    yield {"sem": sem, "block": block, "a1": a1, "a2": a2, "day": day}

    # Teardown: delete any committed data so the next test's fixture setup
    # doesn't hit UNIQUE constraint errors (routes may commit via follow_redirects).
    db.session.rollback()
    for model, filters in [
        (GroupRotation, {"practical_day_id": day.id}),
        (PracticalDay, {"semester_id": sem.id}),
        (Analysis, {"block_id": block.id}),
        (Block, {"code": "RT"}),
        (Semester, {"code": "WS_TAGES"}),
        (Substance, {"name": "TagesSubstanz"}),
    ]:
        db.session.query(model).filter_by(**filters).delete()
    db.session.commit()


def test_tagesansicht_passes_all_days(client, tages_fx):
    """Route passes all_days to template (timeline ribbon data)."""
    resp = client.get("/praktikum/?date=2099-11-01")
    assert resp.status_code == 200
    assert b"RT" in resp.data  # block code appears in timeline


def test_tagesansicht_no_practical_day_shows_hint(client, tages_fx):
    """Non-practical-day shows hint message, not raw ISO date."""
    resp = client.get("/praktikum/?date=2099-11-02")
    assert resp.status_code == 200
    assert b"2099-11-02" not in resp.data          # raw ISO must not appear
    assert "02.11.2099".encode() in resp.data       # DD.MM.YYYY format
    assert "oben" in resp.data.decode("utf-8")      # hint references the ribbon


def test_tagesansicht_chip_uses_analysis_code(client, tages_fx, db):
    """Analysis chip shows Analysis.code, not full name."""
    from models import Student, SampleBatch, Sample, SampleAssignment
    sem = tages_fx["sem"]
    day = tages_fx["day"]
    a1 = tages_fx["a1"]

    # Add GroupRotation so rotation_analysis is set
    gr = GroupRotation(practical_day_id=day.id, group_code="A",
                       analysis_id=a1.id, is_override=False)
    db.session.add(gr)

    st = Student(semester_id=sem.id, matrikel="CHIP001", last_name="Chiptest",
                 first_name="Anna", running_number=1, group_code="A")
    db.session.add(st)
    db.session.flush()

    batch = SampleBatch(semester_id=sem.id, analysis_id=a1.id, total_samples_prepared=2)
    db.session.add(batch)
    db.session.flush()

    sample = Sample(batch_id=batch.id, running_number=1, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
    db.session.add(sample)
    db.session.flush()

    sa = SampleAssignment(sample_id=sample.id, student_id=st.id,
                          attempt_number=1, attempt_type="Erstanalyse",
                          assigned_date="2099-11-01", status="assigned")
    db.session.add(sa)
    db.session.flush()

    resp = client.get("/praktikum/?date=2099-11-01")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "RT.1·E" in body                          # short code used
    assert "Route Analyse 1" not in body             # full name NOT in chip
    assert "results/submit" in body                  # links to Ansage


def test_tagesansicht_protocol_missing_column(client, tages_fx, db):
    """Passed assignment without protocol check appears in Protokoll fehlt column."""
    from models import Student, SampleBatch, Sample, SampleAssignment
    sem = tages_fx["sem"]
    day = tages_fx["day"]
    a1 = tages_fx["a1"]

    st = Student(semester_id=sem.id, matrikel="PROTO001", last_name="Prototest",
                 first_name="Bob", running_number=2, group_code="B")
    db.session.add(st)
    db.session.flush()

    batch = SampleBatch(semester_id=sem.id, analysis_id=a1.id, total_samples_prepared=3)
    db.session.add(batch)
    db.session.flush()

    sample = Sample(batch_id=batch.id, running_number=2, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
    db.session.add(sample)
    db.session.flush()

    sa = SampleAssignment(sample_id=sample.id, student_id=st.id,
                          attempt_number=1, attempt_type="Erstanalyse",
                          assigned_date="2099-11-01", status="passed")
    db.session.add(sa)
    db.session.flush()

    resp = client.get("/praktikum/?date=2099-11-01")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Protokoll fehlt" in body


def test_rotation_mini_ui_state_a_shows_form(client, tages_fx):
    """When no GroupRotations configured: form with selects is shown."""
    resp = client.get("/praktikum/?date=2099-11-01")
    body = resp.data.decode("utf-8")
    assert "rotation/save" in body          # save form action
    assert "Rotation speichern" in body     # submit button
    assert 'name="group_A"' in body         # select for group A


def test_rotation_mini_ui_state_b_shows_readonly(client, tages_fx, db):
    """When GroupRotations are configured: read-only view + edit button shown."""
    from models import GroupRotation
    gr = GroupRotation(practical_day_id=tages_fx["day"].id, group_code="A",
                       analysis_id=tages_fx["a1"].id, is_override=False)
    db.session.add(gr)
    db.session.flush()

    resp = client.get("/praktikum/?date=2099-11-01")
    body = resp.data.decode("utf-8")
    assert "rotation-readonly" in body       # read-only div present
    assert "rotation-edit" in body           # edit div pre-rendered (hidden)
    assert "Bearbeiten" in body              # edit button visible
    assert "RT.1" in body                    # analysis code shown


def test_rotation_save_creates_group_rotations(client, tages_fx, db):
    """POST to rotation/save creates GroupRotation records."""
    from models import GroupRotation
    day = tages_fx["day"]
    a1 = tages_fx["a1"]
    a2 = tages_fx["a2"]

    resp = client.post("/praktikum/rotation/save", data={
        "practical_day_id": day.id,
        "group_A": a1.id,
        "group_B": a2.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    grs = GroupRotation.query.filter_by(practical_day_id=day.id).all()
    assert len(grs) == 2
    codes = {gr.group_code for gr in grs}
    assert codes == {"A", "B"}


def test_rotation_save_sets_is_override(client, tages_fx, db):
    """is_override=True when submitted analysis differs from cyclic suggestion."""
    from models import GroupRotation
    day = tages_fx["day"]
    a1 = tages_fx["a1"]
    a2 = tages_fx["a2"]
    # Day 1 suggestion: A→a1, B→a2. Submit A→a2 (override), B→a2 (matches suggestion)
    client.post("/praktikum/rotation/save", data={
        "practical_day_id": day.id,
        "group_A": a2.id,   # differs from suggestion (a1)
        "group_B": a2.id,   # matches suggestion
    }, follow_redirects=True)
    gr_a = GroupRotation.query.filter_by(practical_day_id=day.id, group_code="A").first()
    gr_b = GroupRotation.query.filter_by(practical_day_id=day.id, group_code="B").first()
    assert gr_a.is_override is True
    assert gr_b.is_override is False


def test_rotation_save_rejects_wrong_block_analysis(client, tages_fx, db):
    """Analysis from a different block is rejected with flash error."""
    from models import Block, Analysis, Substance, GroupRotation
    other_sub = Substance(name="OtherSub99", formula="Z", molar_mass_gmol=1.0)
    db.session.add(other_sub)
    other_block = Block(code="OTHER99", name="Other Block")
    db.session.add(other_block)
    db.session.flush()
    other_a = Analysis(name="Other Analysis", block_id=other_block.id, code="OT.1",
                       ordinal=1, substance_id=other_sub.id, calculation_mode="assay_mass_based")
    db.session.add(other_a)
    db.session.flush()

    resp = client.post("/praktikum/rotation/save", data={
        "practical_day_id": tages_fx["day"].id,
        "group_A": other_a.id,
        "group_B": tages_fx["a2"].id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert GroupRotation.query.filter_by(practical_day_id=tages_fx["day"].id).count() == 0
