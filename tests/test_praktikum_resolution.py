"""Tests for praktikum.resolve_student_slots() — no HTTP layer."""
import pytest
from models import (
    db as _db, Semester, Block, Analysis, SampleBatch, Sample,
    SampleAssignment, Student, PracticalDay, GroupRotation,
    Substance,
)


# ─── fixture ────────────────────────────────────────────────────────────────

@pytest.fixture()
def fx(db):
    """Build a minimal but complete practical-day dataset."""
    # Semester
    sem = Semester(code="WS9999", name="Test-Semester", is_active=True)
    db.session.add(sem)
    db.session.flush()

    # Block
    block = Block(code="TBLK", name="Test Block I")
    db.session.add(block)
    db.session.flush()

    # A minimal Substance (required FK for Analysis)
    sub = Substance(name="TestSubstanz_fx", formula="X", molar_mass_gmol=100.0)
    db.session.add(sub)
    db.session.flush()

    # Two analyses in this block.
    # Note: Analysis requires code (unique), ordinal, and substance_id (FK) — the
    # plan's fixture stub omitted these; they were added to match the real schema.
    a1 = Analysis(name="Analyse 1", block_id=block.id, code="TX.1", ordinal=1,
                  substance_id=sub.id, calculation_mode="assay_mass_based")
    a2 = Analysis(name="Analyse 2", block_id=block.id, code="TX.2", ordinal=2,
                  substance_id=sub.id, calculation_mode="assay_mass_based")
    db.session.add_all([a1, a2])
    db.session.flush()

    # One SampleBatch per analysis
    b1 = SampleBatch(semester_id=sem.id, analysis_id=a1.id,
                     total_samples_prepared=4)
    b2 = SampleBatch(semester_id=sem.id, analysis_id=a2.id,
                     total_samples_prepared=4)
    db.session.add_all([b1, b2])
    db.session.flush()

    # 4 regular samples per batch (running_number 1-4, not buffer)
    # + 1 buffer sample per batch (running_number 99) — ensures is_buffer filter is tested
    samples_b1, samples_b2 = [], []
    for n in range(1, 5):
        s1 = Sample(batch_id=b1.id, running_number=n, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
        s2 = Sample(batch_id=b2.id, running_number=n, is_buffer=False,
                    m_s_actual_g=0.1, m_ges_actual_g=0.5)
        samples_b1.append(s1)
        samples_b2.append(s2)
    buf1 = Sample(batch_id=b1.id, running_number=99, is_buffer=True)
    buf2 = Sample(batch_id=b2.id, running_number=99, is_buffer=True)
    db.session.add_all(samples_b1 + samples_b2 + [buf1, buf2])
    db.session.flush()

    # 4 students with group_codes A/B/C/D (running_numbers 1-4)
    # + 1 student with group_code=None (running_number 5) for edge-case test
    codes = ["A", "B", "C", "D"]
    students = []
    for i, code in enumerate(codes, start=1):
        st = Student(semester_id=sem.id, matrikel=f"99{i:04d}",
                     last_name=f"Student{i}", first_name="Test",
                     running_number=i, group_code=code)
        students.append(st)
    st_no_group = Student(semester_id=sem.id, matrikel="990005",
                          last_name="NoGroup", first_name="Test",
                          running_number=5, group_code=None)
    students.append(st_no_group)
    db.session.add_all(students)
    db.session.flush()

    # Normal PracticalDay: group A → a1, group B → a2
    normal_day = PracticalDay(semester_id=sem.id, block_id=block.id,
                              date="2099-10-06", day_type="normal",
                              block_day_number=1)
    db.session.add(normal_day)
    db.session.flush()

    gr_a = GroupRotation(practical_day_id=normal_day.id, group_code="A",
                         analysis_id=a1.id, is_override=False)
    gr_b = GroupRotation(practical_day_id=normal_day.id, group_code="B",
                         analysis_id=a2.id, is_override=False)
    db.session.add_all([gr_a, gr_b])
    db.session.flush()

    # Nachkochtag PracticalDay (same block)
    nach_day = PracticalDay(semester_id=sem.id, block_id=block.id,
                            date="2099-10-11", day_type="nachkochtag",
                            block_day_number=None)
    db.session.add(nach_day)
    db.session.flush()

    return {
        "sem": sem, "block": block,
        "sub": sub,
        "a1": a1, "a2": a2,
        "b1": b1, "b2": b2,
        "samples_b1": samples_b1,   # index 0 = running_number 1
        "samples_b2": samples_b2,
        "students": students,        # indices 0-3 = groups A/B/C/D; index 4 = no group_code
        "st_no_group": st_no_group,
        "normal_day": normal_day,
        "nach_day": nach_day,
    }


# ─── normaltag tests ─────────────────────────────────────────────────────────

def test_normal_day_student_with_assignment(db, fx):
    """Student A (running_number=1) has an assignment for analysis 1 sample 1."""
    from praktikum import resolve_student_slots
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,   # sample running_number=1
        student_id=fx["students"][0].id,     # student A, running_number=1
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])

    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_analysis.id == fx["a1"].id
    assert slot_a.rotation_assignment is not None
    assert slot_a.rotation_assignment.id == sa.id
    assert slot_a.extra_assignments == []


