"""Quanti-LIMS ORM models (SQLAlchemy / SQLite)."""

from __future__ import annotations

from datetime import date
from flask_sqlalchemy import SQLAlchemy

from calculation_modes import (
    MODE_ASSAY_MASS_BASED,
    get_evaluator,
    resolve_mode,
)

db = SQLAlchemy()

AMOUNT_UNIT_MASS = "mass"
AMOUNT_UNIT_VOLUME = "volume"
AMOUNT_UNIT_COUNT = "count"

WEIGHING_BASIS_PER_PREPARATION = "per_preparation"
WEIGHING_BASIS_PER_DETERMINATION = "per_determination"
WEIGHING_BASIS_OPTIONS = (
    (WEIGHING_BASIS_PER_PREPARATION, "Einwaage gilt für Gesamtansatz"),
    (WEIGHING_BASIS_PER_DETERMINATION, "Einwaage gilt je Bestimmung"),
)

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

    analyses = db.relationship("Analysis", back_populates="block", order_by="Analysis.ordinal")

    def __repr__(self):
        return f"<Block {self.code}>"


class Substance(db.Model):
    __tablename__ = "substance"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    formula = db.Column(db.String(100))
    molar_mass_gmol = db.Column(db.Float)
    e_ab_g = db.Column(db.Float)
    g_ab_min_pct = db.Column(db.Float)
    g_ab_max_pct = db.Column(db.Float)
    notes = db.Column(db.Text)

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
    blind_required = db.Column(db.Boolean, nullable=False, default=False)
    b_blind_determinations = db.Column(db.Integer, nullable=False, default=1)
    v_vorlage_ml = db.Column(db.Float)
    weighing_basis = db.Column(db.String(30), nullable=False, default=WEIGHING_BASIS_PER_PREPARATION)
    n_aliquots = db.Column(db.Integer)
    description = db.Column(db.Text)

    analysis = db.relationship("Analysis", back_populates="method")
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
    def weighing_basis_label(self) -> str:
        labels = dict(WEIGHING_BASIS_OPTIONS)
        return labels.get(self.weighing_basis or WEIGHING_BASIS_PER_PREPARATION, "Einwaage gilt für Gesamtansatz")


# ── Reagenzien-BOM ────────────────────────────────────────────────────────

class Reagent(db.Model):
    __tablename__ = "reagent"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    abbreviation = db.Column(db.String(50))
    is_composite = db.Column(db.Boolean, nullable=False, default=False)
    base_unit = db.Column(UNIT_ENUM, nullable=False, default="mL")
    cas_number = db.Column(db.String(30))
    density_g_ml = db.Column(db.Float)
    hazard_symbols = db.Column(db.String(100))
    storage_info = db.Column(db.String(200))
    notes = db.Column(db.Text)

    components = db.relationship(
        "ReagentComponent",
        foreign_keys="ReagentComponent.parent_reagent_id",
        back_populates="parent",
    )
    method_usages = db.relationship("MethodReagent", back_populates="reagent")


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


