"""Tests for auto group assignment algorithm."""
import pytest
from models import GROUP_CODES


def _make_students(names):
    """Create mock students with last_name and group_code=None."""
    from unittest.mock import MagicMock
    students = []
    for name in names:
        s = MagicMock()
        s.last_name = name
        s.group_code = None
        students.append(s)
    return students


def _auto_assign(students, active_group_count=4):
    """Mirror of the algorithm to be implemented."""
    groups = GROUP_CODES[:active_group_count]
    unassigned = [s for s in students if s.group_code is None]
    unassigned.sort(key=lambda s: s.last_name.lower())
    assignments = {}
    for i, student in enumerate(unassigned):
        assignments[id(student)] = groups[i % len(groups)]
    return assignments


def test_round_robin_distribution():
    students = _make_students(["Ziegler", "Bauer", "Meyer", "Fischer"])
    result = _auto_assign(students)
    # Sorted: Bauer, Fischer, Meyer, Ziegler → A, B, C, D
    by_name = {s.last_name: result[id(s)] for s in students}
    assert by_name["Bauer"] == "A"
    assert by_name["Fischer"] == "B"
    assert by_name["Meyer"] == "C"
    assert by_name["Ziegler"] == "D"


def test_already_assigned_skipped():
    from unittest.mock import MagicMock
    s1 = MagicMock(); s1.last_name = "Bauer"; s1.group_code = "A"  # already assigned
    s2 = MagicMock(); s2.last_name = "Fischer"; s2.group_code = None
    result = _auto_assign([s1, s2])
    assert id(s1) not in result  # s1 skipped
    assert result[id(s2)] == "A"  # only s2 assigned, gets first group


def test_active_group_count_respected():
    students = _make_students(["A", "B", "C", "D", "E"])
    result = _auto_assign(students, active_group_count=3)
    groups_used = set(result.values())
    assert groups_used == {"A", "B", "C"}
