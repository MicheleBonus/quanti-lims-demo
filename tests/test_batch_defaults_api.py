"""Tests for /api/analysis/<id>/defaults endpoint."""
import json
import pytest


def test_api_returns_reported_molar_mass_for_phosphor(client, app):
    """III.1 defaults must include reported_molar_mass_gmol and reported_stoichiometry."""
    with app.app_context():
        from models import Analysis
        analysis = Analysis.query.filter_by(code="III.1").first()
        assert analysis is not None
        aid = analysis.id

    resp = client.get(f"/api/analysis/{aid}/defaults")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reported_molar_mass_gmol" in data, "API must return reported_molar_mass_gmol"
    assert "reported_stoichiometry" in data,   "API must return reported_stoichiometry"
    assert abs(data["reported_molar_mass_gmol"] - 30.974) < 0.01
    assert data["reported_stoichiometry"] == 1.0


def test_api_returns_null_reported_mass_for_regular_analysis(client, app):
    """Regular analysis (e.g. I.2) must return reported_molar_mass_gmol=null."""
    with app.app_context():
        from models import Analysis
        analysis = Analysis.query.filter_by(code="I.2").first()
        assert analysis is not None
        aid = analysis.id

    resp = client.get(f"/api/analysis/{aid}/defaults")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reported_molar_mass_gmol" in data
    assert data["reported_molar_mass_gmol"] is None
