"""Route-level tests for admin PracticalDay form with GroupRotation."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, Substance, PracticalDay, GroupRotation,
)


def test_practical_days_list_loads(client):
    resp = client.get("/admin/practical-days")
    assert resp.status_code == 200
    assert b"Praktikumskalender" in resp.data

def test_practical_day_form_loads(client):
    resp = client.get("/admin/practical-days/new")
    assert resp.status_code == 200
    assert b"Datum" in resp.data


def test_admin_practical_day_edit_saves_group_rotations(client, db):
    """POST to admin edit form saves GroupRotation records."""
    sem = Semester(code="ADMIN_ROT", name="Admin Rot Test", is_active=True, active_group_count=2)
    db.session.add(sem)
    sub = Substance(name="AdminRotSub", formula="AR", molar_mass_gmol=1.0)
    db.session.add(sub)
    db.session.flush()
    block = Block(code="AR", name="Admin Rot Block")
    db.session.add(block)
    db.session.flush()
    a1 = Analysis(name="AR Analyse 1", block_id=block.id, code="AR.1",
                  ordinal=1, substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="AR Analyse 2", block_id=block.id, code="AR.2",
                  ordinal=2, substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()
    day = PracticalDay(semester_id=sem.id, block_id=block.id,
                       date="2099-12-01", day_type="normal", block_day_number=1)
    db.session.add(day)
    db.session.commit()

    resp = client.post(f"/admin/practical-days/{day.id}/edit", data={
        "date": "01.12.2099",
        "block_id": block.id,
        "day_type": "normal",
        "block_day_number": "1",
        "rotation_group_A": a1.id,
        "rotation_group_B": a2.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    grs = GroupRotation.query.filter_by(practical_day_id=day.id).all()
    assert len(grs) == 2