def migrate_schema() -> None:
    """Lightweight schema migration for existing SQLite installations."""
    conn = db.engine.connect()
    try:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(method_reagent)").fetchall()}
        if "amount_per_determination" not in cols:
            conn.exec_driver_sql("ALTER TABLE method_reagent ADD COLUMN amount_per_determination FLOAT")
        if "amount_per_blind" not in cols:
            conn.exec_driver_sql("ALTER TABLE method_reagent ADD COLUMN amount_per_blind FLOAT DEFAULT 0")
        if "amount_unit" not in cols:
            conn.exec_driver_sql("ALTER TABLE method_reagent ADD COLUMN amount_unit VARCHAR(20) DEFAULT 'mL'")

        batch_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sample_batch)").fetchall()}
        if "blend_description" not in batch_cols:
            conn.exec_driver_sql("ALTER TABLE sample_batch ADD COLUMN blend_description VARCHAR(500)")

        method_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(method)").fetchall()}
        if "weighing_basis" not in method_cols:
            conn.exec_driver_sql("ALTER TABLE method ADD COLUMN weighing_basis VARCHAR(30) DEFAULT 'per_preparation'")
        if "n_aliquots" not in method_cols:
            conn.exec_driver_sql("ALTER TABLE method ADD COLUMN n_aliquots INTEGER")

        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(method_reagent)").fetchall()}
        if "volume_per_determination_ml" in cols:
            conn.exec_driver_sql(
                "UPDATE method_reagent SET amount_per_determination = COALESCE(amount_per_determination, volume_per_determination_ml) "
                "WHERE volume_per_determination_ml IS NOT NULL"
            )
        if "volume_per_blind_ml" in cols:
            conn.exec_driver_sql(
                "UPDATE method_reagent SET amount_per_blind = COALESCE(amount_per_blind, volume_per_blind_ml, 0)"
            )
        conn.exec_driver_sql("UPDATE method_reagent SET amount_per_determination = COALESCE(amount_per_determination, 0)")
        conn.exec_driver_sql("UPDATE method_reagent SET amount_per_blind = COALESCE(amount_per_blind, 0)")
        conn.exec_driver_sql("UPDATE method_reagent SET amount_unit = COALESCE(amount_unit, 'mL')")

        conn.exec_driver_sql("UPDATE reagent SET base_unit = 'µL' WHERE lower(base_unit) IN ('ul', 'μl', 'µl')")
        conn.exec_driver_sql("UPDATE reagent SET base_unit = 'mL' WHERE lower(base_unit) = 'ml'")
        conn.exec_driver_sql("UPDATE reagent SET base_unit = 'L' WHERE lower(base_unit) = 'l'")
        conn.exec_driver_sql("UPDATE reagent SET base_unit = 'pcs' WHERE lower(base_unit) IN ('stk', 'piece', 'pieces')")

        conn.exec_driver_sql("UPDATE reagent_component SET quantity_unit = 'µL' WHERE lower(quantity_unit) IN ('ul', 'μl', 'µl')")
        conn.exec_driver_sql("UPDATE reagent_component SET quantity_unit = 'mL' WHERE lower(quantity_unit) = 'ml'")
        conn.exec_driver_sql("UPDATE reagent_component SET quantity_unit = 'L' WHERE lower(quantity_unit) = 'l'")
        conn.exec_driver_sql("UPDATE reagent_component SET quantity_unit = 'pcs' WHERE lower(quantity_unit) IN ('stk', 'piece', 'pieces')")

        conn.exec_driver_sql("UPDATE method_reagent SET amount_unit = 'µL' WHERE lower(amount_unit) IN ('ul', 'μl', 'µl')")
        conn.exec_driver_sql("UPDATE method_reagent SET amount_unit = 'mL' WHERE lower(amount_unit) = 'ml'")
        conn.exec_driver_sql("UPDATE method_reagent SET amount_unit = 'L' WHERE lower(amount_unit) = 'l'")
        conn.exec_driver_sql("UPDATE method_reagent SET amount_unit = 'pcs' WHERE lower(amount_unit) IN ('stk', 'piece', 'pieces')")

        conn.exec_driver_sql("UPDATE method SET weighing_basis = COALESCE(weighing_basis, 'per_preparation')")
        conn.exec_driver_sql(
            "UPDATE method SET weighing_basis = 'per_preparation' "
            "WHERE weighing_basis NOT IN ('per_preparation', 'per_determination')"
        )
        conn.exec_driver_sql("UPDATE method SET n_aliquots = NULL WHERE weighing_basis = 'per_preparation'")
        conn.exec_driver_sql("UPDATE method SET n_aliquots = 1 WHERE weighing_basis = 'per_determination' AND COALESCE(n_aliquots, 0) < 1")

        valid_units_sql = "('mg','g','kg','µL','mL','L','pcs')"
        conn.exec_driver_sql(f"UPDATE reagent SET base_unit = 'mL' WHERE base_unit NOT IN {valid_units_sql}")
        conn.exec_driver_sql(f"UPDATE reagent_component SET quantity_unit = 'mL' WHERE quantity_unit NOT IN {valid_units_sql}")
        conn.exec_driver_sql(f"UPDATE method_reagent SET amount_unit = 'mL' WHERE amount_unit NOT IN {valid_units_sql}")

        conn.exec_driver_sql(
            "UPDATE method_reagent SET is_titrant = 0 "
            "WHERE is_titrant = 1 AND method_id IN ("
            "SELECT method.id FROM method "
            "JOIN analysis ON analysis.id = method.analysis_id "
            "WHERE analysis.calculation_mode = 'titrant_standardization'"
            ")"
        )

        # Legacy cleanup: if no flag exists, infer titrant from method.titrant_name.
        conn.exec_driver_sql(
            "UPDATE method_reagent SET is_titrant = 1 "
            "WHERE id IN ("
            "SELECT mr.id FROM method_reagent mr "
            "JOIN method m ON m.id = mr.method_id "
            "LEFT JOIN (SELECT method_id, SUM(CASE WHEN is_titrant = 1 THEN 1 ELSE 0 END) AS titrant_count "
            "           FROM method_reagent GROUP BY method_id) c ON c.method_id = m.id "
            "WHERE COALESCE(c.titrant_count, 0) = 0 "
            "AND m.titrant_name IS NOT NULL "
            "AND trim(m.titrant_name) <> '' "
            "AND lower(trim(m.titrant_name)) = lower(trim((SELECT r.name FROM reagent r WHERE r.id = mr.reagent_id)))"
            ")"
        )

        # Consistency: keep at most one titrant usage per method.
        conn.exec_driver_sql(
            "UPDATE method_reagent SET is_titrant = 0 "
            "WHERE id IN ("
            "SELECT newer.id FROM method_reagent newer "
            "JOIN method_reagent older "
            "  ON older.method_id = newer.method_id "
            " AND older.is_titrant = 1 "
            " AND newer.is_titrant = 1 "
            " AND older.id < newer.id"
            ")"
        )

        # Keep method.titrant_name aligned as legacy/read model fallback.
        conn.exec_driver_sql(
            "UPDATE method "
            "SET titrant_name = ("
            "  SELECT r.name FROM method_reagent mr "
            "  JOIN reagent r ON r.id = mr.reagent_id "
            "  WHERE mr.method_id = method.id AND mr.is_titrant = 1 "
            "  ORDER BY mr.id LIMIT 1"
            ")"
        )

        indexes = {row[1] for row in conn.exec_driver_sql("PRAGMA index_list(method_reagent)").fetchall()}
        if "uq_method_reagent_single_titrant" not in indexes:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_method_reagent_single_titrant "
                "ON method_reagent(method_id) WHERE is_titrant = 1"
            )
        conn.commit()
    finally:
        conn.close()



# ── Semesterbetrieb ───────────────────────────────────────────────────────

class Semester(db.Model):
    __tablename__ = "semester"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

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
    notes = db.Column(db.Text)

    semester = db.relationship("Semester", back_populates="students")
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


class SampleBatch(db.Model):
    __tablename__ = "sample_batch"
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semester.id"), nullable=False)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analysis.id"), nullable=False)
    substance_lot_id = db.Column(db.Integer, db.ForeignKey("substance_lot.id"))
    blend_description = db.Column(db.String(500))
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
    attempt_type = db.Column(db.String(2), nullable=False, default="A")
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
    )

    @property
    def latest_result(self):
        if self.results:
            return self.results[-1]
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
