"""Quanti-LIMS ORM models (SQLAlchemy / SQLite)."""

from __future__ import annotations

from datetime import date
from flask_sqlalchemy import SQLAlchemy

from calculation_modes import (
    MODE_ASSAY_MASS_BASED,
    MODE_MASS_DETERMINATION,
    MODE_TITRANT_STANDARDIZATION,
    get_evaluator,
    resolve_mode,
)

db = SQLAlchemy()

AMOUNT_UNIT_MASS = "mass"
AMOUNT_UNIT_VOLUME = "volume"
AMOUNT_UNIT_COUNT = "count"


UNIT_DEFINITIONS = (
    ("mg", "mg", AMOUNT_UNIT_MASS),
    ("g", "g", AMOUNT_UNIT_MASS),
    ("kg", "kg", AMOUNT_UNIT_MASS),
    ("µL", "µL", AMOUNT_UNIT_VOLUME),
    ("mL", "mL", AMOUNT_UNIT_VOLUME),
    ("L", "L", AMOUNT_UNIT_VOLUME),
    ("pcs", "pcs", AMOUNT_UNIT_COUNT),
)
UNIT_CODES = tuple(code for code, _, _ in UNIT_DEFINITIONS)
AMOUNT_UNIT_TYPES = {code: category for code, _, category in UNIT_DEFINITIONS}
UNIT_LABELS = {code: label for code, label, _ in UNIT_DEFINITIONS}
UNIT_CANONICAL_MAP = {
    "ul": "µL",
    "μl": "µL",
    "µl": "µL",
    "ml": "mL",
    "l": "L",
    "mg": "mg",
    "g": "g",
    "kg": "kg",
    "pcs": "pcs",
    "stk": "pcs",
    "piece": "pcs",
    "pieces": "pcs",
}
UNIT_ENUM = db.Enum(*UNIT_CODES, name="unit_code", native_enum=False, create_constraint=True, validate_strings=True)

GROUP_CODES = ("A", "B", "C", "D")
GROUP_CODE_ENUM = db.Enum(*GROUP_CODES, name="group_code_enum",
                          native_enum=False, create_constraint=True,
                          validate_strings=True)

PRACTICAL_DAY_TYPES = ("normal", "nachkochtag")
PRACTICAL_DAY_TYPE_ENUM = db.Enum(*PRACTICAL_DAY_TYPES, name="practical_day_type",
                                   native_enum=False, create_constraint=True,
                                   validate_strings=True)

DUTY_TYPES = ("Saaldienst", "Entsorgungsdienst")
DUTY_TYPE_ENUM = db.Enum(*DUTY_TYPES, name="duty_type_enum",
                          native_enum=False, create_constraint=True,
                          validate_strings=True)


def normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    compact = unit.strip()
    if not compact:
        return None
    return UNIT_CANONICAL_MAP.get(compact.lower(), compact if compact in UNIT_CODES else None)


def is_known_unit(unit: str | None) -> bool:
    return normalize_unit(unit) in UNIT_CODES


def get_unit_options() -> list[tuple[str, str]]:
    return [(code, label) for code, label, _ in UNIT_DEFINITIONS]


def canonical_unit_label(unit: str | None) -> str:
    normalized = normalize_unit(unit)
    if normalized is None:
        return unit or ""
    return UNIT_LABELS.get(normalized, normalized)


def get_amount_unit_type(unit: str | None) -> str:
    normalized = normalize_unit(unit)
    return AMOUNT_UNIT_TYPES.get(normalized or "", AMOUNT_UNIT_COUNT)

# ── Stammdaten ────────────────────────────────────────────────────────────

class Block(db.Model):
    __tablename__ = "block"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    max_days = db.Column(db.Integer, nullable=True)  # Orientation value; not a hard constraint

    analyses = db.relationship("Analysis", back_populates="block", order_by="Analysis.ordinal")
    colloquiums = db.relationship("Colloquium", back_populates="block")

    def __repr__(self):
        return f"<Block {self.code}>"


class Substance(db.Model):
    __tablename__ = "substance"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    formula = db.Column(db.String(100))
    molar_mass_gmol = db.Column(db.Float)
    anhydrous_molar_mass_gmol = db.Column(db.Float, nullable=True)  # For hydrate correction (e.g. Li citrate tetrahydrate)
    e_ab_g = db.Column(db.Float)
    g_ab_min_pct = db.Column(db.Float)
    g_ab_max_pct = db.Column(db.Float)
    notes = db.Column(db.Text)
    position = db.Column(db.Integer, nullable=False, default=0)

    lots = db.relationship("SubstanceLot", back_populates="substance")
    analyses = db.relationship("Analysis", back_populates="substance")

    def __repr__(self):
        return f"<Substance {self.name}>"


