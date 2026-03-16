"""Quanti-LIMS – Flask Application."""

from __future__ import annotations

import csv
import io
from functools import wraps
from datetime import date
from sqlalchemy.exc import IntegrityError

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify,
)
from config import Config
from models import (
    db, Block, Substance, SubstanceLot, Analysis, Method,
    Reagent, ReagentComponent, MethodReagent,
    Semester, Student, SampleBatch, Sample, SampleAssignment, Result,
)
from calculation_modes import MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION, resolve_mode



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        from init_db import seed_database
        seed_database()

    register_routes(app)
    register_filters(app)
    return app


def register_filters(app):
    @app.template_filter("fmt")
    def fmt_number(value, decimals=4):
        if value is None:
            return "–"
        return f"{value:.{decimals}f}"

    @app.template_filter("zip")
    def zip_filter(a, b):
        return list(zip(a, b))

    @app.template_global("options_for")
    def options_for(items, value_attr="id", label_attr="name"):
        """Build select options from a list of ORM objects."""
        return [(getattr(i, value_attr), getattr(i, label_attr)) for i in items]


def register_routes(app):
    # ─── Helper ──────────────────────────────────────────────────
    def active_semester():
        return Semester.query.filter_by(is_active=True).first()

    def require_active_semester(redirect_endpoint="dashboard"):
        """Guard semester-dependent routes when no active semester is configured."""
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                if active_semester():
                    return view(*args, **kwargs)
                flash(
                    "Kein aktives Semester gefunden. Bitte zuerst ein Semester aktivieren.",
                    "danger",
                )
                return redirect(url_for(redirect_endpoint))

            return wrapped

        return decorator

    # ═══════════════════════════════════════════════════════════════
    # DASHBOARD
    # ═══════════════════════════════════════════════════════════════
    @app.route("/")
    def dashboard():
        sem = active_semester()
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        batches = {}
        if sem:
            for b in SampleBatch.query.filter_by(semester_id=sem.id).all():
                batches[b.analysis_id] = b
        return render_template("dashboard.html", semester=sem, analyses=analyses, batches=batches)

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Substances
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/substances")
    def admin_substances():
        items = Substance.query.order_by(Substance.name).all()
        return render_template("admin/substances.html", items=items)

    @app.route("/admin/substances/new", methods=["GET", "POST"])
    @app.route("/admin/substances/<int:id>/edit", methods=["GET", "POST"])
    def admin_substance_form(id=None):
        item = Substance.query.get(id) if id else Substance()
        if request.method == "POST":
            item.name = request.form["name"]
            item.formula = request.form.get("formula") or None
            item.molar_mass_gmol = _float(request.form.get("molar_mass_gmol"))
            item.e_ab_g = _float(request.form.get("e_ab_g"))
            item.g_ab_min_pct = _float(request.form.get("g_ab_min_pct"))
            item.g_ab_max_pct = _float(request.form.get("g_ab_max_pct"))
            item.notes = request.form.get("notes") or None
            duplicate = Substance.query.filter(
                Substance.name == item.name,
                Substance.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Eine Substanz mit diesem Namen existiert bereits.", "danger")
                return render_template("admin/substance_form.html", item=item)
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash("Substanz gespeichert.", "success")
                return redirect(url_for("admin_substances"))
            except IntegrityError:
                db.session.rollback()
                flash("Substanz konnte nicht gespeichert werden (Name ist bereits vergeben).", "danger")
        return render_template("admin/substance_form.html", item=item)

    @app.route("/admin/substances/<int:id>/delete", methods=["POST"])
    def admin_substance_delete(id):
        db.session.delete(Substance.query.get_or_404(id))
        db.session.commit()
        flash("Substanz gelöscht.", "warning")
        return redirect(url_for("admin_substances"))

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Substance Lots
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/lots")
    def admin_lots():
        items = SubstanceLot.query.order_by(SubstanceLot.id.desc()).all()
        return render_template("admin/lots.html", items=items)

    @app.route("/admin/lots/new", methods=["GET", "POST"])
    @app.route("/admin/lots/<int:id>/edit", methods=["GET", "POST"])
    def admin_lot_form(id=None):
        item = SubstanceLot.query.get(id) if id else SubstanceLot()
        substances = Substance.query.order_by(Substance.name).all()
        if request.method == "POST":
            item.substance_id = int(request.form["substance_id"])
            item.lot_number = request.form["lot_number"]
            item.supplier = request.form.get("supplier") or None
            item.receipt_date = request.form.get("receipt_date") or None
            item.g_coa_pct = _float(request.form.get("g_coa_pct"))
            item.coa_date = request.form.get("coa_date") or None
            item.coa_valid_until = request.form.get("coa_valid_until") or None
            item.g_analytical_pct = _float(request.form.get("g_analytical_pct"))
            item.g_analytical_date = request.form.get("g_analytical_date") or None
            item.g_analytical_method = request.form.get("g_analytical_method") or None
            item.notes = request.form.get("notes") or None
            duplicate = SubstanceLot.query.filter(
                SubstanceLot.substance_id == item.substance_id,
                SubstanceLot.lot_number == item.lot_number,
                SubstanceLot.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Diese Chargennummer existiert für die gewählte Substanz bereits.", "danger")
                sub_opts = [(s.id, s.name) for s in substances]
                return render_template("admin/lot_form.html", item=item, sub_opts=sub_opts)
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash("Charge gespeichert.", "success")
                return redirect(url_for("admin_lots"))
            except IntegrityError:
                db.session.rollback()
                flash("Charge konnte nicht gespeichert werden (Substanz + Chargennummer muss eindeutig sein).", "danger")
        sub_opts = [(s.id, s.name) for s in substances]
        return render_template("admin/lot_form.html", item=item, sub_opts=sub_opts)

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Analyses
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/analyses")
    def admin_analyses():
        items = Analysis.query.order_by(Analysis.ordinal).all()
        return render_template("admin/analyses.html", items=items)

    @app.route("/admin/analyses/new", methods=["GET", "POST"])
    @app.route("/admin/analyses/<int:id>/edit", methods=["GET", "POST"])
    def admin_analysis_form(id=None):
        item = Analysis.query.get(id) if id else Analysis()
        blocks = Block.query.order_by(Block.code).all()
        substances = Substance.query.order_by(Substance.name).all()
        if request.method == "POST":
            item.block_id = int(request.form["block_id"])
            item.code = request.form["code"]
            item.ordinal = int(request.form["ordinal"])
            item.name = request.form["name"]
            item.substance_id = int(request.form["substance_id"])
            item.k_determinations = int(request.form.get("k_determinations", 3))
            item.result_unit = request.form.get("result_unit", "%")
            item.result_label = request.form.get("result_label", "Gehalt")
            item.calculation_mode = request.form.get("calculation_mode", MODE_ASSAY_MASS_BASED)
            item.tolerance_override_min_pct = _float(request.form.get("tolerance_override_min_pct"))
            item.tolerance_override_max_pct = _float(request.form.get("tolerance_override_max_pct"))
            item.notes = request.form.get("notes") or None
            duplicate = Analysis.query.filter(
                Analysis.code == item.code,
                Analysis.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Der Analyse-Code ist bereits vergeben.", "danger")
                block_opts = [(b.id, b.code) for b in blocks]
                sub_opts = [(s.id, s.name) for s in substances]
                mode_opts = [
                    (MODE_ASSAY_MASS_BASED, "assay_mass_based"),
                    (MODE_TITRANT_STANDARDIZATION, "titrant_standardization"),
                ]
                return render_template("admin/analysis_form.html", item=item, block_opts=block_opts, sub_opts=sub_opts, mode_opts=mode_opts)
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash("Analyse gespeichert.", "success")
                return redirect(url_for("admin_analyses"))
            except IntegrityError:
                db.session.rollback()
                flash("Analyse konnte nicht gespeichert werden (Code ist bereits vergeben).", "danger")
        block_opts = [(b.id, b.code) for b in blocks]
        sub_opts = [(s.id, s.name) for s in substances]
        mode_opts = [
            (MODE_ASSAY_MASS_BASED, "assay_mass_based"),
            (MODE_TITRANT_STANDARDIZATION, "titrant_standardization"),
        ]
        return render_template("admin/analysis_form.html", item=item, block_opts=block_opts, sub_opts=sub_opts, mode_opts=mode_opts)

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Methods
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/methods")
    def admin_methods():
        items = Method.query.join(Analysis).order_by(Analysis.ordinal).all()
        return render_template("admin/methods.html", items=items)

    @app.route("/admin/methods/new", methods=["GET", "POST"])
    @app.route("/admin/methods/<int:id>/edit", methods=["GET", "POST"])
    def admin_method_form(id=None):
        item = Method.query.get(id) if id else Method()
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        if request.method == "POST":
            item.analysis_id = int(request.form["analysis_id"])
            item.method_type = request.form["method_type"]
            item.m_eq_mg = _float(request.form.get("m_eq_mg"))
            item.titrant_name = request.form.get("titrant_name") or None
            item.titrant_concentration = request.form.get("titrant_concentration") or None
            item.blind_required = "blind_required" in request.form
            item.b_blind_determinations = int(request.form.get("b_blind_determinations", 1))
            item.v_vorlage_ml = _float(request.form.get("v_vorlage_ml"))
            item.description = request.form.get("description") or None
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash("Methode gespeichert.", "success")
                return redirect(url_for("admin_methods"))
            except IntegrityError:
                db.session.rollback()
                flash("Methode konnte nicht gespeichert werden (Integritätsfehler).", "danger")
        ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
        return render_template("admin/method_form.html", item=item, ana_opts=ana_opts)

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Reagents
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/reagents")
    def admin_reagents():
        items = Reagent.query.order_by(Reagent.name).all()
        return render_template("admin/reagents.html", items=items)

    @app.route("/admin/reagents/new", methods=["GET", "POST"])
    @app.route("/admin/reagents/<int:id>/edit", methods=["GET", "POST"])
    def admin_reagent_form(id=None):
        item = Reagent.query.get(id) if id else Reagent()
        if request.method == "POST":
            item.name = request.form["name"]
            item.abbreviation = request.form.get("abbreviation") or None
            item.is_composite = "is_composite" in request.form
            item.base_unit = request.form.get("base_unit", "mL")
            item.cas_number = request.form.get("cas_number") or None
            item.density_g_ml = _float(request.form.get("density_g_ml"))
            item.hazard_symbols = request.form.get("hazard_symbols") or None
            item.storage_info = request.form.get("storage_info") or None
            item.notes = request.form.get("notes") or None
            duplicate = Reagent.query.filter(
                Reagent.name == item.name,
                Reagent.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Eine Reagenz mit diesem Namen existiert bereits.", "danger")
                return render_template("admin/reagent_form.html", item=item)
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash("Reagenz gespeichert.", "success")
                return redirect(url_for("admin_reagents"))
            except IntegrityError:
                db.session.rollback()
                flash("Reagenz konnte nicht gespeichert werden (Name ist bereits vergeben).", "danger")
        return render_template("admin/reagent_form.html", item=item)

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Reagent Components (BOM)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/reagents/<int:reagent_id>/components")
    def admin_reagent_components(reagent_id):
        parent = Reagent.query.get_or_404(reagent_id)
        reagents = Reagent.query.filter(Reagent.id != reagent_id).order_by(Reagent.name).all()
        reag_opts = [(r.id, r.name) for r in reagents]
        return render_template("admin/reagent_components.html", parent=parent, reag_opts=reag_opts)

    @app.route("/admin/reagents/<int:reagent_id>/components/add", methods=["POST"])
    def admin_reagent_component_add(reagent_id):
        rc = ReagentComponent(
            parent_reagent_id=reagent_id,
            child_reagent_id=int(request.form["child_reagent_id"]),
            quantity=float(request.form["quantity"]),
            quantity_unit=request.form["quantity_unit"],
            per_parent_volume_ml=_float(request.form.get("per_parent_volume_ml")),
        )
        db.session.add(rc)
        try:
            db.session.commit()
            flash("Komponente hinzugefügt.", "success")
            return redirect(url_for("admin_reagent_components", reagent_id=reagent_id))
        except IntegrityError:
            db.session.rollback()
            flash("Komponente konnte nicht hinzugefügt werden (Integritätsfehler).", "danger")
            return redirect(url_for("admin_reagent_components", reagent_id=reagent_id))

    @app.route("/admin/reagent-components/<int:id>/delete", methods=["POST"])
    def admin_reagent_component_delete(id):
        rc = ReagentComponent.query.get_or_404(id)
        rid = rc.parent_reagent_id
        db.session.delete(rc)
        db.session.commit()
        flash("Komponente entfernt.", "warning")
        return redirect(url_for("admin_reagent_components", reagent_id=rid))

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Method Reagents
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/methods/<int:method_id>/reagents")
    def admin_method_reagents(method_id):
        method = Method.query.get_or_404(method_id)
        reagents = Reagent.query.order_by(Reagent.name).all()
        reag_opts = [(r.id, r.name) for r in reagents]
        return render_template("admin/method_reagents.html", method=method, reag_opts=reag_opts)

    @app.route("/admin/methods/<int:method_id>/reagents/add", methods=["POST"])
    def admin_method_reagent_add(method_id):
        mr = MethodReagent(
            method_id=method_id,
            reagent_id=int(request.form["reagent_id"]),
            volume_per_determination_ml=float(request.form["volume_per_determination_ml"]),
            volume_per_blind_ml=float(request.form.get("volume_per_blind_ml", 0)),
            is_titrant="is_titrant" in request.form,
            step_description=request.form.get("step_description") or None,
        )
        db.session.add(mr)
        try:
            db.session.commit()
            flash("Reagenz-Zuordnung hinzugefügt.", "success")
            return redirect(url_for("admin_method_reagents", method_id=method_id))
        except IntegrityError:
            db.session.rollback()
            flash("Reagenz-Zuordnung konnte nicht hinzugefügt werden (Integritätsfehler).", "danger")
            return redirect(url_for("admin_method_reagents", method_id=method_id))

    @app.route("/admin/method-reagents/<int:id>/delete", methods=["POST"])
    def admin_method_reagent_delete(id):
        mr = MethodReagent.query.get_or_404(id)
        mid = mr.method_id
        db.session.delete(mr)
        db.session.commit()
        flash("Zuordnung entfernt.", "warning")
        return redirect(url_for("admin_method_reagents", method_id=mid))

    # ═══════════════════════════════════════════════════════════════
    # SEMESTER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/semesters")
    def admin_semesters():
        items = Semester.query.order_by(Semester.id.desc()).all()
        return render_template("admin/semesters.html", items=items)

    @app.route("/admin/semesters/new", methods=["GET", "POST"])
    @app.route("/admin/semesters/<int:id>/edit", methods=["GET", "POST"])
    def admin_semester_form(id=None):
        item = Semester.query.get(id) if id else Semester()
        if request.method == "POST":
            item.code = request.form["code"]
            item.name = request.form["name"]
            item.start_date = request.form.get("start_date") or None
            item.end_date = request.form.get("end_date") or None
            item.is_active = "is_active" in request.form
            duplicate = Semester.query.filter(
                Semester.code == item.code,
                Semester.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Der Semester-Code ist bereits vergeben.", "danger")
                return render_template("admin/semester_form.html", item=item)
            if not id:
                db.session.add(item)
            # Deactivate other semesters if this one is active
            if item.is_active:
                Semester.query.filter(Semester.id != item.id).update({"is_active": False})
            try:
                db.session.commit()
                flash("Semester gespeichert.", "success")
                return redirect(url_for("admin_semesters"))
            except IntegrityError:
                db.session.rollback()
                flash("Semester konnte nicht gespeichert werden (Code ist bereits vergeben).", "danger")
        return render_template("admin/semester_form.html", item=item)

    # ═══════════════════════════════════════════════════════════════
    # STUDENTS
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/students")
    def admin_students():
        sem = active_semester()
        students = Student.query.filter_by(semester_id=sem.id).order_by(Student.running_number).all() if sem else []
        return render_template("admin/students.html", students=students, semester=sem)

    @app.route("/admin/students/new", methods=["GET", "POST"])
    @app.route("/admin/students/<int:id>/edit", methods=["GET", "POST"])
    @require_active_semester("admin_students")
    def admin_student_form(id=None):
        item = Student.query.get(id) if id else Student()
        sem = active_semester()
        if request.method == "POST":
            item.semester_id = sem.id
            item.matrikel = request.form["matrikel"]
            item.last_name = request.form["last_name"]
            item.first_name = request.form["first_name"]
            item.running_number = int(request.form["running_number"])
            item.email = request.form.get("email") or None
            item.notes = request.form.get("notes") or None
            duplicate_matrikel = Student.query.filter(
                Student.semester_id == sem.id,
                Student.matrikel == item.matrikel,
                Student.id != (item.id or 0),
            ).first()
            if duplicate_matrikel:
                flash("Die Matrikelnummer existiert in diesem Semester bereits.", "danger")
                next_num = 1
                if sem:
                    max_num = db.session.query(db.func.max(Student.running_number)).filter_by(semester_id=sem.id).scalar()
                    next_num = (max_num or 0) + 1
                return render_template("admin/student_form.html", item=item, semester=sem, next_num=next_num)

            duplicate_running_number = Student.query.filter(
                Student.semester_id == sem.id,
                Student.running_number == item.running_number,
                Student.id != (item.id or 0),
            ).first()
            if duplicate_running_number:
                flash("Die Laufnummer ist in diesem Semester bereits vergeben.", "danger")
                next_num = 1
                if sem:
                    max_num = db.session.query(db.func.max(Student.running_number)).filter_by(semester_id=sem.id).scalar()
                    next_num = (max_num or 0) + 1
                return render_template("admin/student_form.html", item=item, semester=sem, next_num=next_num)

            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash("Studierende/r gespeichert.", "success")
                return redirect(url_for("admin_students"))
            except IntegrityError:
                db.session.rollback()
                flash("Studierende/r konnte nicht gespeichert werden (Matrikelnummer/Laufnummer muss je Semester eindeutig sein).", "danger")
        next_num = 1
        if sem:
            max_num = db.session.query(db.func.max(Student.running_number)).filter_by(semester_id=sem.id).scalar()
            next_num = (max_num or 0) + 1
        return render_template("admin/student_form.html", item=item, semester=sem, next_num=next_num)

    @app.route("/admin/students/import", methods=["POST"])
    def admin_students_import():
        def normalize_header(header):
            key = (header or "").strip().lower()
            synonyms = {
                "matrikelnummer": "matrikel",
                "matrikel-nr": "matrikel",
                "matrikel nr": "matrikel",
                "nachname": "last_name",
                "surname": "last_name",
                "last name": "last_name",
                "vorname": "first_name",
                "firstname": "first_name",
                "first name": "first_name",
                "e-mail": "email",
                "mail": "email",
            }
            return synonyms.get(key, key)

        sem = active_semester()
        if not sem:
            flash("Kein aktives Semester.", "danger")
            return redirect(url_for("admin_students"))
        file = request.files.get("csv_file")
        if not file:
            flash("Keine Datei ausgewählt.", "danger")
            return redirect(url_for("admin_students"))
        content = file.stream.read().decode("utf-8-sig")
        delimiter = ";"
        try:
            dialect = csv.Sniffer().sniff(content[:2048], delimiters=";,\t,|")
            delimiter = dialect.delimiter
        except csv.Error:
            pass

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        if not reader.fieldnames:
            flash("Import fehlgeschlagen: Datei enthält keine Kopfzeile.", "danger")
            return redirect(url_for("admin_students"))

        reader.fieldnames = [normalize_header(name) for name in reader.fieldnames]

        max_num = db.session.query(db.func.max(Student.running_number)).filter_by(semester_id=sem.id).scalar() or 0
        imported = 0
        skipped_duplicates = 0
        skipped_invalid = 0
        row_warnings = []

        for line_no, row in enumerate(reader, start=2):
            if None in row:
                skipped_invalid += 1
                row_warnings.append(f"Zeile {line_no}: Zu viele Spalten in der CSV-Zeile.")
                continue
            if any(value is None for value in row.values()):
                skipped_invalid += 1
                row_warnings.append(f"Zeile {line_no}: Zu wenige Spalten in der CSV-Zeile.")
                continue

            mat = (row.get("matrikel") or "").strip()
            ln = (row.get("last_name") or "").strip()
            fn = (row.get("first_name") or "").strip()
            email = (row.get("email") or "").strip() or None

            missing = []
            if not mat:
                missing.append("Matrikel")
            if not ln:
                missing.append("Nachname")
            if missing:
                skipped_invalid += 1
                row_warnings.append(f"Zeile {line_no}: Pflichtfeld fehlt ({', '.join(missing)}).")
                continue

            exists = Student.query.filter_by(semester_id=sem.id, matrikel=mat).first()
            if exists:
                skipped_duplicates += 1
                continue

            max_num += 1
            st = Student(semester=sem, matrikel=mat, last_name=ln,
                         first_name=fn, running_number=max_num,
                         email=email)
            db.session.add(st)
            imported += 1

        db.session.commit()
        flash(
            (
                "Import abgeschlossen: "
                f"{imported} importiert, "
                f"{skipped_duplicates} Duplikate übersprungen, "
                f"{skipped_invalid} ungültige Zeilen übersprungen."
            ),
            "success",
        )
        if row_warnings:
            flash("Import-Hinweise:\n" + "\n".join(row_warnings), "warning")
        return redirect(url_for("admin_students"))

    @app.route("/admin/students/<int:id>/delete", methods=["POST"])
    def admin_student_delete(id):
        item = Student.query.get_or_404(id)

        force = request.form.get("force") == "1"
        assignment_count = SampleAssignment.query.filter_by(student_id=item.id).count()

        if assignment_count and not force:
            flash(
                (
                    "Löschen blockiert: Dieser/diese Studierende hat bereits "
                    f"{assignment_count} Zuweisung(en). "
                    "Standardmäßig werden Datensätze aus Gründen der Nachvollziehbarkeit nur storniert. "
                    "Bitte zuerst Zuweisungen im Bereich ‚Zuweisungen‘ stornieren oder explizit ‚Endgültig löschen‘ verwenden."
                ),
                "danger",
            )
            return redirect(url_for("admin_students"))

        try:
            db.session.delete(item)
            db.session.commit()
            if assignment_count:
                flash(
                    (
                        "Studierende/r und verknüpfte Datensätze wurden endgültig gelöscht "
                        f"({assignment_count} Zuweisung(en) inkl. Ergebnisse)."
                    ),
                    "warning",
                )
            else:
                flash("Studierende/r gelöscht.", "success")
        except IntegrityError:
            db.session.rollback()
            flash(
                "Studierende/r konnte wegen bestehender Verknüpfungen nicht gelöscht werden.",
                "danger",
            )

        return redirect(url_for("admin_students"))

    # ═══════════════════════════════════════════════════════════════
    # SAMPLE BATCHES
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/batches")
    def admin_batches():
        sem = active_semester()
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all() if sem else []
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        return render_template("admin/batches.html", batches=batches, analyses=analyses, semester=sem)

    @app.route("/admin/batches/new", methods=["GET", "POST"])
    @app.route("/admin/batches/<int:id>/edit", methods=["GET", "POST"])
    @require_active_semester("admin_batches")
    def admin_batch_form(id=None):
        item = SampleBatch.query.get(id) if id else SampleBatch()
        sem = active_semester()
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        analysis_modes = {a.id: resolve_mode(a.calculation_mode) for a in analyses}
        lots = SubstanceLot.query.order_by(SubstanceLot.id.desc()).all()
        n_students = Student.query.filter_by(semester_id=sem.id).count() if sem else 0
        if request.method == "POST":
            item.semester_id = sem.id
            item.analysis_id = int(request.form["analysis_id"])
            analysis = Analysis.query.get(item.analysis_id)
            mode = resolve_mode(analysis.calculation_mode if analysis else None)

            item.substance_lot_id = _int(request.form.get("substance_lot_id"))
            item.target_m_s_min_g = _float(request.form.get("target_m_s_min_g"))
            item.target_m_ges_g = _float(request.form.get("target_m_ges_g"))
            item.target_v_min_ml = _float(request.form.get("target_v_min_ml"))
            item.target_v_max_ml = _float(request.form.get("target_v_max_ml"))
            item.dilution_factor = _float(request.form.get("dilution_factor"))
            item.dilution_solvent = request.form.get("dilution_solvent") or None
            item.dilution_notes = request.form.get("dilution_notes") or None
            item.titer = float(request.form.get("titer", 1.0))
            item.total_samples_prepared = int(request.form["total_samples_prepared"])
            item.preparation_date = request.form.get("preparation_date") or None
            item.prepared_by = request.form.get("prepared_by") or None
            item.notes = request.form.get("notes") or None

            if mode == MODE_ASSAY_MASS_BASED:
                if item.target_m_s_min_g is None or item.target_m_ges_g is None:
                    flash("Für massenbasierte Analysen sind Ziel-m_S,min und Ziel-m_ges erforderlich.", "danger")
                    ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
                    lot_opts = [(l.id, f"{l.substance.name} / {l.lot_number} (p={l.p_effective:.1f}%)") for l in lots]
                    return render_template("admin/batch_form.html", item=item, ana_opts=ana_opts,
                                           lot_opts=lot_opts, semester=sem, n_students=n_students, analysis_modes=analysis_modes)
            elif mode == MODE_TITRANT_STANDARDIZATION:
                if item.target_v_min_ml is None or item.target_v_max_ml is None:
                    flash("Für Titerstandardisierung sind Ziel-V_min und Ziel-V_max erforderlich.", "danger")
                    ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
                    lot_opts = [(l.id, f"{l.substance.name} / {l.lot_number} (p={l.p_effective:.1f}%)") for l in lots]
                    return render_template("admin/batch_form.html", item=item, ana_opts=ana_opts,
                                           lot_opts=lot_opts, semester=sem, n_students=n_students, analysis_modes=analysis_modes)

            duplicate = SampleBatch.query.filter(
                SampleBatch.semester_id == sem.id,
                SampleBatch.analysis_id == item.analysis_id,
                SampleBatch.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Für dieses Semester existiert bereits ein Probenansatz für die gewählte Analyse.", "danger")
                ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
                lot_opts = [(l.id, f"{l.substance.name} / {l.lot_number} (p={l.p_effective:.1f}%)") for l in lots]
                return render_template("admin/batch_form.html", item=item, ana_opts=ana_opts,
                                       lot_opts=lot_opts, semester=sem, n_students=n_students, analysis_modes=analysis_modes)
            if not id:
                db.session.add(item)
            try:
                db.session.flush()
                # Auto-generate samples if none exist
                existing = Sample.query.filter_by(batch_id=item.id).count()
                if existing == 0:
                    for i in range(1, item.total_samples_prepared + 1):
                        s = Sample(batch=item, running_number=i, is_buffer=(i > n_students))
                        db.session.add(s)
                db.session.commit()
                flash("Probenansatz gespeichert. Proben generiert.", "success")
                return redirect(url_for("admin_batches"))
            except IntegrityError:
                db.session.rollback()
                flash("Probenansatz konnte nicht gespeichert werden (Analyse je Semester nur einmal erlaubt).", "danger")
        ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
        lot_opts = [(l.id, f"{l.substance.name} / {l.lot_number} (p={l.p_effective:.1f}%)") for l in lots]
        return render_template("admin/batch_form.html", item=item, ana_opts=ana_opts,
                               lot_opts=lot_opts, semester=sem, n_students=n_students, analysis_modes=analysis_modes)

    @app.route("/admin/batches/<int:id>/assign-initial", methods=["POST"])
    def admin_batch_assign_initial(id):
        """Erstanalysen zuweisen: Student k → Probe k."""
        batch = SampleBatch.query.get_or_404(id)
        sem = batch.semester
        students = Student.query.filter_by(semester_id=sem.id).order_by(Student.running_number).all()
        samples = Sample.query.filter_by(batch_id=batch.id, is_buffer=False).order_by(Sample.running_number).all()
        count = 0
        for st in students:
            # Find sample with matching running_number
            sample = next((s for s in samples if s.running_number == st.running_number), None)
            if not sample:
                continue
            existing = (
                SampleAssignment.query
                .filter_by(sample_id=sample.id, student_id=st.id)
                # Cancelled assignments are historical and should not block a fresh initial assignment.
                .filter(SampleAssignment.status != "cancelled")
                .first()
            )
            if existing:
                continue
            sa = SampleAssignment(
                sample=sample, student=st, attempt_number=1, attempt_type="A",
                assigned_date=date.today().isoformat(), assigned_by="System",
                status="assigned",
            )
            db.session.add(sa)
            count += 1
        db.session.commit()
        flash(f"{count} Erstanalysen zugewiesen.", "success")
        return redirect(url_for("admin_batches"))

    # ═══════════════════════════════════════════════════════════════
    # TA: WEIGHING (Einwaage-Eingabe)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/ta/weighing")
    def ta_weighing():
        sem = active_semester()
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all() if sem else []
        return render_template("ta/weighing_select.html", batches=batches, semester=sem)

    @app.route("/ta/weighing/<int:batch_id>", methods=["GET", "POST"])
    def ta_weighing_batch(batch_id):
        batch = SampleBatch.query.get_or_404(batch_id)
        samples = Sample.query.filter_by(batch_id=batch_id).order_by(Sample.running_number).all()
        if request.method == "POST":
            for s in samples:
                m_s = request.form.get(f"m_s_{s.id}")
                m_ges = request.form.get(f"m_ges_{s.id}")
                if m_s:
                    s.m_s_actual_g = float(m_s.replace(",", "."))
                if m_ges:
                    s.m_ges_actual_g = float(m_ges.replace(",", "."))
                s.weighed_by = request.form.get("weighed_by") or s.weighed_by
                s.weighed_date = date.today().isoformat()
            db.session.commit()
            flash("Einwaagen gespeichert.", "success")
            return redirect(url_for("ta_weighing_batch", batch_id=batch_id))
        return render_template("ta/weighing.html", batch=batch, samples=samples)

    @app.route("/ta/samples/<int:batch_id>")
    def ta_sample_overview(batch_id):
        batch = SampleBatch.query.get_or_404(batch_id)
        samples = Sample.query.filter_by(batch_id=batch_id).order_by(Sample.running_number).all()
        return render_template("ta/sample_overview.html", batch=batch, samples=samples)

    # ═══════════════════════════════════════════════════════════════
    # ASSIGNMENTS (Wiederholungsanalysen)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/assignments")
    def assignments_overview():
        sem = active_semester()
        if not sem:
            return render_template("assignments/overview.html", semester=None, analyses=[], data={})
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        data = {}
        for a in analyses:
            batch = SampleBatch.query.filter_by(semester_id=sem.id, analysis_id=a.id).first()
            if not batch:
                continue
            assignments = (
                SampleAssignment.query
                .join(Sample).filter(Sample.batch_id == batch.id)
                .order_by(SampleAssignment.student_id, SampleAssignment.attempt_number)
                .all()
            )
            buffer_samples = (
                Sample.query.filter_by(batch_id=batch.id, is_buffer=True)
                .filter(~Sample.id.in_(
                    db.session.query(SampleAssignment.sample_id)
                    .filter(SampleAssignment.status != "cancelled")
                ))
                .order_by(Sample.running_number).all()
            )
            data[a.code] = {
                "batch": batch,
                "assignments": assignments,
                "buffer_count": len(buffer_samples),
            }
        return render_template("assignments/overview.html", semester=sem, analyses=analyses, data=data)

    @app.route("/assignments/assign-buffer", methods=["POST"])
    @require_active_semester("assignments_overview")
    def assign_buffer():
        student_id = int(request.form["student_id"])
        analysis_id = int(request.form["analysis_id"])
        sem = active_semester()
        batch = SampleBatch.query.filter_by(semester_id=sem.id, analysis_id=analysis_id).first()
        if not batch:
            flash("Kein Batch gefunden.", "danger")
            return redirect(url_for("assignments_overview"))
        # Find next free buffer sample
        used_ids = [sa.sample_id for sa in SampleAssignment.query.filter(SampleAssignment.status != "cancelled").all()]
        buffer_sample = (
            Sample.query.filter_by(batch_id=batch.id, is_buffer=True)
            .filter(~Sample.id.in_(used_ids))
            .order_by(Sample.running_number).first()
        )
        if not buffer_sample:
            flash("Keine freien Pufferproben mehr!", "danger")
            return redirect(url_for("assignments_overview"))
        # Determine attempt number/type
        prev_count = (
            SampleAssignment.query
            .join(Sample).filter(Sample.batch_id == batch.id)
            .filter(SampleAssignment.student_id == student_id)
            .count()
        )
        types = ["A", "B", "C", "D"]
        attempt_type = types[min(prev_count, len(types) - 1)]
        sa = SampleAssignment(
            sample=buffer_sample, student_id=student_id,
            attempt_number=prev_count + 1, attempt_type=attempt_type,
            assigned_date=date.today().isoformat(), assigned_by="Praktikumsleitung",
            status="assigned",
        )
        db.session.add(sa)
        db.session.commit()
        flash(f"Pufferprobe #{buffer_sample.running_number} ({attempt_type}-Analyse) zugewiesen.", "success")
        return redirect(url_for("assignments_overview"))

    @app.route("/assignments/<int:id>/cancel", methods=["POST"])
    @require_active_semester("assignments_overview")
    def assignment_cancel(id):
        assignment = SampleAssignment.query.get_or_404(id)

        if assignment.status == "cancelled":
            flash("Zuweisung ist bereits storniert.", "info")
            return redirect(url_for("assignments_overview"))

        assignment.status = "cancelled"
        db.session.commit()
        flash(
            (
                f"Zuweisung für {assignment.student.full_name} (Probe #{assignment.sample.running_number}) wurde storniert. "
                "Historische Ansagen bleiben zur Nachvollziehbarkeit erhalten."
            ),
            "warning",
        )
        return redirect(url_for("assignments_overview"))

    @app.route("/assignments/<int:id>/delete", methods=["POST"])
    @require_active_semester("assignments_overview")
    def assignment_delete(id):
        assignment = SampleAssignment.query.get_or_404(id)

        force = request.form.get("force") == "1"
        result_count = Result.query.filter_by(assignment_id=assignment.id).count()

        if not force:
            flash(
                "Endgültiges Löschen ist nur als explizite Aktion erlaubt. Bitte stattdessen standardmäßig ‚Stornieren‘ verwenden.",
                "danger",
            )
            return redirect(url_for("assignments_overview"))

        student_name = assignment.student.full_name
        sample_number = assignment.sample.running_number
        db.session.delete(assignment)
        db.session.commit()
        flash(
            (
                f"Zuweisung für {student_name} (Probe #{sample_number}) endgültig gelöscht. "
                f"Entfernt: {result_count} Ergebnis(se)."
            ),
            "warning",
        )
        return redirect(url_for("assignments_overview"))

    # ═══════════════════════════════════════════════════════════════
    # RESULTS (Ansagen)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/results")
    def results_overview():
        sem = active_semester()
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        selected_analysis_id = request.args.get("analysis_id", type=int)
        assignments = []
        selected_analysis = None
        if sem and selected_analysis_id:
            selected_analysis = Analysis.query.get(selected_analysis_id)
            batch = SampleBatch.query.filter_by(semester_id=sem.id, analysis_id=selected_analysis_id).first()
            if batch:
                assignments = (
                    SampleAssignment.query
                    .join(Sample).filter(Sample.batch_id == batch.id)
                    .join(Student)
                    .order_by(Student.running_number, SampleAssignment.attempt_number)
                    .all()
                )
        return render_template("results/overview.html", semester=sem, analyses=analyses,
                               selected_analysis_id=selected_analysis_id, selected_analysis=selected_analysis, assignments=assignments)

    @app.route("/results/submit/<int:assignment_id>", methods=["GET", "POST"])
    def results_submit(assignment_id):
        assignment = SampleAssignment.query.get_or_404(assignment_id)
        analysis = assignment.sample.batch.analysis

        sample = assignment.sample
        method = analysis.method
        missing_requirements = []
        mode = analysis.calculation_mode or MODE_ASSAY_MASS_BASED
        if mode == MODE_ASSAY_MASS_BASED:
            if sample.m_s_actual_g is None or sample.m_ges_actual_g is None:
                missing_requirements.append("Einwaagedaten der Probe")
            if method is None or method.m_eq_mg is None:
                missing_requirements.append("Methodenäquivalent (m_eq)")
            if analysis.tol_min is None or analysis.tol_max is None:
                missing_requirements.append("Toleranzgrenzen")
        elif mode == MODE_TITRANT_STANDARDIZATION:
            if sample.m_s_actual_g is None:
                missing_requirements.append("Referenzeinwaage (m_S)")
            if method is None or method.m_eq_mg is None:
                missing_requirements.append("Methodenäquivalent (m_eq)")
            if analysis.tol_min is None or analysis.tol_max is None:
                missing_requirements.append("Titer-Grenzen")

        if missing_requirements:
            flash(
                "Ansage kann derzeit nicht bewertet werden. Bitte vervollständigen: "
                + ", ".join(missing_requirements)
                + ".",
                "warning",
            )
            return redirect(url_for("results_overview", analysis_id=analysis.id))

        if request.method == "POST":
            val = float(request.form["ansage_value"].replace(",", "."))
            r = Result(
                assignment=assignment,
                ansage_value=val,
                ansage_unit=analysis.result_unit,
            )
            r.evaluate()
            db.session.add(r)
            if r.passed is True:
                assignment.status = "passed"
            elif r.passed is False:
                assignment.status = "failed"
            else:
                assignment.status = "submitted"
            db.session.commit()
            if r.passed is True:
                flash(f"✅ Bestanden! Ansage: {val} {analysis.result_unit}", "success")
            elif r.passed is False:
                if r.a_min is not None and r.a_max is not None:
                    tolerance_text = f"(Toleranz: {r.a_min:.4f} – {r.a_max:.4f})"
                else:
                    tolerance_text = ""
                flash(f"❌ Nicht bestanden. Ansage: {val} {analysis.result_unit} "
                      f"{tolerance_text}".strip(), "danger")
            else:
                flash("⚠️ Bewertung nicht möglich – Einwaage/Toleranzdaten fehlen.", "warning")
            return redirect(url_for("results_overview", analysis_id=analysis.id))
        return render_template("results/submit.html", assignment=assignment, analysis=analysis)

    # ═══════════════════════════════════════════════════════════════
    # REPORTS
    # ═══════════════════════════════════════════════════════════════
    @app.route("/reports/progress")
    def reports_progress():
        sem = active_semester()
        if not sem:
            return render_template("reports/progress.html", semester=None, students=[], analyses=[])
        students = Student.query.filter_by(semester_id=sem.id).order_by(Student.running_number).all()
        analyses = Analysis.query.order_by(Analysis.ordinal).all()
        # Build progress matrix
        progress = {}
        for st in students:
            progress[st.id] = {}
            for a in analyses:
                batch = SampleBatch.query.filter_by(semester_id=sem.id, analysis_id=a.id).first()
                if not batch:
                    progress[st.id][a.code] = None
                    continue
                assgns = (
                    SampleAssignment.query
                    .join(Sample).filter(Sample.batch_id == batch.id)
                    .filter(SampleAssignment.student_id == st.id)
                    .order_by(SampleAssignment.attempt_number.desc())
                    .all()
                )
                if not assgns:
                    progress[st.id][a.code] = {"status": "not_assigned"}
                else:
                    latest = assgns[0]
                    progress[st.id][a.code] = {
                        "status": latest.status,
                        "attempt": latest.attempt_type,
                        "attempts": len(assgns),
                    }
        return render_template("reports/progress.html", semester=sem, students=students,
                               analyses=analyses, progress=progress)

    @app.route("/reports/reagents")
    def reports_reagents():
        sem = active_semester()
        if not sem:
            return render_template("reports/reagents.html", semester=None, demand=[])
        demand = []
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        for batch in batches:
            analysis = batch.analysis
            method = analysis.method
            if not method:
                continue
            for mr in method.reagent_usages:
                k = analysis.k_determinations
                b = method.b_blind_determinations if method.blind_required else 0
                n = batch.total_samples_prepared
                safety = 1.2
                total = n * (k * mr.volume_per_determination_ml + b * mr.volume_per_blind_ml) * safety
                demand.append({
                    "analysis": analysis.code,
                    "analysis_name": analysis.name,
                    "reagent": mr.reagent.name,
                    "unit": mr.reagent.base_unit,
                    "per_det": mr.volume_per_determination_ml,
                    "per_blind": mr.volume_per_blind_ml,
                    "k": k,
                    "b": b,
                    "n": n,
                    "total": round(total, 1),
                    "is_titrant": mr.is_titrant,
                })
        return render_template("reports/reagents.html", semester=sem, demand=demand)

    # ═══════════════════════════════════════════════════════════════
    # API endpoints (for HTMX / JS)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/api/sample/<int:sample_id>/calc")
    def api_sample_calc(sample_id):
        s = Sample.query.get_or_404(sample_id)
        return jsonify({
            "g_wahr": round(s.g_wahr, 4) if s.g_wahr else None,
            "a_min": s.a_min,
            "a_max": s.a_max,
            "v_expected": s.v_expected,
            "titer_expected": s.titer_expected,
            "p_effective": s.batch.p_effective,
            "p_source": s.batch.p_source,
        })


# ── Utility ──────────────────────────────────────────────────────────

def _float(val):
    if val is None or val == "":
        return None
    return float(str(val).replace(",", "."))


def _int(val):
    if val is None or val == "":
        return None
    return int(val)


# ── Entry point ──────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
