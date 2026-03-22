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

    return {"sem": sem, "block": block, "a1": a1, "a2": a2, "day": day}


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