class SubstanceLot(db.Model):
    __tablename__ = "substance_lot"
    id = db.Column(db.Integer, primary_key=True)
    substance_id = db.Column(db.Integer, db.ForeignKey("substance.id"), nullable=False)
    lot_number = db.Column(db.String(100), nullable=False)
    supplier = db.Column(db.String(200))
    receipt_date = db.Column(db.String(20))
    g_coa_pct = db.Column(db.Float)
    coa_date = db.Column(db.String(20))
    coa_valid_until = db.Column(db.String(20))
    g_analytical_pct = db.Column(db.Float)
    g_analytical_date = db.Column(db.String(20))
    g_analytical_method = db.Column(db.String(100))
    notes = db.Column(db.Text)
    position = db.Column(db.Integer, nullable=False, default=0)

    substance = db.relationship("Substance", back_populates="lots")
    batches = db.relationship("SampleBatch", back_populates="substance_lot")

    __table_args__ = (db.UniqueConstraint("substance_id", "lot_number"),)

    @property
    def p_effective(self) -> float:
        """Effektive Reinheit nach Prioritäts-Hierarchie."""
        if self.g_analytical_pct is not None:
            return self.g_analytical_pct
        if self.g_coa_pct is not None:
            return self.g_coa_pct
        return 100.0

    @property
    def p_source(self) -> str:
        if self.g_analytical_pct is not None:
            return "analytisch"
        if self.g_coa_pct is not None:
            return "CoA"
        return "Standard (100 %)"


class Analysis(db.Model):
    __tablename__ = "analysis"
    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    ordinal = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    substance_id = db.Column(db.Integer, db.ForeignKey("substance.id"), nullable=False)
    k_determinations = db.Column(db.Integer, nullable=False, default=3)
    result_unit = db.Column(db.String(20), nullable=False, default="%")
    result_label = db.Column(db.String(50), nullable=False, default="Gehalt")
    calculation_mode = db.Column(db.String(50), nullable=False, default=MODE_ASSAY_MASS_BASED)
    e_ab_g = db.Column(db.Float)
    g_ab_min_pct = db.Column(db.Float)
    g_ab_max_pct = db.Column(db.Float)
    source_reference = db.Column(db.String(255))
    tolerance_override_min_pct = db.Column(db.Float)
    tolerance_override_max_pct = db.Column(db.Float)
    notes = db.Column(db.Text)
    m_einwaage_min_mg = db.Column(db.Float, nullable=True)  # Min TA weighing mass (mass_determination mode, mg)
    m_einwaage_max_mg = db.Column(db.Float, nullable=True)  # Max TA weighing mass (mass_determination mode, mg)
    reported_molar_mass_gmol = db.Column(db.Float, nullable=True)
    reported_stoichiometry = db.Column(db.Float, nullable=True)

    block = db.relationship("Block", back_populates="analyses")
    substance = db.relationship("Substance", back_populates="analyses")
    method = db.relationship("Method", back_populates="analysis", uselist=False)
    batches = db.relationship("SampleBatch", back_populates="analysis")

    @property
    def tol_min(self) -> float | None:
        if self.tolerance_override_min_pct is not None:
            return self.tolerance_override_min_pct
        if self.g_ab_min_pct is not None:
            return self.g_ab_min_pct
        if self.substance and self.substance.g_ab_min_pct is not None:
            return self.substance.g_ab_min_pct
        return None

    @property
    def tol_max(self) -> float | None:
        if self.tolerance_override_max_pct is not None:
            return self.tolerance_override_max_pct
        if self.g_ab_max_pct is not None:
            return self.g_ab_max_pct
        if self.substance and self.substance.g_ab_max_pct is not None:
            return self.substance.g_ab_max_pct
        return None