def test_normal_day_no_assignment_yet(db, fx):
    """Student A has no assignment yet (assign_initial not run)."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])

    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_analysis.id == fx["a1"].id
    assert slot_a.rotation_assignment is None
    assert slot_a.extra_assignments == []


def test_normal_day_no_group_code(db, fx):
    """Student with no group_code → rotation_analysis and rotation_assignment are None.
    Uses the pre-built st_no_group student from the fixture (running_number=5)."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])

    slot = next(s for s in slots if s.student.id == fx["st_no_group"].id)
    assert slot.rotation_analysis is None
    assert slot.rotation_assignment is None


def test_normal_day_extra_assignment_not_duplicated(db, fx):
    """rotation_assignment must NOT appear in extra_assignments, while another
    open assignment IS included. Fixture state: student A has both a rotation
    assignment (b1, sample 1) AND an open extra assignment (b2, sample 1).
    Only the extra should appear in extra_assignments."""
    from praktikum import resolve_student_slots
    sa_rot = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,   # rotation sample
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    sa_other = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,   # different analysis/sample
        student_id=fx["students"][0].id,
        attempt_number=2, attempt_type="A",
        assigned_date="2099-10-05", status="assigned",
    )
    db.session.add_all([sa_rot, sa_other])
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")

    extra_ids = [e.id for e in slot_a.extra_assignments]
    assert sa_rot.id not in extra_ids   # rotation must be excluded
    assert sa_other.id in extra_ids     # other open assignment must be included


def test_normal_day_extra_assignment_retry(db, fx):
    """Student A has a rotation assignment + a pending retry from another analysis."""
    from praktikum import resolve_student_slots

    # rotation assignment for a1
    sa_rot = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    # open retry assignment for a2
    sa_extra = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=2, attempt_type="A",
        assigned_date="2099-10-05", status="assigned",
    )
    db.session.add_all([sa_rot, sa_extra])
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")

    assert slot_a.rotation_assignment.id == sa_rot.id
    assert len(slot_a.extra_assignments) == 1
    assert slot_a.extra_assignments[0].id == sa_extra.id


