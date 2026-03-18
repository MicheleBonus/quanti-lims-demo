# tests/test_practical_day_routes.py
def test_practical_days_list_loads(client):
    resp = client.get("/admin/practical-days")
    assert resp.status_code == 200
    assert b"Praktikumskalender" in resp.data

def test_practical_day_form_loads(client):
    resp = client.get("/admin/practical-days/new")
    assert resp.status_code == 200
    assert b"Datum" in resp.data
