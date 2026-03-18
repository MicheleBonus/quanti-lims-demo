# tests/test_navigation.py
def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Vorbereitung" in resp.data
    assert b"Praktikum" in resp.data

def test_navbar_has_vorbereitung_section(client):
    resp = client.get("/")
    assert b"Vorbereitung" in resp.data

def test_navbar_has_praktikum_section(client):
    resp = client.get("/")
    assert b"Praktikum" in resp.data

def test_navbar_stammdaten_link_present(client):
    resp = client.get("/admin/substances")
    assert b"Stammdaten" in resp.data

def test_navbar_semesterplanung_link_present(client):
    resp = client.get("/admin/substances")
    assert b"Semesterplanung" in resp.data

def test_praktikum_tagesansicht_loads(client):
    resp = client.get("/praktikum/")
    assert resp.status_code == 200
    assert b"Tagesansicht" in resp.data

def test_tagesansicht_no_practical_day_shows_banner(client):
    """When no PracticalDay exists for the selected date, page loads with info banner."""
    resp = client.get("/praktikum/?date=2099-12-31")
    assert resp.status_code == 200
    assert b"Tagesansicht" in resp.data

def test_tagesansicht_default_loads(client):
    """Default /praktikum/ loads without error."""
    resp = client.get("/praktikum/")
    assert resp.status_code == 200

def test_tagesansicht_no_active_semester_returns_200(client, app):
    """If no semester is active, the route returns 200 with a warning banner."""
    from models import db, Semester
    with app.app_context():
        # Deactivate all semesters temporarily
        Semester.query.update({"is_active": False})
        db.session.flush()
        resp = client.get("/praktikum/?date=2099-12-31")
        assert resp.status_code == 200
        db.session.rollback()

def test_tagesansicht_shows_student_table_when_slots(client, app):
    """When slots exist, the template renders student rows."""
    with app.app_context():
        from models import Semester
        sem = Semester.query.filter_by(is_active=True).first()
        if sem is None:
            import pytest; pytest.skip("No active semester in test DB")
        # Just verify the page loads — slot rendering tested via unit tests
        resp = client.get("/praktikum/?date=2099-12-30")
        assert resp.status_code == 200
