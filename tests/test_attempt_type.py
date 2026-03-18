"""Tests for attempt_type_for() mapping."""
from calculation_modes import attempt_type_for


def test_attempt_1_is_erstanalyse():
    assert attempt_type_for(1) == "Erstanalyse"


def test_attempt_2_is_A():
    assert attempt_type_for(2) == "A"


def test_attempt_3_is_B():
    assert attempt_type_for(3) == "B"


def test_attempt_27_is_Z():
    assert attempt_type_for(27) == "Z"


def test_attempt_28_fallback():
    result = attempt_type_for(28)
    assert result == "#28"


def test_attempt_large_fallback():
    assert attempt_type_for(100) == "#100"