class Method(db.Model):
    __tablename__ = "method"
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analysis.id"), nullable=False)
    method_type = db.Column(db.String(30), nullable=False)  # direct, back, gravimetric, ...
    m_eq_mg = db.Column(db.Float)
    titrant_name = db.Column(db.String(200))
    titrant_concentration = db.Column(db.String(50))
    # Explicit titration parameters (preferred over m_eq_mg)
    c_titrant_mol_l = db.Column(db.Float)      # Numeric concentration of titrant (mol/L)
    n_eq_titrant = db.Column(db.Float)          # Equivalents of titrant per mol analyte (direct) or per mol Vorlage (back)
    c_vorlage_mol_l = db.Column(db.Float)       # Concentration of Vorlage reagent (back-titration only)
    n_eq_vorlage = db.Column(db.Float)          # Equivalents of Vorlage consumed per mol analyte (back-titration only)
    blind_required = db.Column(db.Boolean, nullable=False, default=False)
    b_blind_determinations = db.Column(db.Integer, nullable=False, default=1)
    v_vorlage_ml = db.Column(db.Float)
    v_solution_ml = db.Column(db.Float)       # Total volume substance is dissolved to (e.g. 100.0 mL)
    v_aliquot_ml = db.Column(db.Float)        # Aliquot volume taken for each titration (e.g. 20.0 mL)
    aliquot_enabled = db.Column(db.Boolean, nullable=True, default=None)
    primary_standard_id = db.Column(db.Integer, db.ForeignKey("reagent.id"))
    m_eq_primary_mg = db.Column(db.Float)
    m_eq_primary_mg_override = db.Column(db.Boolean, nullable=False, default=False)  # True → use stored value; False → auto-calculate from c_Titrant × MW_PS / z
    e_ab_ps_g = db.Column(db.Float)          # Arzneibuch-Einwaage Primärstandard (g) – per method, not per reagent
    c_stock_mol_l = db.Column(db.Float)      # Stammkonzentration (mol/L), z.B. 1.0 für 1M HCl
    v_dilution_ml = db.Column(db.Float)      # Verdünnungsvolumen (mL), z.B. 100.0
    description = db.Column(db.Text)
    position = db.Column(db.Integer, nullable=False, default=0)

    analysis = db.relationship("Analysis", back_populates="method")
    primary_standard = db.relationship("Reagent", foreign_keys=[primary_standard_id], back_populates="primary_standard_methods")
    reagent_usages = db.relationship("MethodReagent", back_populates="method")

    @property
    def titrant_reagent_usage(self) -> MethodReagent | None:
        return next((usage for usage in self.reagent_usages if usage.is_titrant), None)

    @property
    def derived_titrant_name(self) -> str | None:
        usage = self.titrant_reagent_usage
        if usage and usage.reagent:
            return usage.reagent.name
        return self.titrant_name

    @property
    def aliquot_fraction(self) -> float:
        if self.aliquot_enabled is False:
            return 1.0
        if self.v_solution_ml and self.v_aliquot_ml and self.v_solution_ml > 0:
            return self.v_aliquot_ml / self.v_solution_ml
        return 1.0

    @property
    def has_aliquot(self) -> bool:
        if self.aliquot_enabled is False:
            return False
        return bool(self.v_solution_ml and self.v_aliquot_ml)


# ── Reagenzien-BOM ────────────────────────────────────────────────────────

class Reagent(db.Model):
    __tablename__ = "reagent"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    abbreviation = db.Column(db.String(50))
    is_composite = db.Column(db.Boolean, nullable=False, default=False)
    is_primary_standard = db.Column(db.Boolean, nullable=False, default=False)
    formula = db.Column(db.String(100))
    molar_mass_gmol = db.Column(db.Float)
    e_ab_g = db.Column(db.Float)
    base_unit = db.Column(UNIT_ENUM, nullable=False, default="mL")
    cas_number = db.Column(db.String(30))
    density_g_ml = db.Column(db.Float)
    hazard_symbols = db.Column(db.String(100))
    storage_info = db.Column(db.String(200))
    notes = db.Column(db.Text)
    position = db.Column(db.Integer, nullable=False, default=0)

    components = db.relationship(
        "ReagentComponent",
        foreign_keys="ReagentComponent.parent_reagent_id",
        back_populates="parent",
    )
    method_usages = db.relationship("MethodReagent", back_populates="reagent")
    primary_standard_methods = db.relationship("Method", back_populates="primary_standard")


