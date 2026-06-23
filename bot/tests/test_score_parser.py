from bot.model.score import mov_multiplier, parse_games


def test_simple_straight_sets():
    assert parse_games("6-4 6-3") == (12, 7)


def test_tiebreak_parentheses_ignored():
    assert parse_games("7-6(5) 6-7(3) 7-5") == (20, 18)


def test_retirement_counts_played_games():
    assert parse_games("6-2 3-6 6-4 RET") == (15, 12)


def test_walkover_is_none():
    assert parse_games("W/O") is None
    assert parse_games("") is None
    assert parse_games(None) is None


def test_mov_multiplier_range_and_default():
    assert mov_multiplier(None) == 1.0
    m = mov_multiplier("6-0 6-0")        # dominanter Sieg
    n = mov_multiplier("7-6 6-7 7-6")    # knapper Sieg
    assert 0.7 <= n < m <= 1.5
