"""Tests for compute_evaluation_label()."""
from calculation_modes import compute_evaluation_label


def test_label_correct():
    assert compute_evaluation_label(0.9400, 0.9400, 98.0, 102.0, "Erstanalyse") == "✓"


def test_label_f_up_erstanalyse():
    # 0.9700 is above 0.9588 but within 2×T_max → f↑
    assert compute_evaluation_label(0.9700, 0.9400, 98.0, 102.0, "Erstanalyse") == "f↑ → A"


def test_label_f_up_a_analyse():
    assert compute_evaluation_label(0.9700, 0.9400, 98.0, 102.0, "A") == "f↑ → B"


def test_label_f_down():
    # δ = (0.9100 - 0.9400)/0.9400 * 100 = -3.19%
    # T_min = 100 - 98 = 2; -2*T_min=-4 ≤ δ=-3.19 < -T_min=-2 → f↓
    assert compute_evaluation_label(0.9100, 0.9400, 98.0, 102.0, "Erstanalyse") == "f↓ → A"


def test_label_f_up_up_up():
    # very far above: δ >> 4*T_max
    assert compute_evaluation_label(1.100, 0.9400, 98.0, 102.0, "Erstanalyse") == "f↑↑↑ → A"


def test_label_none_when_tol_missing():
    assert compute_evaluation_label(0.9400, 0.9400, None, None, "Erstanalyse") is None


def test_label_none_when_true_value_zero():
    assert compute_evaluation_label(1.0, 0.0, 98.0, 102.0, "Erstanalyse") is None
