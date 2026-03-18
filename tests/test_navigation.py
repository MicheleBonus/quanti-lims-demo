# tests/test_navigation.py
def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Vorbereitung" in resp.data
    assert b"Praktikum" in resp.data