class ReagentComponent(db.Model):
    __tablename__ = "reagent_component"
    id = db.Column(db.Integer, primary_key=True)
    parent_reagent_id = db.Column(db.Integer, db.ForeignKey("reagent.id"), nullable=False)
    child_reagent_id = db.Column(db.Integer, db.ForeignKey("reagent.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    quantity_unit = db.Column(UNIT_ENUM, nullable=False)
    per_parent_volume_ml = db.Column(db.Float)
    notes = db.Column(db.Text)

    parent = db.relationship("Reagent", foreign_keys=[parent_reagent_id], back_populates="components")
    child = db.relationship("Reagent", foreign_keys=[child_reagent_id])


class MethodReagent(db.Model):
    __tablename__ = "method_reagent"
    id = db.Column(db.Integer, primary_key=True)
    method_id = db.Column(db.Integer, db.ForeignKey("method.id"), nullable=False)
    reagent_id = db.Column(db.Integer, db.ForeignKey("reagent.id"), nullable=False)
    amount_per_determination = db.Column(db.Float, nullable=False)
    amount_per_blind = db.Column(db.Float, nullable=False, default=0)
    amount_unit = db.Column(UNIT_ENUM, nullable=False, default="mL")
    is_titrant = db.Column(db.Boolean, nullable=False, default=False)
    step_description = db.Column(db.Text)
    notes = db.Column(db.Text)

    method = db.relationship("Method", back_populates="reagent_usages")
    reagent = db.relationship("Reagent", back_populates="method_usages")

    @property
    def amount_unit_type(self) -> str:
        return get_amount_unit_type(self.amount_unit)


# ── Semesterbetrieb ───────────────────────────────────────────────────────

class Semester(db.Model):
    __tablename__ = "semester"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    active_group_count = db.Column(db.Integer, nullable=False, default=4)

    students = db.relationship("Student", back_populates="semester", order_by="Student.running_number")
    batches = db.relationship("SampleBatch", back_populates="semester")


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semester.id"), nullable=False)
    matrikel = db.Column(db.String(20), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    running_number = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(200))
    group_code = db.Column(GROUP_CODE_ENUM, nullable=True)
    is_excluded = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)

    semester = db.relationship("Semester", back_populates="students")
    colloquiums = db.relationship("Colloquium", back_populates="student", cascade="all, delete-orphan")
    assignments = db.relationship(
        "SampleAssignment",
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.UniqueConstraint("semester_id", "matrikel"),
        db.UniqueConstraint("semester_id", "running_number"),
    )

    @property
    def full_name(self):
        return f"{self.last_name}, {self.first_name}"


class Colloquium(db.Model):
    __tablename__ = "colloquium"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    scheduled_date = db.Column(db.String(20), nullable=True)
    conducted_date = db.Column(db.String(20), nullable=True)
    examiner = db.Column(db.String(200), nullable=True)
    passed = db.Column(db.Boolean, nullable=True)  # None = not yet held
    notes = db.Column(db.Text, nullable=True)

    student = db.relationship("Student", back_populates="colloquiums")
    block = db.relationship("Block", back_populates="colloquiums")

    __table_args__ = (
        db.UniqueConstraint("student_id", "block_id", "attempt_number"),
    )

    @property
    def status_label(self) -> str:
        if self.passed is True:
            return "Bestanden"
        if self.passed is False:
            return "Nicht bestanden"
        if self.scheduled_date:
            return "Geplant"
        return "Nicht geplant"

    @property
    def attempt_label(self) -> str:
        labels = {1: "Erstversuch", 2: "Nachholkolloquium", 3: "beim Chef"}
        return labels.get(self.attempt_number, f"Versuch {self.attempt_number}")


class SampleBatch(db.Model):
    __tablename__ = "sample_batch"
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semester.id"), nullable=False)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analysis.id"), nullable=False)
    substance_lot_id = db.Column(db.Integer, db.ForeignKey("substance_lot.id"))
    blend_description = db.Column(db.String(500))
    gehalt_min_pct = db.Column(db.Float)
    n_extra_determinations = db.Column(db.Integer, nullable=False, default=1)
    mortar_loss_factor = db.Column(db.Float, nullable=False, default=1.1)
    target_m_s_min_g = db.Column(db.Float)
    target_m_ges_g = db.Column(db.Float)
    target_v_min_ml = db.Column(db.Float)
    target_v_max_ml = db.Column(db.Float)
    dilution_factor = db.Column(db.Float)
    dilution_solvent = db.Column(db.String(120))
    dilution_notes = db.Column(db.Text)
    titer = db.Column(db.Float, nullable=False, default=1.000)
    titer_source = db.Column(db.String(40), nullable=False, default="manual")
    titer_source_date = db.Column(db.String(20))
    titer_source_operator = db.Column(db.String(100))
    total_samples_prepared = db.Column(db.Integer, nullable=False)
    preparation_date = db.Column(db.String(20))
    prepared_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    safety_factor = db.Column(db.Float, nullable=False, default=1.2)

    position = db.Column(db.Integer, nullable=False, default=0)

    semester = db.relationship("Semester", back_populates="batches")
    analysis = db.relationship("Analysis", back_populates="batches")
    substance_lot = db.relationship("SubstanceLot", back_populates="batches")
    samples = db.relationship("Sample", back_populates="batch", order_by="Sample.running_number")

    __table_args__ = (db.UniqueConstraint("semester_id", "analysis_id"),)

    @property
    def p_effective(self) -> float:
        if self.substance_lot:
            return self.substance_lot.p_effective
        return 100.0

    @property
    def p_source(self) -> str:
        if self.substance_lot:
            return self.substance_lot.p_source
        return "Standard (100 %)"


    @property
    def titer_label(self) -> str:
        mode = resolve_mode(self.analysis.calculation_mode if self.analysis else None)
        if mode == MODE_ASSAY_MASS_BASED:
            return "Faktor"
        return "Titer"

    @property
    def titer_source_label(self) -> str:
        mapping = {
            "standardization_result": "aus Einstellung übernommen",
            "manual_override": "manuell überschrieben",
            "fixed_for_standardization": "fix für Einstellanalyse",
            "manual": "manuell gesetzt",
        }
        return mapping.get(self.titer_source or "manual", "manuell gesetzt")

