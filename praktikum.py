"""Praktikum service module — resolution logic for the Tagesansicht."""
from __future__ import annotations
from dataclasses import dataclass, field

from models import (
    Analysis, SampleAssignment, SampleBatch, Sample,
    Student, GroupRotation,
)


GROUP_CODES = ["A", "B", "C", "D"]
# Constrained by GROUP_CODE_ENUM in models.py — max 4 groups.


def suggest_rotation(block, block_day_number, active_group_count: int) -> dict:
    """Return {group_code: Analysis} cyclic suggestion for a normal practical day.

    Group at position i → analysis at index (i + block_day_number - 1) % len(analyses).
    Returns {} when block has no analyses or block_day_number is None (Nachkochtag).
    """
    analyses = sorted(block.analyses, key=lambda a: a.ordinal)
    if not analyses or block_day_number is None:
        return {}
    groups = GROUP_CODES[:active_group_count]
    return {
        group: analyses[(i + block_day_number - 1) % len(analyses)]
        for i, group in enumerate(groups)
    }


def _load_protocol_missing(semester_id: int, block_id: int | None = None) -> dict:
    """Return {student_id: [SampleAssignment]} for passed assignments missing a ProtocolCheck.

    block_id: if given, restrict to analyses in that block (used for Nachkochtag).
    Uses selectinload to avoid N+1 on protocol_check.
    """
    from sqlalchemy.orm import selectinload
    q = (
        SampleAssignment.query
        .options(selectinload(SampleAssignment.protocol_check))
        .join(Sample)
        .join(SampleBatch)
        .filter(
            SampleBatch.semester_id == semester_id,
            SampleAssignment.status == "passed",
        )
    )
    if block_id is not None:
        q = q.join(Analysis, SampleBatch.analysis_id == Analysis.id).filter(
            Analysis.block_id == block_id
        )
    result: dict[int, list] = {}
    for sa in q.all():
        if sa.protocol_check is None:
            result.setdefault(sa.student_id, []).append(sa)
    return result


@dataclass
class StudentSlot:
    student: Student
    rotation_analysis: Analysis | None
    rotation_assignment: SampleAssignment | None
    extra_assignments: list[SampleAssignment] = field(default_factory=list)
    protocol_missing_assignments: list[SampleAssignment] = field(default_factory=list)


def resolve_student_slots(practical_day, semester) -> list[StudentSlot]:
    """Return one StudentSlot per student in semester for the given practical_day."""
    students = (
        Student.query
        .filter_by(semester_id=semester.id)
        .order_by(Student.running_number)
        .all()
    )
    if practical_day.day_type == "nachkochtag":
        return _resolve_nachkochtag(practical_day, semester, students)
    return _resolve_normal_day(practical_day, semester, students)


def _resolve_normal_day(practical_day, semester, students) -> list[StudentSlot]:
    # Step 1: GroupRotations for this day keyed by group_code
    rotations: dict[str, GroupRotation] = {
        gr.group_code: gr
        for gr in practical_day.group_rotations
    }

    # Step 2: All open SampleAssignments for this semester, grouped by student_id
    open_assignments: list[SampleAssignment] = (
        SampleAssignment.query
        .join(Sample)
        .join(SampleBatch)
        .filter(
            SampleBatch.semester_id == semester.id,
            SampleAssignment.status.notin_(["passed", "cancelled"]),
        )
        .all()
    )
    by_student: dict[int, list[SampleAssignment]] = {}
    for sa in open_assignments:
        by_student.setdefault(sa.student_id, []).append(sa)

    # Step 3: Pre-load SampleBatch and Sample lookups to avoid N+1
    batches_by_analysis: dict[int, SampleBatch] = {
        sb.analysis_id: sb
        for sb in SampleBatch.query.filter_by(semester_id=semester.id).all()
    }
    all_batch_ids = [sb.id for sb in batches_by_analysis.values()]
    samples_by_key: dict[tuple[int, int], Sample] = {}
    if all_batch_ids:
        for s in Sample.query.filter(
            Sample.batch_id.in_(all_batch_ids),
            Sample.is_buffer.is_(False),
        ).all():
            samples_by_key[(s.batch_id, s.running_number)] = s

    # Protocol-missing (full semester scope for normal days)
    protocol_missing = _load_protocol_missing(semester.id)

    # Step 4: Build one slot per student
    slots: list[StudentSlot] = []
    for student in students:
        rotation = rotations.get(student.group_code) if student.group_code else None
        rotation_analysis = rotation.analysis if rotation else None
        rotation_assignment: SampleAssignment | None = None

        if rotation_analysis:
            batch = batches_by_analysis.get(rotation_analysis.id)
            if batch:
                sample = samples_by_key.get((batch.id, student.running_number))
                if sample:
                    rotation_assignment = next(
                        (sa for sa in by_student.get(student.id, [])
                         if sa.sample_id == sample.id),
                        None,
                    )

        # extra_assignments: all open assignments EXCEPT the rotation one
        rot_id = rotation_assignment.id if rotation_assignment else None
        extra = [
            sa for sa in by_student.get(student.id, [])
            if sa.id != rot_id
        ]

        slots.append(StudentSlot(
            student=student,
            rotation_analysis=rotation_analysis,
            rotation_assignment=rotation_assignment,
            extra_assignments=extra,
            protocol_missing_assignments=protocol_missing.get(student.id, []),
        ))

    return slots


def _resolve_nachkochtag(practical_day, semester, students) -> list[StudentSlot]:
    block_id = practical_day.block_id

    # All open assignments for this block
    open_assignments: list[SampleAssignment] = (
        SampleAssignment.query
        .join(Sample)
        .join(SampleBatch)
        .join(Analysis, SampleBatch.analysis_id == Analysis.id)
        .filter(
            SampleBatch.semester_id == semester.id,
            Analysis.block_id == block_id,
            SampleAssignment.status.notin_(["passed", "cancelled"]),
        )
        .all()
    )
    by_student: dict[int, list[SampleAssignment]] = {}
    for sa in open_assignments:
        by_student.setdefault(sa.student_id, []).append(sa)

    protocol_missing = _load_protocol_missing(semester.id, block_id=block_id)

    # All students appear; empty extra_assignments = block completed
    return [
        StudentSlot(
            student=student,
            rotation_analysis=None,
            rotation_assignment=None,
            extra_assignments=by_student.get(student.id, []),
            protocol_missing_assignments=protocol_missing.get(student.id, []),
        )
        for student in students
    ]
