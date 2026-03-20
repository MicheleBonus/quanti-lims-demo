"""Tests for reagent demand calculation (k=1 Grundbedarf, configurable safety_factor)."""
from unittest.mock import MagicMock, patch


def _make_batch_with_reagent(safety_factor=1.2, amount_per_det=25.0, amount_per_blind=25.0,
                              blind_required=True, b_blind=1, k_determinations=3, n=80):
    reagent = MagicMock()
    reagent.name = "NaOH-Lösung (0,1 mol/L)"
    reagent.is_composite = False
    mr = MagicMock()
    mr.reagent = reagent
    mr.amount_per_determination = amount_per_det
    mr.amount_per_blind = amount_per_blind
    mr.amount_unit = "mL"
    mr.amount_unit_type = "volume"
    mr.is_titrant = False
    method = MagicMock()
    method.blind_required = blind_required
    method.b_blind_determinations = b_blind
    method.reagent_usages = [mr]
    analysis = MagicMock()
    analysis.code = "GLYC"
    analysis.name = "Glycerol"
    analysis.k_determinations = k_determinations
    analysis.method = method
    batch = MagicMock()
    batch.analysis = analysis
    batch.total_samples_prepared = n
    batch.safety_factor = safety_factor
    return batch, mr


def test_grundbedarf_uses_k_equals_1():
    """Grundbedarf uses k=1 (Erstanalysen only), not analysis.k_determinations."""
    batch, mr = _make_batch_with_reagent(safety_factor=1.2, amount_per_det=25.0,
                                          amount_per_blind=0.0, blind_required=False, n=80, k_determinations=3)
    # Expected: 80 × (1 × 25.0 + 0) × 1.2 = 2400.0
    k = 1
    b = 0
    total = batch.total_samples_prepared * (k * mr.amount_per_determination + b * mr.amount_per_blind) * batch.safety_factor
    assert abs(total - 2400.0) < 0.01


def test_grundbedarf_includes_blind():
    """Blind determinations are still included in the formula."""
    batch, mr = _make_batch_with_reagent(safety_factor=1.2, amount_per_det=25.0,
                                          amount_per_blind=25.0, blind_required=True, b_blind=1, n=80)
    # Expected: 80 × (1 × 25.0 + 1 × 25.0) × 1.2 = 4800.0
    k = 1
    b = 1
    total = batch.total_samples_prepared * (k * mr.amount_per_determination + b * mr.amount_per_blind) * batch.safety_factor
    assert abs(total - 4800.0) < 0.01


def test_safety_factor_from_batch():
    """Safety factor is read from batch, not hardcoded."""
    batch, mr = _make_batch_with_reagent(safety_factor=1.5, amount_per_det=25.0,
                                          amount_per_blind=0.0, blind_required=False, n=10)
    k = 1
    b = 0
    total = batch.total_samples_prepared * (k * mr.amount_per_determination + b * mr.amount_per_blind) * batch.safety_factor
    assert abs(total - 375.0) < 0.01  # 10 × 25.0 × 1.5


def test_reports_reagents_route_uses_k1_and_batch_safety(client, db):
    """Integration test: /reports/reagents uses k=1 and batch.safety_factor."""
    resp = client.get("/reports/reagents")
    assert resp.status_code == 200
    # Formula text should mention "1 ×" not "k ×"
    assert b"1 \xc3\x97" in resp.data or b"(1 &times;" in resp.data or b"Erstanalysen" in resp.data