class Sample(db.Model):
    __tablename__ = "sample"
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("sample_batch.id"), nullable=False)
    running_number = db.Column(db.Integer, nullable=False)
    m_s_actual_g = db.Column(db.Float)
    m_ges_actual_g = db.Column(db.Float)
    is_buffer = db.Column(db.Boolean, nullable=False, default=False)
    weighed_by = db.Column(db.String(100))
    weighed_date = db.Column(db.String(20))
    notes = db.Column(db.Text)

    batch = db.relationship("SampleBatch", back_populates="samples")
    assignments = db.relationship("SampleAssignment", back_populates="sample")

    __table_args__ = (db.UniqueConstraint("batch_id", "running_number"),)

    def _calc(self):
        if not hasattr(self, '_calc_cache'):
            evaluator = get_evaluator(self.batch.analysis.calculation_mode)
            self._calc_cache = evaluator.calculate_sample(self)
        return self._calc_cache

    @property
    def g_wahr(self) -> float | None:
        return self._calc().g_wahr

    @property
    def a_min(self) -> float | None:
        return self._calc().a_min

    @property
    def a_max(self) -> float | None:
        return self._calc().a_max

    @property
    def v_expected(self) -> float | None:
        return self._calc().v_expected_ml

    @property
    def titer_expected(self) -> float | None:
        return self._calc().titer_expected

    @property
    def is_weighed(self) -> bool:
        mode = resolve_mode(self.batch.analysis.calculation_mode if self.batch and self.batch.analysis else None)
        if mode == MODE_TITRANT_STANDARDIZATION:
            return self.m_ges_actual_g is not None
        if mode == MODE_MASS_DETERMINATION:
            return self.m_s_actual_g is not None
        return self.m_s_actual_g is not None and self.m_ges_actual_g is not None

    @property
    def active_assignment(self):
        """Most recent non-cancelled assignment."""
        for a in sorted(self.assignments, key=lambda x: x.attempt_number, reverse=True):
            if a.status != "cancelled":
                return a
        return None


