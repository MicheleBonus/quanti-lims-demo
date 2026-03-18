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
