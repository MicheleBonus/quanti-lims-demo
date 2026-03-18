"""Quanti-LIMS – Flask Application."""

from __future__ import annotations

import csv
import io
import json
import os
from functools import wraps
from datetime import date
from sqlalchemy.exc import IntegrityError

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_file, session, abort,
)
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from config import Config
from models import (
    db, Block, Substance, SubstanceLot, Analysis, Method,
    Reagent, ReagentComponent, MethodReagent,
    Semester, Student, SampleBatch, Sample, SampleAssignment, Result,
    AMOUNT_UNIT_VOLUME, GROUP_CODES,
    canonical_unit_label, get_amount_unit_type, get_unit_options, is_known_unit, normalize_unit,
    PracticalDay, GroupRotation, DutyAssignment,
)
from calculation_modes import MODE_ASSAY_MASS_BASED, MODE_TITRANT_STANDARDIZATION, resolve_mode, attempt_type_for, compute_evaluation_label


# Legacy constant kept for reference; validation now uses minimum-only check.
TARGET_M_GES_TOLERANCE_G = 0.005



def mode_titer_label(mode: str | None) -> str:
    resolved = resolve_mode(mode)
    if resolved == MODE_ASSAY_MASS_BASED:
        return "Faktor (aus Einstellung)"
    return "Titer"


def _method_supports_titrant_flag(method: Method) -> bool:
    mode = resolve_mode(method.analysis.calculation_mode if method.analysis else None)
    return mode != MODE_TITRANT_STANDARDIZATION and method.method_type in {"direct", "back"}


def _sync_method_titrant_name(method: Method) -> None:
    usage = next((u for u in method.reagent_usages if u.is_titrant and u.reagent), None)
    method.titrant_name = usage.reagent.name if usage else None


def _validate_aliquot(method: Method) -> str | None:
    has_sol = method.v_solution_ml is not None
    has_aliq = method.v_aliquot_ml is not None
    if has_sol != has_aliq:
        return "V Lösung und V Aliquot müssen beide gesetzt oder beide leer sein."
    if has_sol and has_aliq:
        if method.v_solution_ml <= 0 or method.v_aliquot_ml <= 0:
            return "V Lösung und V Aliquot müssen größer als 0 sein."
        if method.v_aliquot_ml > method.v_solution_ml:
            return "V Aliquot darf nicht größer als V Lösung sein."
    return None


def evaluate_weighing_limits(batch: SampleBatch, m_s_actual_g: float | None, m_ges_actual_g: float | None) -> dict:
    """Evaluate whether actual weighing values are within configured limits."""
    mode = resolve_mode(batch.analysis.calculation_mode if batch.analysis else None)
    checks: list[str] = []
    details: dict[str, bool] = {
        "m_s_min_violation": False,
        "m_ges_target_violation": False,
        "volume_range_violation": False,
    }

    if mode == MODE_ASSAY_MASS_BASED:
        if (
            m_s_actual_g is not None
            and batch.target_m_s_min_g is not None
            and m_s_actual_g < batch.target_m_s_min_g
        ):
            details["m_s_min_violation"] = True
            checks.append(f"m_S {m_s_actual_g:.3f} g < Mindest {batch.target_m_s_min_g:.3f} g")

        if (
            m_ges_actual_g is not None
            and batch.target_m_ges_g is not None
            and m_ges_actual_g < batch.target_m_ges_g
        ):
            details["m_ges_target_violation"] = True
            checks.append(
                f"m_ges {m_ges_actual_g:.3f} g < Mindest {batch.target_m_ges_g:.3f} g"
            )
    else:
        if (
            m_ges_actual_g is not None
            and batch.target_v_min_ml is not None
            and batch.target_v_max_ml is not None
            and not (batch.target_v_min_ml <= m_ges_actual_g <= batch.target_v_max_ml)
        ):
            details["volume_range_violation"] = True
            checks.append(
                f"V {m_ges_actual_g:.3f} mL außerhalb Zielbereich {batch.target_v_min_ml:.3f}–{batch.target_v_max_ml:.3f} mL"
            )

    return {
        "mode": mode,
        "out_of_range": bool(checks),
        "messages": checks,
        **details,
    }


def resolve_standardization_titer(semester_id: int) -> dict | None:
    latest = (
        Result.query
        .join(SampleAssignment, Result.assignment_id == SampleAssignment.id)
        .join(Sample, SampleAssignment.sample_id == Sample.id)
        .join(SampleBatch, Sample.batch_id == SampleBatch.id)
        .join(Analysis, SampleBatch.analysis_id == Analysis.id)
        .filter(SampleBatch.semester_id == semester_id)
        .filter(Analysis.calculation_mode == MODE_TITRANT_STANDARDIZATION)
        .filter(Result.titer_result.isnot(None))
        .order_by(Result.submitted_date.desc(), Result.id.desc())
        .first()
    )
    if not latest:
        return None
    return {
        "value": latest.titer_result,
        "date": latest.submitted_date or date.today().isoformat(),
        "operator": latest.evaluated_by or latest.assignment.assigned_by or "Unbekannt",
    }