class SampleAssignment(db.Model):
    __tablename__ = "sample_assignment"
    id = db.Column(db.Integer, primary_key=True)
    sample_id = db.Column(db.Integer, db.ForeignKey("sample.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    attempt_type = db.Column(db.String(20), nullable=False, default="Erstanalyse")
    assigned_date = db.Column(db.String(20), nullable=False)
    assigned_by = db.Column(db.String(100))
    status = db.Column(db.String(20), nullable=False, default="assigned")
    notes = db.Column(db.Text)

    sample = db.relationship("Sample", back_populates="assignments")
    student = db.relationship("Student", back_populates="assignments")
    results = db.relationship(
        "Result",
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Result.id",
    )

    @property
    def latest_result(self):
        if self.results:
            return self.results[-1]
        return None

    @property
    def active_result(self):
        """The most recent non-revoked result, or None."""
        for r in sorted(self.results, key=lambda r: r.id, reverse=True):
            if not r.revoked:
                return r
        return None


class Result(db.Model):
    __tablename__ = "result"
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("sample_assignment.id", ondelete="CASCADE"),
        nullable=False,
    )
    ansage_value = db.Column(db.Float, nullable=False)
    ansage_unit = db.Column(db.String(20), nullable=False)
    g_wahr = db.Column(db.Float)
    v_expected_ml = db.Column(db.Float)
    a_min = db.Column(db.Float)
    a_max = db.Column(db.Float)
    titer_expected = db.Column(db.Float)
    titer_result = db.Column(db.Float)
    passed = db.Column(db.Boolean)
    revoked       = db.Column(db.Boolean, nullable=False, default=False)
    revoked_by    = db.Column(db.String(100), nullable=True)
    revoked_date  = db.Column(db.String(20), nullable=True)
    evaluation_label = db.Column(db.String(20), nullable=True)
    submitted_date = db.Column(db.String(20))
    evaluated_by = db.Column(db.String(100))
    notes = db.Column(db.Text)

    assignment = db.relationship("SampleAssignment", back_populates="results")

    def evaluate(self):
        """Bewertet die Ansage mittels modusspezifischer Logik."""
        analysis = self.assignment.sample.batch.analysis
        evaluator = get_evaluator(analysis.calculation_mode)
        evaluation = evaluator.evaluate_result(self)

        self.g_wahr = evaluation.g_wahr
        self.v_expected_ml = evaluation.v_expected_ml
        self.a_min = evaluation.a_min
        self.a_max = evaluation.a_max
        self.titer_expected = evaluation.titer_expected
        self.titer_result = evaluation.titer_result
        self.passed = evaluation.passed
        self.submitted_date = date.today().isoformat()


# ── Praktikumsbetrieb ─────────────────────────────────────────────────────

class PracticalDay(db.Model):
    __tablename__ = "practical_day"
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semester.id"), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    day_type = db.Column(PRACTICAL_DAY_TYPE_ENUM, nullable=False, default="normal")
    block_day_number = db.Column(db.Integer, nullable=True)  # 1–4 for normal days; NULL for Nachkochtag
    notes = db.Column(db.Text)

    semester = db.relationship("Semester", backref="practical_days")
    block = db.relationship("Block", backref="practical_days")
    group_rotations = db.relationship("GroupRotation", back_populates="practical_day",
                                      cascade="all, delete-orphan")
    duty_assignments = db.relationship("DutyAssignment", back_populates="practical_day",
                                       cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("semester_id", "date"),
    )


class GroupRotation(db.Model):
    __tablename__ = "group_rotation"
    id = db.Column(db.Integer, primary_key=True)
    practical_day_id = db.Column(db.Integer, db.ForeignKey("practical_day.id"), nullable=False)
    group_code = db.Column(GROUP_CODE_ENUM, nullable=False)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analysis.id"), nullable=False)
    is_override = db.Column(db.Boolean, nullable=False, default=False)

    practical_day = db.relationship("PracticalDay", back_populates="group_rotations")
    analysis = db.relationship("Analysis")

    __table_args__ = (
        db.UniqueConstraint("practical_day_id", "group_code"),
    )


class DutyAssignment(db.Model):
    __tablename__ = "duty_assignment"
    id = db.Column(db.Integer, primary_key=True)
    practical_day_id = db.Column(db.Integer, db.ForeignKey("practical_day.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    duty_type = db.Column(DUTY_TYPE_ENUM, nullable=False)

    practical_day = db.relationship("PracticalDay", back_populates="duty_assignments")
    student = db.relationship("Student", backref="duty_assignments")


class ProtocolCheck(db.Model):
    __tablename__ = "protocol_check"
    id = db.Column(db.Integer, primary_key=True)
    sample_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("sample_assignment.id"),
        nullable=False,
        unique=True,  # one protocol check per assignment
    )
    checked_date = db.Column(db.String(20), nullable=False)
    checked_by = db.Column(db.String(100), nullable=False)

    assignment = db.relationship("SampleAssignment", backref=db.backref("protocol_check", uselist=False))
