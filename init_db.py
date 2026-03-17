"""Initialise or reset the Quanti-LIMS database with reference data."""

from datetime import date
from models import (
    db, Block, Substance, SubstanceLot, Analysis, Method,
    Reagent, ReagentComponent, MethodReagent,
    Semester, Student, SampleBatch, Sample, SampleAssignment,
)
from calculation_modes import MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION


def seed_database():
    """Populate reference data. Safe to call repeatedly (skips if data exists)."""
    if Block.query.first():
        return  # already seeded

    # ── Blöcke ─────────────────────────────────────────────────────
    blocks = {
        "I":   Block(code="I",   name="Acidimetrie"),
        "II":  Block(code="II",  name="Oxidimetrie"),
        "III": Block(code="III", name="Komplexometrie, Argentometrie, Gravimetrie"),
    }
    for b in blocks.values():
        db.session.add(b)
    db.session.flush()

    # ── Substanzen ─────────────────────────────────────────────────
    substances = {}
    sub_data = [
        ("Salzsäure 0,1 mol/L",              "HCl",            36.461,  None,  None,  None),
        ("Acetylsalicylsäure",                "C₉H₈O₄",        180.16,  1.000, 99.5,  101.0),
        ("Natriumtetraborat",                 "Na₂B₄O₇·10H₂O", 381.37, 0.200, 99.0,  101.0),
        ("Lithiumcitrat",                     "Li₃C₆H₅O₇·4H₂O", 282.00, 0.300, 99.0, 101.0),
        ("Ascorbinsäure",                     "C₆H₈O₆",        176.12,  0.150, 99.0,  100.5),
        ("Kaliumiodid",                       "KI",             166.00,  0.500, 99.0,  100.5),
        ("Glycerol",                          "C₃H₈O₃",        92.09,   1.000, 98.0,  101.0),
        ("Resorcin",                          "C₆H₆O₂",        110.11,  0.200, 99.0,  101.0),
        ("Dinatriumhydrogenphosphat-Dihydrat", "Na₂HPO₄·2H₂O", 177.99, 0.300, 98.0,  101.0),
        ("Kaliumbromid",                      "KBr",            119.00,  0.100, 99.0,  100.5),
        ("Theophyllin",                       "C₇H₈N₄O₂",     180.16,  0.200, 99.0,  101.0),
        ("Glucose-Monohydrat",                "C₆H₁₂O₆·H₂O",  198.17,  1.000, None,  None),
        ("Natriumcarbonat",                   "Na₂CO₃",         105.99,  None,  None,  None),
        ("Trometamol",                        "C₄H₁₁NO₃",      121.14,  None,  None,  None),
    ]
    for name, formula, mm, e_ab, g_min, g_max in sub_data:
        s = Substance(name=name, formula=formula, molar_mass_gmol=mm,
                      e_ab_g=e_ab, g_ab_min_pct=g_min, g_ab_max_pct=g_max)
        db.session.add(s)
        substances[name] = s
    db.session.flush()

    # ── Analysen ───────────────────────────────────────────────────
    analyses = {}
    ana_data = [
        ("I",   "I.1",   1,  "Einstellung Salzsäure 0,1 mol/L",  "Salzsäure 0,1 mol/L",              3, "Faktor", "Titer",            99.0, 101.0, MODE_TITRANT_STANDARDIZATION),
        ("I",   "I.2",   2,  "Acetylsalicylsäure",                "Acetylsalicylsäure",                3, "%",      "Gehalt",           98.0, 102.0),
        ("I",   "I.3",   3,  "Natriumtetraborat",                 "Natriumtetraborat",                 3, "%",      "Gehalt",           98.0, 102.0),
        ("I",   "I.4",   4,  "Lithiumcitrat",                     "Lithiumcitrat",                     3, "%",      "Gehalt",           98.0, 102.0),
        ("II",  "II.1",  5,  "Ascorbinsäure",                     "Ascorbinsäure",                     3, "%",      "Gehalt",           98.0, 102.0),
        ("II",  "II.2",  6,  "Kaliumiodid",                       "Kaliumiodid",                       3, "%",      "Gehalt",           98.0, 102.0),
        ("II",  "II.3",  7,  "Glycerol",                          "Glycerol",                          3, "mg",     "Masse Glycerol",   98.0, 102.0),
        ("II",  "II.4",  8,  "Resorcin",                          "Resorcin",                          3, "%",      "Gehalt",           98.0, 102.0),
        ("III", "III.1", 9,  "Phosphorgehalt (Na₂HPO₄·2H₂O)",    "Dinatriumhydrogenphosphat-Dihydrat", 2, "%",     "Phosphorgehalt",   98.0, 102.0),
        ("III", "III.2", 10, "Kaliumbromid (nach Volhard)",        "Kaliumbromid",                      3, "%",      "Gehalt",           98.0, 102.0),
        ("III", "III.3", 11, "Theophyllin",                       "Theophyllin",                       3, "%",      "Gehalt",           98.0, 102.0),
        ("III", "III.4", 12, "Trocknungsverlust (Glucose-MH)",    "Glucose-Monohydrat",                3, "%",      "Trocknungsverlust", 98.0, 102.0),
    ]
    for row in ana_data:
        if len(row) == 10:
            blk, code, ordinal, name, sub_name, k, unit, label, tmin, tmax = row
            mode = MODE_ASSAY_MASS_BASED
        else:
            blk, code, ordinal, name, sub_name, k, unit, label, tmin, tmax, mode = row
        a = Analysis(
            block=blocks[blk], code=code, ordinal=ordinal, name=name,
            substance=substances[sub_name], k_determinations=k,
            result_unit=unit, result_label=label, calculation_mode=mode,
            e_ab_g=substances[sub_name].e_ab_g,
            g_ab_min_pct=substances[sub_name].g_ab_min_pct,
            g_ab_max_pct=substances[sub_name].g_ab_max_pct,
            tolerance_override_min_pct=tmin, tolerance_override_max_pct=tmax,
        )
        db.session.add(a)
        analyses[code] = a
    db.session.flush()

    # ── Methoden (exemplarisch) ────────────────────────────────────
    methods = {}
    meth_data = [
        ("I.1",  "direct",   3.646, "Salzsäure",          "0,1 mol/L",  False, 0, None),
        ("I.2",  "back",     45.04, "Salzsäure",          "0,5 mol/L",  True,  1, 50.0),
        ("I.3",  "direct",   19.07, "Salzsäure",          "0,1 mol/L",  False, 0, None),
        ("I.4",  "direct",   9.403, "Salzsäure",          "0,1 mol/L",  False, 0, None),
        ("II.1", "direct",    8.81, "Iod-Lösung",         "0,05 mol/L", False, 0, None),
        ("II.2", "direct",   None,  "Silbernitrat-Lösung", "0,1 mol/L", False, 0, None),
        ("II.3", "back",     None,  "Natriumthiosulfat",   "0,1 mol/L", True,  1, None),
        ("II.4", "back",     None,  "Natriumthiosulfat",   "0,1 mol/L", True,  2, None),
        ("III.1","complexometric", None, "Zinksulfat-Lösung", "0,1 mol/L", False, 0, None),
        ("III.2","argentometric",  None, "Ammoniumthiocyanat", "0,1 mol/L", False, 0, None),
        ("III.3","direct",   None,  "Perchlorsäure",       "0,1 mol/L", False, 0, None),
        ("III.4","gravimetric",    None, None,              None,          False, 0, None),
    ]
    for acode, mtype, meq, tname, tconc, blind, b_det, vorlage in meth_data:
        m = Method(
            analysis=analyses[acode], method_type=mtype, m_eq_mg=meq,
            titrant_name=tname, titrant_concentration=tconc,
            blind_required=blind, b_blind_determinations=b_det,
            v_vorlage_ml=vorlage,
        )
        db.session.add(m)
        methods[acode] = m
    db.session.flush()

    # ── Explicit titration parameters ───────────────────────────────
    # I.1: HCl 0.1 mol/L – direct titration of Na2B4O7 (2 eq per mol)
    methods["I.1"].c_titrant_mol_l = 0.1
    methods["I.1"].n_eq_titrant = 2.0

    # I.2: ASS back-titration – 50 mL NaOH 0.5M added, 2 eq NaOH per mol ASS, back-titrate with HCl 0.5M
    methods["I.2"].c_titrant_mol_l = 0.5
    methods["I.2"].n_eq_titrant = 1.0
    methods["I.2"].c_vorlage_mol_l = 0.5
    methods["I.2"].n_eq_vorlage = 2.0

    # I.3: Natriumhydrogencarbonat – direct titration with HCl 0.1 mol/L (1 eq)
    methods["I.3"].c_titrant_mol_l = 0.1
    methods["I.3"].n_eq_titrant = 1.0

    # I.4: Natriumcarbonat – direct titration with HCl 0.1 mol/L (2 eq per mol)
    methods["I.4"].c_titrant_mol_l = 0.1
    methods["I.4"].n_eq_titrant = 2.0

    # II.1: Ascorbinsäure – direct titration with I2 0.05 mol/L (1 eq per mol)
    methods["II.1"].c_titrant_mol_l = 0.05
    methods["II.1"].n_eq_titrant = 1.0

    # ── Reagenzien (Beispiel-Katalog) ──────────────────────────────
    reagents = {}
    reag_data = [
        # Grundchemikalien / Primärstandards
        ("Ethanol 96 % R",          "EtOH 96%",   False, "mL", None),
        ("Natriumhydroxid-Lösung 0,5 mol/L", "NaOH 0,5M", False, "mL", None),
        ("Salzsäure 0,5 mol/L",     "HCl 0,5M",   False, "mL", None),
        ("Phenolphthalein-Lösung R", "PhPh",       False, "mL", None),
        ("Iod-Lösung 0,05 mol/L",   "I₂ 0,05M",   False, "mL", None),
        ("Verdünnte Schwefelsäure R", "H₂SO₄ verd.", True, "mL", None),
        ("Kohlendioxidfreies Wasser R", "CO₂-frei H₂O", False, "mL", None),
        ("Stärke-Lösung R",         "Stärke",      True,  "mL", None),
        ("Schwefelsäure konz.",      "H₂SO₄ konz.", False, "mL", None),
        ("Wasser R",                "H₂O R",       False, "mL", None),
        ("Stärke",                  "Stärke (fest)", False, "g", None),
        ("Natriumthiosulfat-Lösung 0,1 mol/L", "Na₂S₂O₃ 0,1M", False, "mL", None),
        ("Kaliumbromat-Lösung 0,0167 mol/L", "KBrO₃", False, "mL", None),
        ("Kaliumbromid R",          "KBr R",        False, "g",  None),
        ("Chloroform R",            "CHCl₃",        False, "mL", None),
        ("Salzsäure R 1",           "HCl R 1",      False, "mL", None),
        ("Kaliumiodid R Lösung 100 g/L", "KI 10%",  False, "mL", None),
        ("EDTA-Lösung 0,1 mol/L",   "EDTA 0,1M",   False, "mL", None),
        ("Zinksulfat-Lösung 0,1 mol/L", "ZnSO₄ 0,1M", False, "mL", None),
        ("Magnesiumsulfat-Lösung 1 mol/L", "MgSO₄ 1M", False, "mL", None),
        ("Ammoniak konz.",          "NH₃ konz.",    False, "mL", None),
        ("Ammoniaklösung 1 mol/L",  "NH₃ 1M",      False, "mL", None),
        ("Salzsäure konz.",         "HCl konz.",    False, "mL", None),
        ("Methylrot 0,1 % in Ethanol", "MR",        False, "mL", None),
        ("Eriochromschwarz-T-Verreibung", "EBT",     False, "g",  None),
    ]
    for name, abbrev, composite, unit, cas in reag_data:
        r = Reagent(name=name, abbreviation=abbrev, is_composite=composite,
                    base_unit=unit, cas_number=cas)
        db.session.add(r)
        reagents[name] = r

    # ── Primärstandards / Urtitersubstanzen ──────────────────────
    ps_data = [
        ("Natriumtetraborat (Primärstandard)", "Na₂B₄O₇", "Na₂B₄O₇·10H₂O", 381.37, 0.200, "g"),
        ("Natriumcarbonat (Primärstandard)",   "Na₂CO₃",  "Na₂CO₃",          105.99, None,  "g"),
        ("Trometamol (Primärstandard)",        "TRIS",     "C₄H₁₁NO₃",       121.14, None,  "g"),
    ]
    for name, abbrev, formula, mm, e_ab, unit in ps_data:
        r = Reagent(name=name, abbreviation=abbrev, is_primary_standard=True,
                    formula=formula, molar_mass_gmol=mm, e_ab_g=e_ab, base_unit=unit)
        db.session.add(r)
        reagents[name] = r

    db.session.flush()

    # Primary standard for titrant standardization (I.1: HCl standardized with Na2B4O7)
    # Na2B4O7·10H2O: MW=381.37, 2 equiv → m_eq_primary = 381.37/2 × 0.1 = 19.069 mg/mL
    methods["I.1"].primary_standard = reagents["Natriumtetraborat (Primärstandard)"]
    methods["I.1"].m_eq_primary_mg = 19.069

    # ── BOM: Verdünnte Schwefelsäure R ─────────────────────────────
    db.session.add(ReagentComponent(
        parent=reagents["Verdünnte Schwefelsäure R"],
        child=reagents["Schwefelsäure konz."],
        quantity=5.7, quantity_unit="mL", per_parent_volume_ml=100.0,
    ))
    db.session.add(ReagentComponent(
        parent=reagents["Verdünnte Schwefelsäure R"],
        child=reagents["Wasser R"],
        quantity=94.3, quantity_unit="mL", per_parent_volume_ml=100.0,
    ))

    # ── BOM: Stärke-Lösung R ──────────────────────────────────────
    db.session.add(ReagentComponent(
        parent=reagents["Stärke-Lösung R"],
        child=reagents["Stärke"],
        quantity=1.0, quantity_unit="g", per_parent_volume_ml=100.0,
    ))
    db.session.add(ReagentComponent(
        parent=reagents["Stärke-Lösung R"],
        child=reagents["Wasser R"],
        quantity=100.0, quantity_unit="mL", per_parent_volume_ml=100.0,
    ))

    # ── Reagenzien pro Methode (ASS & Ascorbinsäure als Beispiel) ──
    # ASS (I.2): back titration
    mr_data_ass = [
        ("Ethanol 96 % R",                     10.0, 10.0, False),
        ("Natriumhydroxid-Lösung 0,5 mol/L",   50.0, 50.0, False),
        ("Phenolphthalein-Lösung R",            0.2,  0.2,  False),
        ("Salzsäure 0,5 mol/L",                 25.0, 50.0, True),  # ~25 mL Verbrauch, 50 mL Blind
    ]
    for rname, vol_det, vol_blind, is_tit in mr_data_ass:
        db.session.add(MethodReagent(
            method=methods["I.2"], reagent=reagents[rname],
            amount_per_determination=vol_det, amount_per_blind=vol_blind,
            amount_unit="mL",
            is_titrant=is_tit,
        ))

    # Ascorbinsäure (II.1): direct titration
    mr_data_asc = [
        ("Verdünnte Schwefelsäure R",   10.0, 0, False),
        ("Kohlendioxidfreies Wasser R", 80.0, 0, False),
        ("Stärke-Lösung R",            1.0,  0, False),
        ("Iod-Lösung 0,05 mol/L",      3.0,  0, True),  # ~2.5 mL Verbrauch
    ]
    for rname, vol_det, vol_blind, is_tit in mr_data_asc:
        db.session.add(MethodReagent(
            method=methods["II.1"], reagent=reagents[rname],
            amount_per_determination=vol_det, amount_per_blind=vol_blind,
            amount_unit="mL",
            is_titrant=is_tit,
        ))

    # Resorcin (II.4): back titration with mandatory blind
    mr_data_res = [
        ("Kaliumbromid R",                       1.0,  1.0,  False),
        ("Kaliumbromat-Lösung 0,0167 mol/L",     50.0, 50.0, False),
        ("Chloroform R",                         15.0, 15.0, False),
        ("Salzsäure R 1",                        15.0, 15.0, False),
        ("Kaliumiodid R Lösung 100 g/L",         10.0, 10.0, False),
        ("Stärke-Lösung R",                      1.0,  1.0,  False),
        ("Natriumthiosulfat-Lösung 0,1 mol/L",   15.0, 50.0, True),
    ]
    for rname, vol_det, vol_blind, is_tit in mr_data_res:
        db.session.add(MethodReagent(
            method=methods["II.4"], reagent=reagents[rname],
            amount_per_determination=vol_det, amount_per_blind=vol_blind,
            amount_unit="mL",
            is_titrant=is_tit,
        ))

    # ── Demo-Semester mit Studierenden ─────────────────────────────
    sem = Semester(code="WS2025/26", name="Wintersemester 2025/26",
                   start_date="2025-10-13", end_date="2026-02-13", is_active=True)
    db.session.add(sem)
    db.session.flush()

    # Beispiel-Chargen
    lot_ass = SubstanceLot(substance=substances["Acetylsalicylsäure"],
                           lot_number="ASS-2025-001", supplier="Sigma-Aldrich",
                           g_coa_pct=99.8, coa_date="2025-06-15")
    lot_asc = SubstanceLot(substance=substances["Ascorbinsäure"],
                           lot_number="ASC-2025-001", supplier="Merck",
                           g_coa_pct=99.5, coa_date="2025-07-01")
    db.session.add(lot_ass)
    db.session.add(lot_asc)
    db.session.flush()

    # 5 Demo-Studierende
    demo_students = [
        ("2345678", "Müller",    "Anna"),
        ("2345679", "Schmidt",   "Ben"),
        ("2345680", "Weber",     "Clara"),
        ("2345681", "Fischer",   "David"),
        ("2345682", "Wagner",    "Elena"),
    ]
    students = []
    for i, (mat, ln, fn) in enumerate(demo_students, 1):
        st = Student(semester=sem, matrikel=mat, last_name=ln,
                     first_name=fn, running_number=i)
        db.session.add(st)
        students.append(st)
    db.session.flush()

    # Demo-Batches (ASS und Ascorbinsäure)
    batch_ass = SampleBatch(
        semester=sem, analysis=analyses["I.2"], substance_lot=lot_ass,
        target_m_s_min_g=3.0, target_m_ges_g=6.0, titer=1.000,
        total_samples_prepared=10, preparation_date="2025-10-01",
        prepared_by="TA Demo",
    )
    db.session.add(batch_ass)
    db.session.flush()

    # Erstproben (1-5) + Pufferproben (6-10)
    import random
    random.seed(42)
    for i in range(1, 11):
        m_s = round(random.uniform(2.95, 3.10), 4)
        m_ges = round(random.uniform(5.95, 6.05), 4)
        s = Sample(
            batch=batch_ass, running_number=i,
            m_s_actual_g=m_s, m_ges_actual_g=m_ges,
            is_buffer=(i > 5),
            weighed_by="TA Demo", weighed_date="2025-10-01",
        )
        db.session.add(s)
    db.session.flush()

    # Erstanalysen zuweisen (Student k → Probe k)
    samples_ass = Sample.query.filter_by(batch_id=batch_ass.id).order_by(Sample.running_number).all()
    for st in students:
        sample = samples_ass[st.running_number - 1]
        sa = SampleAssignment(
            sample=sample, student=st, attempt_number=1, attempt_type="A",
            assigned_date=date.today().isoformat(), assigned_by="System",
            status="assigned",
        )
        db.session.add(sa)

    db.session.commit()
    print("✅ Datenbank erfolgreich initialisiert mit Referenz- und Demo-Daten.")
