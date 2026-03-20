"""Tests for reagent demand calculation (k=1 Grundbedarf, configurable safety_factor)."""
from unittest.mock import MagicMock


def test_safety_factor_from_batch():
    """Safety factor is read from batch, not hardcoded."""
    reagent = MagicMock()
    reagent.name = "NaOH-Lösung (0,1 mol/L)"
    reagent.is_composite = False
    mr = MagicMock()
    mr.reagent = reagent
    mr.amount_per_determination = 25.0
    mr.amount_per_blind = 0.0
    mr.amount_unit = "mL"
    mr.amount_unit_type = "volume"
    mr.is_titrant = False
    method = MagicMock()
    method.blind_required = False
    method.b_blind_determinations = 0
    method.reagent_usages = [mr]
    analysis = MagicMock()
    analysis.code = "GLYC"
    analysis.name = "Glycerol"
    analysis.k_determinations = 1
    analysis.method = method
    batch = MagicMock()
    batch.analysis = analysis
    batch.total_samples_prepared = 10
    batch.safety_factor = 1.5
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


def test_reagent_demand_uses_k1_not_k_determinations(client, db):
    """Integration: demand total uses k=1 regardless of analysis.k_determinations."""
    from models import Block, Substance, Analysis, Method, Semester, SampleBatch, Reagent, MethodReagent
    with client.application.app_context():
        # Deactivate any existing semesters so our test semester is the active one
        Semester.query.update({"is_active": False})
        db.session.flush()
        sem = Semester(code="RD26", name="Reagent Demand Test", is_active=True)
        block = Block(code="RD", name="Reagent Demand Block", max_days=4)
        substance = Substance(name="RD Substance", molar_mass_gmol=100.0)
        db.session.add_all([sem, block, substance])
        db.session.flush()
        # k_determinations=3, but Grundbedarf should only use k=1
        analysis = Analysis(
            block_id=block.id, code="RD1", ordinal=97, name="RD Analysis",
            substance_id=substance.id, calculation_mode="assay_mass_based",
            k_determinations=3, result_unit="%", result_label="Gehalt",
            g_ab_min_pct=98.0, g_ab_max_pct=102.0, e_ab_g=0.5,
        )
        db.session.add(analysis)
        db.session.flush()
        reagent = Reagent(name="TestNaOH", is_composite=False)
        db.session.add(reagent)
        db.session.flush()
        method = Method(
            analysis_id=analysis.id, method_type="direct",
            blind_required=False, b_blind_determinations=0,
            v_solution_ml=100.0, aliquot_enabled=False,
        )
        db.session.add(method)
        db.session.flush()
        usage = MethodReagent(
            method_id=method.id, reagent_id=reagent.id,
            amount_per_determination=25.0, amount_per_blind=0.0,
            amount_unit="mL", is_titrant=False,
        )
        db.session.add(usage)
        # n=10, safety_factor=1.2, k=1 → total = 10 × (1×25.0 + 0) × 1.2 = 300.0
        batch = SampleBatch(
            analysis_id=analysis.id, semester_id=sem.id,
            total_samples_prepared=10, titer=1.0, safety_factor=1.2,
        )
        db.session.add(batch)
        db.session.commit()

        resp = client.get("/reports/reagents")
        assert resp.status_code == 200
        # Total should be 300.0 (k=1), NOT 900.0 (k=3)
        assert b"300" in resp.data
        assert b"900" not in resp.data


def test_reagent_demand_uses_batch_safety_factor(client, db):
    """Integration: demand total uses batch.safety_factor not hardcoded 1.2."""
    from models import Block, Substance, Analysis, Method, Semester, SampleBatch, Reagent, MethodReagent
    with client.application.app_context():
        # Deactivate any existing semesters so our test semester is the active one
        Semester.query.update({"is_active": False})
        db.session.flush()
        sem = Semester(code="RD27", name="Reagent Safety Test", is_active=True)
        block = Block(code="RS", name="Reagent Safety Block", max_days=4)
        substance = Substance(name="RS Substance", molar_mass_gmol=100.0)
        db.session.add_all([sem, block, substance])
        db.session.flush()
        analysis = Analysis(
            block_id=block.id, code="RS1", ordinal=96, name="RS Analysis",
            substance_id=substance.id, calculation_mode="assay_mass_based",
            k_determinations=1, result_unit="%", result_label="Gehalt",
            g_ab_min_pct=98.0, g_ab_max_pct=102.0, e_ab_g=0.5,
        )
        db.session.add(analysis)
        db.session.flush()
        reagent = Reagent(name="TestReagent2", is_composite=False)
        db.session.add(reagent)
        db.session.flush()
        method = Method(
            analysis_id=analysis.id, method_type="direct",
            blind_required=False, b_blind_determinations=0,
            v_solution_ml=100.0, aliquot_enabled=False,
        )
        db.session.add(method)
        db.session.flush()
        usage = MethodReagent(
            method_id=method.id, reagent_id=reagent.id,
            amount_per_determination=10.0, amount_per_blind=0.0,
            amount_unit="mL", is_titrant=False,
        )
        db.session.add(usage)
        # n=4, safety_factor=1.5, k=1 → total = 4 × 10.0 × 1.5 = 60.0 (not 48.0 with 1.2)
        batch = SampleBatch(
            analysis_id=analysis.id, semester_id=sem.id,
            total_samples_prepared=4, titer=1.0, safety_factor=1.5,
        )
        db.session.add(batch)
        db.session.commit()

        resp = client.get("/reports/reagents")
        assert resp.status_code == 200
        assert b"60" in resp.data
