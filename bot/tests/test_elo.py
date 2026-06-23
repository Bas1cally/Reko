from bot.model import elo


def test_expected_score_symmetry():
    p_ab = elo.expected_score(1600, 1500)
    p_ba = elo.expected_score(1500, 1600)
    assert abs((p_ab + p_ba) - 1.0) < 1e-9


def test_equal_ratings_is_coinflip():
    assert abs(elo.expected_score(1500, 1500) - 0.5) < 1e-9


def test_higher_rating_favored():
    assert elo.expected_score(1800, 1500) > 0.5
    assert elo.expected_score(1200, 1500) < 0.5


def test_k_factor_decreases_with_experience():
    assert elo.k_factor(0) > elo.k_factor(50) > elo.k_factor(500)


def test_blended_probability_bounds_and_symmetry():
    p = elo.blended_win_probability(1700, 1750, 1500, 1480)
    assert 0.0 < p < 1.0
    q = elo.blended_win_probability(1500, 1480, 1700, 1750)
    assert abs((p + q) - 1.0) < 1e-9


def test_update_moves_toward_outcome():
    expected = elo.expected_score(1500, 1500)
    new = elo.update(1500, 1.0, expected, elo.k_factor(10))
    assert new > 1500  # Sieg gegen Gleichstarken -> Rating steigt
