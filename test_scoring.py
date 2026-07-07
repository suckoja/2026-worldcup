from scoring import score_prediction

RULES = {
    "32":    {"exact": 2, "correct": 1, "wrong": 0, "double_cap": 0},
    "16":    {"exact": 4, "correct": 2, "wrong": 0, "double_cap": 2},
    "8":     {"exact": 6, "correct": 3, "wrong": 0, "double_cap": 1},
    "4":     {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 1},
    "final": {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 0},
}


def test_exact_score_round32():
    assert score_prediction((1, 0), (1, 0), "32", RULES) == 2


def test_correct_result_round32():
    assert score_prediction((2, 0), (1, 0), "32", RULES) == 1


def test_wrong_result_round32():
    assert score_prediction((0, 1), (1, 0), "32", RULES) == 0


def test_exact_draw():
    assert score_prediction((1, 1), (1, 1), "32", RULES) == 2


def test_correct_draw_different_score():
    assert score_prediction((0, 0), (2, 2), "32", RULES) == 1


def test_wrong_predicted_draw_actual_win():
    assert score_prediction((1, 1), (2, 1), "32", RULES) == 0


def test_exact_score_round16():
    assert score_prediction((2, 1), (2, 1), "16", RULES) == 4


def test_correct_result_round16():
    assert score_prediction((3, 1), (2, 1), "16", RULES) == 2


def test_exact_score_round8():
    assert score_prediction((1, 0), (1, 0), "8", RULES) == 6


def test_exact_score_round4():
    assert score_prediction((1, 0), (1, 0), "4", RULES) == 8


def test_doubled_exact_score():
    assert score_prediction((2, 1), (2, 1), "16", RULES, doubled=True) == 8


def test_doubled_correct_result_only():
    assert score_prediction((3, 1), (2, 1), "16", RULES, doubled=True) == 4


def test_doubled_wrong_is_minus_two_not_zero():
    assert score_prediction((0, 1), (1, 0), "16", RULES, doubled=True) == -2


def test_not_doubled_defaults_unchanged():
    assert score_prediction((2, 1), (2, 1), "16", RULES) == 4
