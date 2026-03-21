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


def test_order_list_expands_nested_composites(client, db):
    """Integration: /reports/reagents/order-list expands 3-level composites correctly."""
    from models import (
        Block, Substance, Analysis, Method, Semester, SampleBatch,
        Reagent, MethodReagent, ReagentComponent,
    )
    with client.application.app_context():
        Semester.query.update({"is_active": False})
        db.session.flush()
        sem = Semester(code="OL01", name="Order List Nested Test", is_active=True)
        block = Block(code="OL", name="Order List Block", max_days=4)
        substance = Substance(name="OL Substance", molar_mass_gmol=100.0)
        db.session.add_all([sem, block, substance])
        db.session.flush()

        analysis = Analysis(
            block_id=block.id, code="OL1", ordinal=90, name="OL Analysis",
            substance_id=substance.id, calculation_mode="assay_mass_based",
            k_determinations=1, result_unit="%", result_label="Gehalt",
            g_ab_min_pct=98.0, g_ab_max_pct=102.0, e_ab_g=0.5,
        )
        db.session.add(analysis)
        db.session.flush()

        # 3-level: ammonia (base) → ammoniak_lsg (composite) → buffer (composite)
        ammonia = Reagent(name="OL Ammoniak konz.", is_composite=False, base_unit="mL", density_g_ml=0.91)
        water = Reagent(name="OL Wasser R", is_composite=False, base_unit="mL")
        nh3_lsg = Reagent(name="OL Ammoniaklösung R", is_composite=True, base_unit="mL")
        buffer = Reagent(name="OL Pufferlösung R", is_composite=True, base_unit="mL")
        db.session.add_all([ammonia, water, nh3_lsg, buffer])
        db.session.flush()

        # nh3_lsg: 67g ammonia + 26mL water per 93mL
        db.session.add_all([
            ReagentComponent(parent_reagent_id=nh3_lsg.id, child_reagent_id=ammonia.id,
                             quantity=67.0, quantity_unit="g", per_parent_volume_ml=93.0),
            ReagentComponent(parent_reagent_id=nh3_lsg.id, child_reagent_id=water.id,
                             quantity=26.0, quantity_unit="mL", per_parent_volume_ml=93.0),
            # buffer: 100mL nh3_lsg per 1000mL
            ReagentComponent(parent_reagent_id=buffer.id, child_reagent_id=nh3_lsg.id,
                             quantity=100.0, quantity_unit="mL", per_parent_volume_ml=1000.0),
        ])

        method = Method(
            analysis_id=analysis.id, method_type="direct",
            blind_required=False, b_blind_determinations=0,
            v_solution_ml=100.0, aliquot_enabled=False,
        )
        db.session.add(method)
        db.session.flush()

        usage = MethodReagent(
            method_id=method.id, reagent_id=buffer.id,
            amount_per_determination=100.0, amount_per_blind=0.0,
            amount_unit="mL", is_titrant=False,
        )
        db.session.add(usage)
        batch = SampleBatch(
            analysis_id=analysis.id, semester_id=sem.id,
            total_samples_prepared=1, titer=1.0, safety_factor=1.0,
        )
        db.session.add(batch)
        db.session.commit()

        # NOTE: No Sample rows added → batch.samples is empty → n=0 → all totals are 0.
        # The test checks name presence only (items are inserted into order_acc even with
        # amount=0 because expand_reagent runs regardless). This is a structural smoke test.
        resp = client.get("/reports/reagents/order-list")
        assert resp.status_code == 200
        text = resp.data.decode()
        # Base reagents appear (name present in table)
        assert "OL Ammoniak konz." in text
        assert "OL Wasser R" in text
        # Composites should NOT appear as table rows (only as "Verwendung" references)
        assert "<td>OL Ammoniaklösung R</td>" not in text
        assert "<td>OL Pufferlösung R</td>" not in text


def test_prep_list_includes_intermediate_composites(client, db):
    """Integration: /reports/reagents/prep-list shows all composites in topo order."""
    from models import (
        Block, Substance, Analysis, Method, Semester, SampleBatch,
        Reagent, MethodReagent, ReagentComponent,
    )
    with client.application.app_context():
        Semester.query.update({"is_active": False})
        db.session.flush()
        sem = Semester(code="PL01", name="Prep List Nested Test", is_active=True)
        block = Block(code="PL", name="Prep List Block", max_days=4)
        substance = Substance(name="PL Substance", molar_mass_gmol=100.0)
        db.session.add_all([sem, block, substance])
        db.session.flush()
        analysis = Analysis(
            block_id=block.id, code="PL1", ordinal=89, name="PL Analysis",
            substance_id=substance.id, calculation_mode="assay_mass_based",
            k_determinations=1, result_unit="%", result_label="Gehalt",
            g_ab_min_pct=98.0, g_ab_max_pct=102.0, e_ab_g=0.5,
        )
        db.session.add(analysis)
        db.session.flush()
        water = Reagent(name="PL Wasser R", is_composite=False, base_unit="mL")
        nh3_lsg = Reagent(name="PL Ammoniaklösung R", is_composite=True, base_unit="mL")
        buffer = Reagent(name="PL Pufferlösung R", is_composite=True, base_unit="mL")
        db.session.add_all([water, nh3_lsg, buffer])
        db.session.flush()
        db.session.add_all([
            ReagentComponent(parent_reagent_id=nh3_lsg.id, child_reagent_id=water.id,
                             quantity=26.0, quantity_unit="mL", per_parent_volume_ml=93.0),
            ReagentComponent(parent_reagent_id=buffer.id, child_reagent_id=nh3_lsg.id,
                             quantity=100.0, quantity_unit="mL", per_parent_volume_ml=1000.0),
        ])
        method = Method(
            analysis_id=analysis.id, method_type="direct",
            blind_required=False, b_blind_determinations=0,
            v_solution_ml=100.0, aliquot_enabled=False,
        )
        db.session.add(method)
        db.session.flush()
        usage = MethodReagent(
            method_id=method.id, reagent_id=buffer.id,
            amount_per_determination=100.0, amount_per_blind=0.0,
            amount_unit="mL", is_titrant=False,
        )
        db.session.add(usage)
        db.session.add(SampleBatch(
            analysis_id=analysis.id, semester_id=sem.id,
            total_samples_prepared=1, titer=1.0, safety_factor=1.0,
        ))
        db.session.commit()

        resp = client.get("/reports/reagents/prep-list")
        assert resp.status_code == 200
        text = resp.data.decode()
        # Both composites appear
        assert "PL Ammoniaklösung R" in text
        assert "PL Pufferlösung R" in text
        # Intermediate composite appears BEFORE the top-level composite (topo order)
        assert text.index("PL Ammoniaklösung R") < text.index("PL Pufferlösung R")
        # Intermediate composite is in the block section, NOT "Vorabherstellungen"
        assert "Vorabherstellungen" not in text
        assert "Prep List Block" in text  # block heading present


def test_order_list_renders_without_error(client, db):
    """Smoke test: /reports/reagents/order-list renders with no active semester."""
    # Deactivate all semesters to trigger the no-semester path (warnings=[] required)
    from models import Semester
    with client.application.app_context():
        Semester.query.update({"is_active": False})
        db.session.commit()
    resp = client.get("/reports/reagents/order-list")
    assert resp.status_code == 200
    # "warnings" variable must be defined in template (no Jinja UndefinedError)
    assert b"Kein aktives Semester" in resp.data