def test_normal_day_all_students_appear(db, fx):
    """All semester students appear in the output, even those with no assignment."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    assert len(slots) == len(fx["students"])


def test_normal_day_no_batch_for_analysis(db, fx):
    """If no SampleBatch exists for the rotation analysis, rotation_assignment is None
    (graceful fallback, no KeyError)."""
    from praktikum import resolve_student_slots
    from models import Analysis, GroupRotation, PracticalDay
    # Create a new analysis with no batch
    orphan_analysis = Analysis(name="Orphan", block_id=fx["block"].id,
                               code="TX.99", ordinal=99,
                               substance_id=fx["sub"].id,
                               calculation_mode="assay_mass_based")
    db.session.add(orphan_analysis)
    db.session.flush()
    orphan_day = PracticalDay(semester_id=fx["sem"].id, block_id=fx["block"].id,
                              date="2099-10-08", day_type="normal", block_day_number=3)
    db.session.add(orphan_day)
    db.session.flush()
    gr = GroupRotation(practical_day_id=orphan_day.id, group_code="A",
                       analysis_id=orphan_analysis.id, is_override=False)
    db.session.add(gr)
    db.session.flush()

    slots = resolve_student_slots(orphan_day, fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_analysis.id == orphan_analysis.id
    assert slot_a.rotation_assignment is None  # no batch → no assignment


def test_normal_day_no_sample_for_running_number(db, fx):
    """If the batch exists but has no sample matching student.running_number,
    rotation_assignment is None (graceful fallback, no KeyError)."""
    from praktikum import resolve_student_slots
    from models import Analysis, SampleBatch, GroupRotation, PracticalDay
    # Analysis + batch exist, but batch has no samples
    sparse_analysis = Analysis(name="Sparse", block_id=fx["block"].id,
                               code="TX.98", ordinal=98,
                               substance_id=fx["sub"].id,
                               calculation_mode="assay_mass_based")
    db.session.add(sparse_analysis)
    db.session.flush()
    sparse_batch = SampleBatch(semester_id=fx["sem"].id,
                               analysis_id=sparse_analysis.id,
                               total_samples_prepared=0)
    db.session.add(sparse_batch)
    db.session.flush()
    sparse_day = PracticalDay(semester_id=fx["sem"].id, block_id=fx["block"].id,
                              date="2099-10-09", day_type="normal", block_day_number=4)
    db.session.add(sparse_day)
    db.session.flush()
    gr = GroupRotation(practical_day_id=sparse_day.id, group_code="A",
                       analysis_id=sparse_analysis.id, is_override=False)
    db.session.add(gr)
    db.session.flush()

    slots = resolve_student_slots(sparse_day, fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.rotation_assignment is None  # no sample → no assignment


def test_normal_day_passed_assignment_not_in_extra(db, fx):
    """Passed assignments are not included in extra_assignments."""
    from praktikum import resolve_student_slots
    sa_passed = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-01", status="passed",
    )
    db.session.add(sa_passed)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.extra_assignments == []


# ─── nachkochtag tests ───────────────────────────────────────────────────────

def test_nachkochtag_student_with_open_assignment(db, fx):
    """Student with open block assignment appears with it in extra_assignments."""
    from praktikum import resolve_student_slots
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    slot = next(s for s in slots if s.student.id == fx["students"][0].id)

    assert slot.rotation_analysis is None
    assert slot.rotation_assignment is None
    assert len(slot.extra_assignments) == 1
    assert slot.extra_assignments[0].id == sa.id


def test_nachkochtag_student_without_open_assignment_still_appears(db, fx):
    """Student with no open block assignments appears with empty extra_assignments."""
    from praktikum import resolve_student_slots

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    assert len(slots) == len(fx["students"])

    slot = next(s for s in slots if s.student.id == fx["students"][0].id)
    assert slot.extra_assignments == []


def test_nachkochtag_multiple_open_assignments(db, fx):
    """Student with 2 open block assignments gets both in extra_assignments."""
    from praktikum import resolve_student_slots
    sa1 = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    sa2 = SampleAssignment(
        sample_id=fx["samples_b2"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-07", status="assigned",
    )
    db.session.add_all([sa1, sa2])
    db.session.flush()

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    slot = next(s for s in slots if s.student.id == fx["students"][0].id)
    assert len(slot.extra_assignments) == 2


# ─── suggest_rotation tests ──────────────────────────────────────────────────

def test_suggest_rotation_day1(db, fx):
    """Day 1: group A → first analysis, B → second."""
    from praktikum import suggest_rotation
    result = suggest_rotation(fx["block"], block_day_number=1, active_group_count=2)
    assert result["A"].id == fx["a1"].id
    assert result["B"].id == fx["a2"].id

def test_suggest_rotation_day2_wraps(db, fx):
    """Day 2: shifts by one, wraps around."""
    from praktikum import suggest_rotation
    result = suggest_rotation(fx["block"], block_day_number=2, active_group_count=2)
    assert result["A"].id == fx["a2"].id
    assert result["B"].id == fx["a1"].id

def test_suggest_rotation_more_groups_than_analyses(db, fx):
    """4 groups, 2 analyses — wraps modulo len(analyses)."""
    from praktikum import suggest_rotation
    result = suggest_rotation(fx["block"], block_day_number=1, active_group_count=4)
    assert len(result) == 4
    assert result["A"].id == fx["a1"].id
    assert result["C"].id == fx["a1"].id  # wraps back

def test_suggest_rotation_empty_block(db, fx):
    """Block with no analyses → empty dict."""
    from praktikum import suggest_rotation
    from models import Block
    empty_block = Block(code="EMPTY", name="Empty")
    db.session.add(empty_block)
    db.session.flush()
    assert suggest_rotation(empty_block, block_day_number=1, active_group_count=2) == {}

def test_suggest_rotation_null_day_number(db, fx):
    """Nachkochtag has block_day_number=None → empty dict."""
    from praktikum import suggest_rotation
    assert suggest_rotation(fx["block"], block_day_number=None, active_group_count=2) == {}


# ─── protocol_missing_assignments tests ──────────────────────────────────────

def test_protocol_missing_passed_no_check(db, fx):
    """Passed assignment without ProtocolCheck → in protocol_missing_assignments."""
    from praktikum import resolve_student_slots
    from models import ProtocolCheck
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,  # group A, running_number=1
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="passed",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert len(slot_a.protocol_missing_assignments) == 1
    assert slot_a.protocol_missing_assignments[0].id == sa.id


def test_protocol_missing_passed_with_check(db, fx):
    """Passed assignment WITH ProtocolCheck → NOT in protocol_missing_assignments."""
    from praktikum import resolve_student_slots
    from models import ProtocolCheck
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="passed",
    )
    db.session.add(sa)
    db.session.flush()
    pc = ProtocolCheck(sample_assignment_id=sa.id,
                       checked_date="2099-10-07", checked_by="TA")
    db.session.add(pc)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.protocol_missing_assignments == []


def test_protocol_missing_assigned_status_excluded(db, fx):
    """Open (assigned) assignment → NOT in protocol_missing_assignments."""
    from praktikum import resolve_student_slots
    sa = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="assigned",
    )
    db.session.add(sa)
    db.session.flush()

    slots = resolve_student_slots(fx["normal_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert slot_a.protocol_missing_assignments == []


def test_protocol_missing_nachkochtag_block_scoped(db, fx):
    """Nachkochtag: protocol_missing_assignments scoped to current block only."""
    from praktikum import resolve_student_slots
    # passed assignment in same block → included
    sa1 = SampleAssignment(
        sample_id=fx["samples_b1"][0].id,
        student_id=fx["students"][0].id,
        attempt_number=1, attempt_type="Erstanalyse",
        assigned_date="2099-10-06", status="passed",
    )
    db.session.add(sa1)
    db.session.flush()

    slots = resolve_student_slots(fx["nach_day"], fx["sem"])
    slot_a = next(s for s in slots if s.student.group_code == "A")
    assert len(slot_a.protocol_missing_assignments) == 1