def create_app(test_config: dict | None = None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config is not None:
        app.config.update(test_config)
    CSRFProtect(app)
    db.init_app(app)
    Migrate(app, db)  # registers `flask db` CLI commands

    with app.app_context():
        if app.config.get("TESTING"):
            db.create_all()   # tests: create schema directly (SQLite in-memory)
        from init_db import seed_database
        seed_database()

    register_routes(app)
    register_filters(app)
    register_error_handlers(app)
    return app


def register_filters(app):
    @app.template_filter("fmt")
    def fmt_number(value, decimals=4):
        if value is None:
            return "–"
        return f"{value:.{decimals}f}"

    @app.template_filter("unit")
    def fmt_unit(value):
        return canonical_unit_label(value)

    @app.template_filter("zip")
    def zip_filter(a, b):
        return list(zip(a, b))

    @app.template_filter("de_date")
    def de_date_filter(value):
        """Format ISO date string (YYYY-MM-DD) as German dd.mm.yyyy."""
        if not value:
            return "–"
        try:
            parts = str(value).split("-")
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
        except (ValueError, IndexError):
            pass
        return str(value)

    @app.template_global("options_for")
    def options_for(items, value_attr="id", label_attr="name"):
        """Build select options from a list of ORM objects."""
        return [(getattr(i, value_attr), getattr(i, label_attr)) for i in items]


def register_error_handlers(app):
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("errors/500.html"), 500


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

    def _iso_now() -> str:
        return date.today().isoformat()

    def _de_date(iso: str) -> str:
        """Convert ISO date to German dd.mm.yyyy format."""
        try:
            parts = iso.split("-")
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
        except (ValueError, IndexError):
            pass
        return iso

    def _get_active_semester_id():
        """Returns the id of the active semester, or aborts with 400."""
        sem = Semester.query.filter_by(is_active=True).first()
        if sem is None:
            abort(400, "Kein aktives Semester gefunden.")
        return sem.id

    def flash_saved(entity_label: str, details: str | None = None) -> None:
        timestamp = _de_date(_iso_now())
        save_times = session.get("save_timestamps", {})
        save_times[entity_label] = timestamp
        session["save_timestamps"] = save_times
        suffix = f" ({details})" if details else ""
        flash(f"{entity_label} gespeichert – {timestamp}{suffix}", "success")

    def _dict_rows(rows: list[dict], filename: str, fmt: str):
        if fmt == "json":
            payload = json.dumps(rows, ensure_ascii=False, indent=2)
            return Response(
                payload,
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}.json"},
            )
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
        else:
            output.write("\n")
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )

    @app.context_processor
    def inject_save_feedback():
        return {"save_timestamps": session.get("save_timestamps", {})}

    def _db_file_path() -> str | None:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        prefix = "sqlite:///"
        if not uri.startswith(prefix):
            return None
        raw_path = uri[len(prefix):]
        if not raw_path:
            return None
        return raw_path if os.path.isabs(raw_path) else os.path.abspath(raw_path)

    def _is_admin_request() -> bool:
        if session.get("is_admin") is True:
            return True
        token = app.config.get("ADMIN_BACKUP_TOKEN")
        if token and request.args.get("token") == token:
            session["is_admin"] = True
            return True
        return False

    # ═══════════════════════════════════════════════════════════════
    # DASHBOARD
    # ═══════════════════════════════════════════════════════════════
    @app.route("/")
    def dashboard():
        return render_template("home.html")

    @app.route("/vorbereitung/stammdaten")
    def vorbereitung_stammdaten():
        return redirect(url_for("admin_substances"))

    @app.route("/praktikum/")
    def praktikum_tagesansicht():
        return render_template("praktikum/tagesansicht.html")

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Substances
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/substances")
    def admin_substances():
        items = Substance.query.order_by(Substance.position, Substance.name).all()
        return render_template("admin/substances.html", items=items)

    @app.route("/admin/substances/new", methods=["GET", "POST"])
    @app.route("/admin/substances/<int:id>/edit", methods=["GET", "POST"])
    def admin_substance_form(id=None):
        item = Substance.query.get(id) if id else Substance()
        if request.method == "POST":
            item.name = request.form["name"]
            item.formula = request.form.get("formula") or None
            item.molar_mass_gmol = _float(request.form.get("molar_mass_gmol"))
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
                flash_saved("Substanz")
                return redirect(url_for("admin_substances"))
            except IntegrityError:
                db.session.rollback()
                flash("Substanz konnte nicht gespeichert werden (Name ist bereits vergeben).", "danger")
        return render_template("admin/substance_form.html", item=item)

    @app.route("/admin/substances/<int:id>/delete", methods=["POST"])
    def admin_substance_delete(id):
        item = Substance.query.get_or_404(id)
        if item.lots or item.analyses:
            flash("Substanz kann nicht gelöscht werden – es existieren verknüpfte Chargen oder Analysen.", "danger")
            return redirect(url_for("admin_substances"))
        db.session.delete(item)
        db.session.commit()
        flash("Substanz gelöscht.", "warning")
        return redirect(url_for("admin_substances"))

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Substance Lots
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/lots")
    def admin_lots():
        items = SubstanceLot.query.order_by(SubstanceLot.position, SubstanceLot.id.desc()).all()
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
                flash_saved("Charge")
                return redirect(url_for("admin_lots"))
            except IntegrityError:
                db.session.rollback()
                flash("Charge konnte nicht gespeichert werden (Substanz + Chargennummer muss eindeutig sein).", "danger")
        sub_opts = [(s.id, s.name) for s in substances]
        return render_template("admin/lot_form.html", item=item, sub_opts=sub_opts)

    @app.route("/admin/lots/<int:id>/delete", methods=["POST"])
    def admin_lot_delete(id):
        item = SubstanceLot.query.get_or_404(id)
        if item.batches:
            flash("Charge kann nicht gelöscht werden – es existieren verknüpfte Probenansätze.", "danger")
            return redirect(url_for("admin_lots"))
        db.session.delete(item)
        db.session.commit()
        flash("Charge gelöscht.", "warning")
        return redirect(url_for("admin_lots"))

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Analyses (Prüfungen)
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
            item.e_ab_g = _float(request.form.get("e_ab_g"))
            item.g_ab_min_pct = _float(request.form.get("g_ab_min_pct"))
            item.g_ab_max_pct = _float(request.form.get("g_ab_max_pct"))
            item.source_reference = request.form.get("source_reference") or None
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
                flash_saved("Analyse")
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
        items = Method.query.join(Analysis).order_by(Method.position, Analysis.ordinal).all()
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
            item.titrant_concentration = request.form.get("titrant_concentration") or None
            item.c_titrant_mol_l = _float(request.form.get("c_titrant_mol_l"))
            item.n_eq_titrant = _float(request.form.get("n_eq_titrant"))
            item.c_vorlage_mol_l = _float(request.form.get("c_vorlage_mol_l"))
            item.n_eq_vorlage = _float(request.form.get("n_eq_vorlage"))
            item.blind_required = "blind_required" in request.form
            item.b_blind_determinations = int(request.form.get("b_blind_determinations", 1))
            item.v_vorlage_ml = _float(request.form.get("v_vorlage_ml"))
            item.v_solution_ml = _float(request.form.get("v_solution_ml"))
            item.v_aliquot_ml = _float(request.form.get("v_aliquot_ml"))
            item.primary_standard_id = _int(request.form.get("primary_standard_id"))
            # Override/auto-calc logic only applies in standardization mode
            _analysis = Analysis.query.get(item.analysis_id)
            _mode = resolve_mode(_analysis.calculation_mode if _analysis else None)
            if _mode == MODE_TITRANT_STANDARDIZATION:
                item.m_eq_primary_mg_override = "m_eq_primary_mg_override" in request.form
                if item.m_eq_primary_mg_override:
                    item.m_eq_primary_mg = _float(request.form.get("m_eq_primary_mg"))
                else:
                    # Auto-calculate: m_eq = c_Titrant × MW_PS / z
                    ps_id = item.primary_standard_id
                    ps = db.session.get(Reagent, ps_id) if ps_id else None
                    if (ps and ps.molar_mass_gmol
                            and item.c_titrant_mol_l and item.c_titrant_mol_l > 0
                            and item.n_eq_titrant and item.n_eq_titrant > 0):
                        item.m_eq_primary_mg = round(
                            item.c_titrant_mol_l * ps.molar_mass_gmol / item.n_eq_titrant, 4
                        )
                    else:
                        item.m_eq_primary_mg = None
            else:
                item.m_eq_primary_mg = _float(request.form.get("m_eq_primary_mg"))
            item.e_ab_ps_g = _float(request.form.get("e_ab_ps_g"))
            if _mode == MODE_TITRANT_STANDARDIZATION:
                item.c_stock_mol_l = _float(request.form.get("c_stock_mol_l"))
                item.v_dilution_ml = _float(request.form.get("v_dilution_ml"))
            item.description = request.form.get("description") or None
            validation_error = _validate_aliquot(item)
            if validation_error:
                flash(validation_error, "danger")
                ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
                all_reagents = Reagent.query.order_by(Reagent.name).all()
                ps_list = [r for r in all_reagents if r.is_primary_standard]
                ps_opts = [(r.id, f"{r.name} ({r.formula or '–'}, MW={r.molar_mass_gmol or '?'})") for r in ps_list]
                ps_molar_masses = {r.id: r.molar_mass_gmol for r in ps_list if r.molar_mass_gmol}
                return render_template("admin/method_form.html", item=item, ana_opts=ana_opts,
                                       primary_std_opts=ps_opts, ps_molar_masses=ps_molar_masses)
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash_saved("Methode")
                return redirect(url_for("admin_methods"))
            except IntegrityError:
                db.session.rollback()
                flash("Methode konnte nicht gespeichert werden (Integritätsfehler).", "danger")
        ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
        all_reagents = Reagent.query.order_by(Reagent.name).all()
        ps_list = [r for r in all_reagents if r.is_primary_standard]
        ps_opts = [(r.id, f"{r.name} ({r.formula or '–'}, MW={r.molar_mass_gmol or '?'})") for r in ps_list]
        ps_molar_masses = {r.id: r.molar_mass_gmol for r in ps_list if r.molar_mass_gmol}
        return render_template("admin/method_form.html", item=item, ana_opts=ana_opts,
                               primary_std_opts=ps_opts, ps_molar_masses=ps_molar_masses)

    @app.route("/admin/methods/<int:id>/delete", methods=["POST"])
    def admin_method_delete(id):
        item = Method.query.get_or_404(id)
        if item.reagent_usages:
            flash("Methode kann nicht gelöscht werden – es existieren verknüpfte Reagenzien-Zuweisungen. Bitte zuerst die Zuweisungen entfernen.", "danger")
            return redirect(url_for("admin_methods"))
        db.session.delete(item)
        db.session.commit()
        flash("Methode gelöscht.", "warning")
        return redirect(url_for("admin_methods"))

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Reagents
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/reagents")
    def admin_reagents():
        items = Reagent.query.order_by(Reagent.position, Reagent.name).all()
        return render_template("admin/reagents.html", items=items)

    @app.route("/admin/reagents/new", methods=["GET", "POST"])
    @app.route("/admin/reagents/<int:id>/edit", methods=["GET", "POST"])
    def admin_reagent_form(id=None):
        item = Reagent.query.get(id) if id else Reagent()
        if request.method == "POST":
            item.name = request.form["name"]
            item.abbreviation = request.form.get("abbreviation") or None
            item.is_composite = "is_composite" in request.form
            item.is_primary_standard = "is_primary_standard" in request.form
            if item.is_primary_standard:
                item.formula = request.form.get("formula") or None
                item.molar_mass_gmol = _float(request.form.get("molar_mass_gmol"))
            else:
                item.formula = None
                item.molar_mass_gmol = None
            base_unit = normalize_unit(request.form.get("base_unit") or "mL")
            if not is_known_unit(base_unit):
                flash("Ungültige Einheit für Reagenz.", "danger")
                return render_template("admin/reagent_form.html", item=item, unit_options=get_unit_options())
            item.base_unit = base_unit
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
                return render_template("admin/reagent_form.html", item=item, unit_options=get_unit_options())
            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash_saved("Reagenz")
                return redirect(url_for("admin_reagents"))
            except IntegrityError:
                db.session.rollback()
                flash("Reagenz konnte nicht gespeichert werden (Name ist bereits vergeben).", "danger")
        return render_template("admin/reagent_form.html", item=item, unit_options=get_unit_options())

    @app.route("/admin/reagents/<int:id>/delete", methods=["POST"])
    def admin_reagent_delete(id):
        item = Reagent.query.get_or_404(id)
        if item.method_usages:
            flash("Reagenz kann nicht gelöscht werden – es ist Methoden zugewiesen. Bitte zuerst die Methoden-Zuweisungen entfernen.", "danger")
            return redirect(url_for("admin_reagents"))
        if item.primary_standard_methods:
            flash("Reagenz kann nicht gelöscht werden – es wird als Primärstandard in Methoden verwendet.", "danger")
            return redirect(url_for("admin_reagents"))
        if item.components:
            for c in list(item.components):
                db.session.delete(c)
        # Also remove if used as child in other composites
        child_refs = ReagentComponent.query.filter_by(child_reagent_id=id).all()
        for cr in child_refs:
            db.session.delete(cr)
        db.session.delete(item)
        db.session.commit()
        flash("Reagenz gelöscht.", "warning")
        return redirect(url_for("admin_reagents"))

    # ═══════════════════════════════════════════════════════════════
    # ADMIN: Reagent Components (BOM)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/reagents/<int:reagent_id>/components")
    def admin_reagent_components(reagent_id):
        parent = Reagent.query.get_or_404(reagent_id)
        reagents = Reagent.query.filter(Reagent.id != reagent_id).order_by(Reagent.name).all()
        reag_opts = [(r.id, r.name) for r in reagents]
        return render_template("admin/reagent_components.html", parent=parent, reag_opts=reag_opts, unit_options=get_unit_options())

    @app.route("/admin/reagents/<int:reagent_id>/components/add", methods=["POST"])
    def admin_reagent_component_add(reagent_id):
        rc = ReagentComponent(
            parent_reagent_id=reagent_id,
            child_reagent_id=int(request.form["child_reagent_id"]),
            quantity=float(request.form["quantity"]),
            quantity_unit=normalize_unit(request.form.get("quantity_unit")),
            per_parent_volume_ml=_float(request.form.get("per_parent_volume_ml")),
        )
        if not is_known_unit(rc.quantity_unit):
            flash("Ungültige Einheit für Komponente.", "danger")
            return redirect(url_for("admin_reagent_components", reagent_id=reagent_id))
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
        amount_units = get_unit_options()
        analysis_mode = resolve_mode(method.analysis.calculation_mode if method.analysis else None)
        return render_template(
            "admin/method_reagents.html",
            method=method,
            reag_opts=reag_opts,
            amount_units=amount_units,
            analysis_mode=analysis_mode,
            can_mark_titrant=_method_supports_titrant_flag(method),
        )

    @app.route("/admin/methods/<int:method_id>/reagents/add", methods=["POST"])
    def admin_method_reagent_add(method_id):
        method = Method.query.get_or_404(method_id)
        is_titrant_requested = "is_titrant" in request.form
        if is_titrant_requested and not _method_supports_titrant_flag(method):
            flash("Titrant-Markierung ist für diesen Methodentyp/Berechnungsmodus nicht zulässig.", "danger")
            return redirect(url_for("admin_method_reagents", method_id=method_id))

        mr = MethodReagent(
            method_id=method_id,
            reagent_id=int(request.form["reagent_id"]),
            amount_per_determination=float(request.form["amount_per_determination"]),
            amount_per_blind=float(request.form.get("amount_per_blind", 0)),
            amount_unit=normalize_unit(request.form.get("amount_unit") or "mL"),
            is_titrant=is_titrant_requested,
            step_description=request.form.get("step_description") or None,
        )
        if not is_known_unit(mr.amount_unit):
            flash("Ungültige Einheit für Methoden-Reagenz.", "danger")
            return redirect(url_for("admin_method_reagents", method_id=method_id))
        if mr.amount_unit_type != AMOUNT_UNIT_VOLUME and mr.is_titrant:
            flash("Titrant-Markierung ist nur für Volumen-Einheiten zulässig.", "danger")
            return redirect(url_for("admin_method_reagents", method_id=method_id))

        if mr.is_titrant:
            MethodReagent.query.filter_by(method_id=method_id, is_titrant=True).update({"is_titrant": False})

        db.session.add(mr)
        db.session.flush()
        _sync_method_titrant_name(method)
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
        db.session.flush()
        method = Method.query.get(mid)
        if method:
            _sync_method_titrant_name(method)
        db.session.commit()
        flash("Zuordnung entfernt.", "warning")
        return redirect(url_for("admin_method_reagents", method_id=mid))

    # ═══════════════════════════════════════════════════════════════
    # SEMESTER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    @app.route("/admin/semesters")
    def admin_semesters():
        items = Semester.query.order_by(Semester.position, Semester.id.desc()).all()
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
                flash_saved("Semester")
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
            item.group_code = request.form.get("group_code") or None
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
                return render_template("admin/student_form.html", item=item, semester=sem, next_num=next_num, group_codes=GROUP_CODES)

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
                return render_template("admin/student_form.html", item=item, semester=sem, next_num=next_num, group_codes=GROUP_CODES)

            if not id:
                db.session.add(item)
            try:
                db.session.commit()
                flash_saved("Studierende")
                return redirect(url_for("admin_students"))
            except IntegrityError:
                db.session.rollback()
                flash("Studierende/r konnte nicht gespeichert werden (Matrikelnummer/Laufnummer muss je Semester eindeutig sein).", "danger")
        next_num = 1
        if sem:
            max_num = db.session.query(db.func.max(Student.running_number)).filter_by(semester_id=sem.id).scalar()
            next_num = (max_num or 0) + 1
        return render_template("admin/student_form.html", item=item, semester=sem, next_num=next_num, group_codes=GROUP_CODES)

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
                missing.append("Matrikel-Nr.")
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
        batches = SampleBatch.query.filter_by(semester_id=sem.id).order_by(SampleBatch.position, SampleBatch.id).all() if sem else []
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

        def _render_form():
            ana_opts = [(a.id, f"{a.code} – {a.name}") for a in analyses]
            lot_opts = [(l.id, f"{l.substance.name} / {l.lot_number} (p={l.p_effective:.1f}%)") for l in lots]
            return render_template("admin/batch_form.html", item=item, ana_opts=ana_opts,
                                   lot_opts=lot_opts, semester=sem, n_students=n_students, analysis_modes=analysis_modes)

        if request.method == "POST":
            item.semester_id = sem.id
            item.analysis_id = int(request.form["analysis_id"])
            analysis = Analysis.query.get(item.analysis_id)
            mode = resolve_mode(analysis.calculation_mode if analysis else None)
            prepared_by = request.form.get("prepared_by") or None

            item.substance_lot_id = _int(request.form.get("substance_lot_id"))
            item.blend_description = request.form.get("blend_description") or None
            item.n_extra_determinations = _int(request.form.get("n_extra_determinations")) if _int(request.form.get("n_extra_determinations")) is not None else 1
            item.mortar_loss_factor = _float(request.form.get("mortar_loss_factor")) or 1.1
            item.gehalt_min_pct = _float(request.form.get("gehalt_min_pct"))
            item.target_m_s_min_g = _float(request.form.get("target_m_s_min_g"))
            item.target_m_ges_g = _float(request.form.get("target_m_ges_g"))
            item.target_v_min_ml = _float(request.form.get("target_v_min_ml"))
            item.target_v_max_ml = _float(request.form.get("target_v_max_ml"))

            # Server-side auto-calculation as fallback (if JS didn't fill values)
            if mode == MODE_ASSAY_MASS_BASED and analysis:
                e_ab = analysis.e_ab_g
                k_det = analysis.k_determinations or 3
                n_extra = item.n_extra_determinations if item.n_extra_determinations is not None else 1
                mortar_f = item.mortar_loss_factor or 1.1
                k_total = k_det + n_extra
                gehalt_min = item.gehalt_min_pct
                if e_ab is not None and gehalt_min is not None:
                    computed_m_ges = round(e_ab * k_total * mortar_f, 3)
                    computed_m_s = round(computed_m_ges * gehalt_min / 100.0, 3)
                    if item.target_m_ges_g is None:
                        item.target_m_ges_g = computed_m_ges
                    if item.target_m_s_min_g is None:
                        item.target_m_s_min_g = computed_m_s
            item.dilution_factor = _float(request.form.get("dilution_factor"))
            item.dilution_solvent = request.form.get("dilution_solvent") or None
            item.dilution_notes = request.form.get("dilution_notes") or None

            requested_titer = _float(request.form.get("titer"))
            manual_override = request.form.get("titer_override") == "1"
            auto_titer = resolve_standardization_titer(sem.id)

            if mode == MODE_TITRANT_STANDARDIZATION:
                item.titer = requested_titer if requested_titer is not None else 1.0
                item.titer_source = "fixed_for_standardization"
                item.titer_source_date = date.today().isoformat()
                item.titer_source_operator = prepared_by or "Praktikumsleitung"
            elif auto_titer and not manual_override:
                item.titer = auto_titer["value"]
                item.titer_source = "standardization_result"
                item.titer_source_date = auto_titer["date"]
                item.titer_source_operator = auto_titer["operator"]
            else:
                if requested_titer is None:
                    flash("Kein auto-abgeleiteter Faktor verfügbar. Bitte manuellen Faktor angeben und als Override markieren.", "danger")
                    return _render_form()
                item.titer = requested_titer
                item.titer_source = "manual_override" if manual_override else "manual"
                item.titer_source_date = date.today().isoformat()
                item.titer_source_operator = prepared_by or "Unbekannt"

            item.prepared_by = prepared_by
            item.total_samples_prepared = int(request.form["total_samples_prepared"])
            item.preparation_date = request.form.get("preparation_date") or None
            item.notes = request.form.get("notes") or None

            if mode == MODE_ASSAY_MASS_BASED:
                if item.target_m_s_min_g is None or item.target_m_ges_g is None:
                    flash("Für massenbasierte Analysen sind Ziel-m_S,min und Ziel-m_ges erforderlich.", "danger")
                    return _render_form()
            elif mode == MODE_TITRANT_STANDARDIZATION:
                if item.target_v_min_ml is None or item.target_v_max_ml is None:
                    flash("Für Titerstandardisierung sind Ziel-V_min und Ziel-V_max erforderlich.", "danger")
                    return _render_form()

            duplicate = SampleBatch.query.filter(
                SampleBatch.semester_id == sem.id,
                SampleBatch.analysis_id == item.analysis_id,
                SampleBatch.id != (item.id or 0),
            ).first()
            if duplicate:
                flash("Für dieses Semester existiert bereits ein Probenansatz für die gewählte Analyse.", "danger")
                return _render_form()
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
                flash_saved("Probenansatz", "Proben generiert")
                return redirect(url_for("admin_batches"))
            except IntegrityError:
                db.session.rollback()
                flash("Probenansatz konnte nicht gespeichert werden (Analyse je Semester nur einmal erlaubt).", "danger")
        return _render_form()

    @app.route("/admin/batches/<int:id>/delete", methods=["POST"])
    def admin_batch_delete(id):
        batch = SampleBatch.query.get_or_404(id)
        force = request.form.get("force") == "1"
        analysis_code = batch.analysis.code
        samples = list(batch.samples)
        total_assignments = sum(len(s.assignments) for s in samples)
        total_results = sum(len(a.results) for s in samples for a in s.assignments)

        if total_assignments and not force:
            flash(
                f"Probenansatz {analysis_code} kann nicht gelöscht werden: "
                f"{total_assignments} Zuweisung(en) und {total_results} Ergebnis(se) vorhanden. "
                "Bitte mit 'Endgueltig loeschen' bestätigen.",
                "danger",
            )
            return redirect(url_for("admin_batches"))

        n_samples = len(samples)
        for sample in samples:
            for assignment in list(sample.assignments):
                db.session.delete(assignment)
            db.session.delete(sample)
        db.session.delete(batch)
        db.session.commit()
        flash(
            f"Probenansatz {analysis_code} gelöscht "
            f"({n_samples} Proben, {total_assignments} Zuweisungen, {total_results} Ergebnisse entfernt).",
            "warning",
        )
        return redirect(url_for("admin_batches"))

    @app.route("/admin/batches/<int:id>/assign-initial", methods=["POST"])
    def admin_batch_assign_initial(id):
        """Erstanalysen zuweisen: Student k → Probe k."""
        batch = SampleBatch.query.get_or_404(id)
        sem = batch.semester
        students = Student.query.filter_by(semester_id=sem.id).order_by(Student.running_number).all()
        samples = Sample.query.filter_by(batch_id=batch.id, is_buffer=False).order_by(Sample.running_number).all()
        count = 0
        skipped_count = 0
        for st in students:
            # Find sample with matching running_number
            sample = next((s for s in samples if s.running_number == st.running_number), None)
            if not sample:
                continue
            # Skip samples not yet weighed
            if not sample.is_weighed:
                skipped_count += 1
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
                sample=sample, student=st, attempt_number=1, attempt_type=attempt_type_for(1),
                assigned_date=date.today().isoformat(), assigned_by="System",
                status="assigned",
            )
            db.session.add(sa)
            count += 1
        db.session.commit()
        total_students = len(students)
        skipped = skipped_count
        if skipped > 0:
            flash(
                f"{count} von {total_students} Erstanalysen zugewiesen "
                f"({skipped} Probe(n) noch nicht eingewogen).",
                "success" if count > 0 else "warning",
            )
        else:
            flash(f"{count} Erstanalysen zugewiesen.", "success")
        return redirect(url_for("admin_batches"))

    @app.route("/admin/batches/<int:batch_id>/samples")
    def admin_batch_samples(batch_id):
        batch = SampleBatch.query.get_or_404(batch_id)
        samples = Sample.query.filter_by(batch_id=batch_id).order_by(Sample.running_number).all()
        return render_template("admin/batch_samples.html", batch=batch, samples=samples)

    @app.route("/admin/samples/<int:sample_id>/delete", methods=["POST"])
    def admin_sample_delete(sample_id):
        sample = Sample.query.get_or_404(sample_id)
        batch_id = sample.batch_id
        force = request.form.get("force") == "1"
        assignments = list(sample.assignments)
        assignment_count = len(assignments)
        result_count = sum(len(assignment.results) for assignment in assignments)

        if assignment_count and not force:
            flash(
                (
                    f"Probe #{sample.running_number} kann nicht gelöscht werden: "
                    f"{assignment_count} Zuweisung(en) und {result_count} Ergebnis(se) vorhanden. "
                    "Bitte Löschung bestätigen, um Probe und Verknüpfungen endgültig zu entfernen."
                ),
                "danger",
            )
            return redirect(url_for("admin_batch_samples", batch_id=batch_id))

        for assignment in assignments:
            db.session.delete(assignment)
        db.session.delete(sample)
        db.session.commit()
        flash(
            (
                f"Probe #{sample.running_number} gelöscht. "
                f"Entfernt: {assignment_count} Zuweisung(en), {result_count} Ergebnis(se)."
            ),
            "warning" if assignment_count else "success",
        )
        return redirect(url_for("admin_batch_samples", batch_id=batch_id))

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
        method = batch.analysis.method if batch.analysis else None
        if method:
            validation_error = _validate_aliquot(method)
            if validation_error:
                flash(f"Inkonsistente Methoden-Konfiguration: {validation_error}", "danger")
                return redirect(url_for("admin_method_form", id=method.id))
        samples = Sample.query.filter_by(batch_id=batch_id).order_by(Sample.running_number).all()
        weighing_flags = {
            s.id: evaluate_weighing_limits(batch, s.m_s_actual_g, s.m_ges_actual_g)
            for s in samples
        }
        if request.method == "POST":
            ignored_empty_fields = 0
            for s in samples:
                m_s_raw = request.form.get(f"m_s_{s.id}")
                m_ges_raw = request.form.get(f"m_ges_{s.id}")
                m_s = (m_s_raw or "").strip()
                m_ges = (m_ges_raw or "").strip()
                if m_s:
                    parsed = _float(m_s)
                    if parsed is not None:
                        s.m_s_actual_g = parsed
                    else:
                        flash(f"Ungültiger Wert für m_S bei Probe {s.running_number}.", "danger")
                elif m_s_raw is not None and s.m_s_actual_g is not None:
                    ignored_empty_fields += 1
                if m_ges:
                    parsed = _float(m_ges)
                    if parsed is not None:
                        s.m_ges_actual_g = parsed
                    else:
                        flash(f"Ungültiger Wert für m_ges bei Probe {s.running_number}.", "danger")
                elif m_ges_raw is not None and s.m_ges_actual_g is not None:
                    ignored_empty_fields += 1
                s.weighed_by = request.form.get("weighed_by") or s.weighed_by
                s.weighed_date = date.today().isoformat()

                flags = evaluate_weighing_limits(batch, s.m_s_actual_g, s.m_ges_actual_g)
                weighing_flags[s.id] = flags
                if flags["out_of_range"]:
                    flash(f"Probe #{s.running_number}: " + "; ".join(flags["messages"]), "danger")
            if ignored_empty_fields:
                flash(
                    "Leere Eingabefelder löschen bestehende Werte nicht. Bitte „Einwaage löschen“ nutzen.",
                    "warning",
                )
            db.session.commit()
            flash_saved("Einwaagen")
            return redirect(url_for("ta_weighing_batch", batch_id=batch_id))
        return render_template(
            "ta/weighing.html",
            batch=batch,
            samples=samples,
            titer_label=mode_titer_label(batch.analysis.calculation_mode),
            weighing_flags=weighing_flags,
            target_m_ges_tolerance_g=TARGET_M_GES_TOLERANCE_G,
        )

    @app.route("/ta/samples/<int:sample_id>/clear-weighing", methods=["POST"])
    def ta_clear_sample_weighing(sample_id):
        sample = Sample.query.get_or_404(sample_id)
        sample.m_s_actual_g = None
        sample.m_ges_actual_g = None
        sample.weighed_by = None
        sample.weighed_date = None
        db.session.commit()
        flash(f"Einwaage für Probe #{sample.running_number} wurde gelöscht.", "success")
        return redirect(url_for("ta_weighing_batch", batch_id=sample.batch_id))

    @app.route("/ta/samples/<int:batch_id>")
    def ta_sample_overview(batch_id):
        batch = SampleBatch.query.get_or_404(batch_id)
        samples = Sample.query.filter_by(batch_id=batch_id).order_by(Sample.running_number).all()
        return render_template("ta/sample_overview.html", batch=batch, samples=samples, titer_label=mode_titer_label(batch.analysis.calculation_mode))

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
            # Build per-student rows (including students without assignments)
            all_students = Student.query.filter_by(semester_id=sem.id).order_by(Student.running_number).all()
            # Map student_id → assignment(s) for this batch
            assignment_map = {}
            for sa in assignments:
                if sa.status != 'cancelled':
                    assignment_map.setdefault(sa.student_id, []).append(sa)

            student_rows = []
            for st in all_students:
                st_assignments = assignment_map.get(st.id, [])
                if st_assignments:
                    for sa in st_assignments:
                        student_rows.append({"student": st, "assignment": sa, "sample_ready": True})
                else:
                    # Check if sample exists and is weighed
                    sample = next(
                        (s for s in batch.samples if s.running_number == st.running_number and not s.is_buffer),
                        None
                    )
                    sample_ready = sample is not None and sample.is_weighed
                    student_rows.append({"student": st, "assignment": None, "sample_ready": sample_ready})

            data[a.code] = {
                "batch": batch,
                "assignments": assignments,
                "buffer_count": len(buffer_samples),
                "student_rows": student_rows,
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
        new_attempt_number = prev_count + 1
        attempt_type = attempt_type_for(new_attempt_number)
        sa = SampleAssignment(
            sample=buffer_sample, student_id=student_id,
            attempt_number=new_attempt_number, attempt_type=attempt_type,
            assigned_date=date.today().isoformat(), assigned_by="Praktikumsleitung",
            status="assigned",
        )
        db.session.add(sa)
        db.session.commit()
        label = "Erstanalyse" if attempt_type == "Erstanalyse" else f"{attempt_type}-Analyse"
        flash(f"Pufferprobe #{buffer_sample.running_number} ({label}) zugewiesen.", "success")
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
        method_config_error = _validate_aliquot(method) if method else None
        if method_config_error:
            missing_requirements.append(f"Methoden-Konfiguration (Einwaage-Basis): {method_config_error}")
        mode = analysis.calculation_mode or MODE_ASSAY_MASS_BASED
        if mode == MODE_ASSAY_MASS_BASED:
            if sample.m_s_actual_g is None or sample.m_ges_actual_g is None:
                missing_requirements.append("Einwaagedaten der Probe")
            if method is None or method.m_eq_mg is None:
                missing_requirements.append("Methodenäquivalent (m_eq)")
            if analysis.tol_min is None or analysis.tol_max is None:
                missing_requirements.append("Toleranzgrenzen")
        elif mode == MODE_TITRANT_STANDARDIZATION:
            # Student reports the calculated titer directly – no weighing data
            # or method equivalent needed from the system side, only tolerance
            # bounds to validate the reported titer against.
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

        weighing_limits = evaluate_weighing_limits(sample.batch, sample.m_s_actual_g, sample.m_ges_actual_g)
        if weighing_limits["out_of_range"]:
            flash(
                f"Ansage blockiert für Probe #{sample.running_number}: " + "; ".join(weighing_limits["messages"]),
                "danger",
            )
            return redirect(url_for("results_overview", analysis_id=analysis.id))

        if request.method == "POST":
            val = _float(request.form.get("ansage_value"))
            if val is None:
                flash("Ungültiger Ansagewert. Bitte eine Zahl eingeben.", "danger")
                return redirect(url_for("results_submit", assignment_id=assignment_id))
            r = Result(
                assignment=assignment,
                ansage_value=val,
                ansage_unit=analysis.result_unit,
            )
            r.evaluate()
            # Compute evaluation label (same logic as live JS)
            if mode == MODE_TITRANT_STANDARDIZATION:
                true_val = assignment.sample.titer_expected
            else:
                true_val = assignment.sample.g_wahr
            r.evaluation_label = compute_evaluation_label(
                ansage_value=val,
                true_value=true_val,
                tol_min_pct=analysis.tol_min,
                tol_max_pct=analysis.tol_max,
                attempt_type=assignment.attempt_type,
            )
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
                flash_saved("Ergebnisse")
            elif r.passed is False:
                if r.a_min is not None and r.a_max is not None:
                    tolerance_text = f"(Toleranz: {r.a_min:.4f} – {r.a_max:.4f})"
                else:
                    tolerance_text = ""
                flash(f"❌ Nicht bestanden. Ansage: {val} {analysis.result_unit} "
                      f"{tolerance_text}".strip(), "danger")
                flash_saved("Ergebnisse")
            else:
                flash("⚠️ Bewertung nicht möglich – Einwaage/Toleranzdaten fehlen.", "warning")
            return redirect(url_for("results_overview", analysis_id=analysis.id))
        # Prepare live-evaluation context for JS (None if tolerances not configured)
        live_eval_ctx = None
        if analysis.tol_min is not None and analysis.tol_max is not None:
            sample = assignment.sample
            if mode == MODE_TITRANT_STANDARDIZATION:
                true_val = sample.titer_expected
                true_value_label = "Titer Soll"
            else:
                true_val = sample.g_wahr
                true_value_label = "G_wahr"
            if true_val is not None:
                v_exp = sample.v_expected if mode != MODE_TITRANT_STANDARDIZATION else None
                live_eval_ctx = {
                    "true_value": true_val,
                    "true_value_label": true_value_label,
                    "tol_min_pct": analysis.tol_min,
                    "tol_max_pct": analysis.tol_max,
                    "attempt_type": assignment.attempt_type,
                    "mode": mode,
                    "a_min": sample.a_min,
                    "a_max": sample.a_max,
                    "result_unit": analysis.result_unit or "",
                    "result_label": analysis.result_label or "",
                    "v_expected_ml": v_exp,
                }
        return render_template("results/submit.html", assignment=assignment, analysis=analysis, titer_label=mode_titer_label(analysis.calculation_mode), live_eval_ctx=live_eval_ctx)

    @app.route("/results/<int:result_id>/revoke", methods=["POST"])
    def result_revoke(result_id):
        """Admin-only: revoke a submitted result and reset assignment to 'assigned'."""
        if not _is_admin_request():
            flash("Nur Admins können Ergebnisse widerrufen.", "danger")
            return redirect(url_for("admin_system"))
        result = Result.query.get_or_404(result_id)
        if result.revoked:
            flash("Dieses Ergebnis ist bereits widerrufen.", "info")
        else:
            assignment = result.assignment
            result.revoked = True
            result.revoked_by = session.get("username", "Admin")
            result.revoked_date = date.today().isoformat()
            assignment.status = "assigned"
            db.session.commit()
            flash(
                f"Ansage {result.ansage_value} {result.ansage_unit} widerrufen. "
                "Zuweisung wieder offen.",
                "warning",
            )
        analysis_id = result.assignment.sample.batch.analysis_id
        return redirect(url_for("results_overview", analysis_id=analysis_id))

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

        # Prefetch all batches and assignments for the semester in bulk
        batches = SampleBatch.query.filter_by(semester_id=sem.id).all()
        batch_by_analysis = {b.analysis_id: b for b in batches}
        batch_ids = [b.id for b in batches]

        all_assignments = (
            SampleAssignment.query
            .join(Sample).filter(Sample.batch_id.in_(batch_ids))
            .order_by(SampleAssignment.attempt_number.desc())
            .all()
        ) if batch_ids else []

        # Index assignments by (student_id, batch_id)
        assgn_index = {}
        for sa in all_assignments:
            key = (sa.student_id, sa.sample.batch_id)
            assgn_index.setdefault(key, []).append(sa)

        # Build progress matrix from prefetched data
        progress = {}
        for st in students:
            progress[st.id] = {}
            for a in analyses:
                batch = batch_by_analysis.get(a.id)
                if not batch:
                    progress[st.id][a.code] = None
                    continue
                assgns = assgn_index.get((st.id, batch.id), [])
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
                formula_kind = "volumetric" if mr.amount_unit_type == AMOUNT_UNIT_VOLUME else "generic"
                total = n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * safety
                demand.append({
                    "analysis": analysis.code,
                    "analysis_name": analysis.name,
                    "reagent": mr.reagent.name,
                    "unit": canonical_unit_label(mr.amount_unit),
                    "per_det": mr.amount_per_determination,
                    "per_blind": mr.amount_per_blind,
                    "formula_kind": formula_kind,
                    "k": k,
                    "b": b,
                    "n": n,
                    "total": round(total, 1),
                    "is_titrant": mr.is_titrant,
                })
        has_non_volume_units = any(get_amount_unit_type(d["unit"]) != AMOUNT_UNIT_VOLUME for d in demand)
        return render_template("reports/reagents.html", semester=sem, demand=demand, has_non_volume_units=has_non_volume_units)

    @app.route("/admin/system")
    def admin_system():
        return render_template("admin/system.html", db_uri=app.config.get("SQLALCHEMY_DATABASE_URI", ""), is_admin=_is_admin_request())

    @app.route("/admin/backup/database")
    def admin_backup_database():
        if not _is_admin_request():
            flash("Backup-Download nur mit Admin-Rolle erlaubt (optional via ?token=...).", "danger")
            return redirect(url_for("admin_system"))
        db_path = _db_file_path()
        if not db_path or not os.path.exists(db_path):
            flash("SQLite-Datei nicht gefunden oder kein SQLite-Backend aktiv.", "danger")
            return redirect(url_for("admin_system"))
        return send_file(db_path, as_attachment=True, download_name=os.path.basename(db_path), mimetype="application/x-sqlite3")

    @app.route("/export/semesters.<fmt>")
    def export_semesters(fmt):
        if fmt not in {"csv", "json"}:
            return ("Unsupported format", 400)
        rows = [{
            "id": s.id, "code": s.code, "name": s.name, "start_date": s.start_date,
            "end_date": s.end_date, "is_active": s.is_active, "students_count": len(s.students),
        } for s in Semester.query.order_by(Semester.id).all()]
        return _dict_rows(rows, "semesters", fmt)

    @app.route("/export/students.<fmt>")
    def export_students(fmt):
        if fmt not in {"csv", "json"}:
            return ("Unsupported format", 400)
        sem = active_semester()
        query = Student.query.order_by(Student.semester_id, Student.running_number)
        if sem:
            query = query.filter_by(semester_id=sem.id)
        rows = [{
            "id": st.id, "semester_id": st.semester_id, "semester_code": st.semester.code if st.semester else None,
            "matrikel": st.matrikel, "last_name": st.last_name, "first_name": st.first_name,
            "running_number": st.running_number, "email": st.email,
        } for st in query.all()]
        return _dict_rows(rows, "students", fmt)

    @app.route("/export/results.<fmt>")
    def export_results(fmt):
        if fmt not in {"csv", "json"}:
            return ("Unsupported format", 400)
        rows = []
        assignments = (
            SampleAssignment.query
            .join(Sample, SampleAssignment.sample_id == Sample.id)
            .join(SampleBatch, Sample.batch_id == SampleBatch.id)
            .join(Analysis, SampleBatch.analysis_id == Analysis.id)
            .join(Student, SampleAssignment.student_id == Student.id)
            .outerjoin(Result, Result.assignment_id == SampleAssignment.id)
            .order_by(SampleBatch.semester_id, Analysis.ordinal, Student.running_number, SampleAssignment.id)
            .all()
        )
        for sa in assignments:
            latest = sa.latest_result
            rows.append({
                "assignment_id": sa.id, "semester_code": sa.sample.batch.semester.code if sa.sample and sa.sample.batch and sa.sample.batch.semester else None,
                "analysis_code": sa.sample.batch.analysis.code if sa.sample and sa.sample.batch and sa.sample.batch.analysis else None,
                "student_matrikel": sa.student.matrikel if sa.student else None, "student_name": sa.student.full_name if sa.student else None,
                "attempt_type": sa.attempt_type, "status": sa.status,
                "ansage_value": latest.ansage_value if latest else None,
                "ansage_unit": latest.ansage_unit if latest else None,
                "passed": latest.passed if latest else None,
                "submitted_date": latest.submitted_date if latest else None,
            })
        return _dict_rows(rows, "results", fmt)

    @app.route("/export/reagents-demand.<fmt>")
    def export_reagents_demand(fmt):
        if fmt not in {"csv", "json"}:
            return ("Unsupported format", 400)
        sem = active_semester()
        if not sem:
            return _dict_rows([], "reagents_demand", fmt)
        rows = []
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
                total = n * (k * mr.amount_per_determination + b * mr.amount_per_blind) * 1.2
                rows.append({
                    "semester_code": sem.code, "analysis_code": analysis.code, "analysis_name": analysis.name,
                    "reagent": mr.reagent.name if mr.reagent else None, "amount_per_determination": mr.amount_per_determination,
                    "amount_per_blind": mr.amount_per_blind, "k": k, "b": b, "n": n,
                    "total_with_safety": round(total, 1), "unit": canonical_unit_label(mr.amount_unit), "is_titrant": mr.is_titrant,
                })
        return _dict_rows(rows, "reagents_demand", fmt)

    # ═══════════════════════════════════════════════════════════════
    # API endpoints (for HTMX / JS)
    # ═══════════════════════════════════════════════════════════════
    @app.route("/api/reorder/students", methods=["POST"])
    def api_reorder_students():
        """Update running_number for students based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        # Two-pass approach to avoid unique constraint violations
        students = []
        for idx, student_id in enumerate(data["order"], 1):
            st = Student.query.get(student_id)
            if st:
                st.running_number = -(idx)
                students.append((st, idx))
        try:
            db.session.flush()
            for st, idx in students:
                st.running_number = idx
            db.session.commit()
            return jsonify({"ok": True})
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Unique constraint conflict"}), 409

    @app.route("/api/reorder/analyses", methods=["POST"])
    def api_reorder_analyses():
        """Update ordinal for analyses based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        # Two-pass approach to avoid unique constraint violations
        items = []
        for idx, analysis_id in enumerate(data["order"], 1):
            a = Analysis.query.get(analysis_id)
            if a:
                a.ordinal = -(idx)
                items.append((a, idx))
        try:
            db.session.flush()
            for a, idx in items:
                a.ordinal = idx
            db.session.commit()
            return jsonify({"ok": True})
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Conflict"}), 409

    @app.route("/api/reorder/semesters", methods=["POST"])
    def api_reorder_semesters():
        """Update position for semesters based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        for idx, item_id in enumerate(data["order"], 1):
            item = Semester.query.get(item_id)
            if item:
                item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reorder/substances", methods=["POST"])
    def api_reorder_substances():
        """Update position for substances based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        for idx, item_id in enumerate(data["order"], 1):
            item = Substance.query.get(item_id)
            if item:
                item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reorder/lots", methods=["POST"])
    def api_reorder_lots():
        """Update position for substance lots based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        for idx, item_id in enumerate(data["order"], 1):
            item = SubstanceLot.query.get(item_id)
            if item:
                item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reorder/reagents", methods=["POST"])
    def api_reorder_reagents():
        """Update position for reagents based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        for idx, item_id in enumerate(data["order"], 1):
            item = Reagent.query.get(item_id)
            if item:
                item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reorder/batches", methods=["POST"])
    def api_reorder_batches():
        """Update position for sample batches based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        for idx, item_id in enumerate(data["order"], 1):
            item = SampleBatch.query.get(item_id)
            if item:
                item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reorder/methods", methods=["POST"])
    def api_reorder_methods():
        """Update position for methods based on drag & drop order."""
        data = request.get_json()
        if not data or "order" not in data:
            return jsonify({"error": "Missing order"}), 400
        for idx, item_id in enumerate(data["order"], 1):
            item = Method.query.get(item_id)
            if item:
                item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reorder/reset/<entity>", methods=["POST"])
    def api_reorder_reset(entity):
        """Reset position to natural order (alphabetic/chronological)."""
        if entity == "semesters":
            items = Semester.query.order_by(Semester.id.desc()).all()
        elif entity == "substances":
            items = Substance.query.order_by(Substance.name).all()
        elif entity == "lots":
            items = SubstanceLot.query.order_by(SubstanceLot.id.desc()).all()
        elif entity == "reagents":
            items = Reagent.query.order_by(Reagent.name).all()
        elif entity == "batches":
            sem = active_semester()
            items = SampleBatch.query.filter_by(semester_id=sem.id).join(Analysis).order_by(Analysis.ordinal).all() if sem else []
        elif entity == "methods":
            items = Method.query.join(Analysis).order_by(Analysis.ordinal).all()
        else:
            return jsonify({"error": "Unknown entity"}), 400
        for idx, item in enumerate(items, 1):
            item.position = idx
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/analysis/<int:analysis_id>/defaults")
    def api_analysis_defaults(analysis_id):
        """Return method defaults for a given analysis (for batch form auto-fill)."""
        analysis = Analysis.query.get_or_404(analysis_id)
        method = analysis.method
        result = {
            "e_ab_g": analysis.e_ab_g,
            "k_determinations": analysis.k_determinations,
            "g_ab_min_pct": analysis.g_ab_min_pct,
            "g_ab_max_pct": analysis.g_ab_max_pct,
            "calculation_mode": resolve_mode(analysis.calculation_mode),
            "molar_mass_gmol": analysis.substance.molar_mass_gmol if analysis.substance else None,
        }
        if method:
            result["m_eq_mg"] = method.m_eq_mg
            result["titrant_concentration"] = method.titrant_concentration
            result["method_type"] = method.method_type
            result["v_vorlage_ml"] = method.v_vorlage_ml
            result["c_titrant_mol_l"] = method.c_titrant_mol_l
            result["n_eq_titrant"] = method.n_eq_titrant
            result["c_vorlage_mol_l"] = method.c_vorlage_mol_l
            result["n_eq_vorlage"] = method.n_eq_vorlage
            # For titrant standardization: compute theoretical volume from primary standard
            if (
                method.e_ab_ps_g is not None
                and method.m_eq_primary_mg is not None
                and method.m_eq_primary_mg > 0
            ):
                v_theoretical = (method.e_ab_ps_g * 1000.0) / method.m_eq_primary_mg
                result["v_theoretical_ml"] = round(v_theoretical, 3)
            # Dispensing volume from stock (correct formula for TA)
            if (
                method.v_dilution_ml is not None
                and method.c_titrant_mol_l is not None
                and method.c_titrant_mol_l > 0
                and method.c_stock_mol_l is not None
                and method.c_stock_mol_l > 0
            ):
                v_disp_theoretical = (
                    method.v_dilution_ml * method.c_titrant_mol_l / method.c_stock_mol_l
                )
                result["v_disp_theoretical_ml"] = round(v_disp_theoretical, 4)
        return jsonify(result)

    @app.route("/admin/practical-days")
    def admin_practical_days():
        days = PracticalDay.query.order_by(PracticalDay.date).all()
        return render_template("admin/practical_days.html", days=days)

    @app.route("/admin/practical-days/new", methods=["GET", "POST"])
    def admin_practical_day_new():
        blocks = Block.query.order_by(Block.code).all()
        if request.method == "POST":
            day = PracticalDay(
                semester_id=_get_active_semester_id(),
                block_id=int(request.form["block_id"]),
                date=request.form["date"],
                day_type=request.form["day_type"],
                block_day_number=int(request.form["block_day_number"]) if request.form.get("block_day_number") else None,
                notes=request.form.get("notes") or None,
            )
            db.session.add(day)
            try:
                db.session.commit()
                flash("Praktikumstag gespeichert.", "success")
                return redirect(url_for("admin_practical_days"))
            except IntegrityError:
                db.session.rollback()
                flash("Datum bereits vergeben für dieses Semester.", "danger")
                return render_template("admin/practical_day_form.html", day=None, blocks=blocks)
        return render_template("admin/practical_day_form.html", day=None, blocks=blocks)

    @app.route("/admin/practical-days/<int:day_id>/edit", methods=["GET", "POST"])
    def admin_practical_day_edit(day_id):
        day = db.get_or_404(PracticalDay, day_id)
        blocks = Block.query.order_by(Block.code).all()
        if request.method == "POST":
            day.block_id = int(request.form["block_id"])
            day.date = request.form["date"]
            day.day_type = request.form["day_type"]
            day.block_day_number = int(request.form["block_day_number"]) if request.form.get("block_day_number") else None
            day.notes = request.form.get("notes") or None
            try:
                db.session.commit()
                flash("Praktikumstag aktualisiert.", "success")
                return redirect(url_for("admin_practical_days"))
            except IntegrityError:
                db.session.rollback()
                flash("Datum bereits vergeben für dieses Semester.", "danger")
                return render_template("admin/practical_day_form.html", day=day, blocks=blocks)
        return render_template("admin/practical_day_form.html", day=day, blocks=blocks)

    @app.route("/admin/practical-days/<int:day_id>/delete", methods=["POST"])
    def admin_practical_day_delete(day_id):
        day = db.get_or_404(PracticalDay, day_id)
        db.session.delete(day)
        db.session.commit()
        flash("Praktikumstag gelöscht.", "success")
        return redirect(url_for("admin_practical_days"))

    @app.route("/api/sample/<int:sample_id>/calc")
    def api_sample_calc(sample_id):
        s = Sample.query.get_or_404(sample_id)
        return jsonify({
            "g_wahr": round(s.g_wahr, 4) if s.g_wahr is not None else None,
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
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _int(val):
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ── Entry point ──────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
