from bot.value import engine


def test_power_symmetric_is_coinflip():
    pa, pb = engine.devig_two_way(2.0, 2.0, method="power")
    assert abs(pa - 0.5) < 1e-6 and abs(pb - 0.5) < 1e-6


def test_power_sums_to_one():
    pa, pb = engine.devig_two_way(1.3, 4.0, method="power")
    assert abs((pa + pb) - 1.0) < 1e-9
    assert 0 < pb < pa < 1          # Favorit (kuerzere Quote) hat hoehere Prob


def test_multiplicative_sums_to_one():
    pa, pb = engine.devig_two_way(1.3, 4.0, method="multiplicative")
    assert abs((pa + pb) - 1.0) < 1e-9


def test_methods_differ_for_asymmetric_market():
    pa_pow, _ = engine.devig_two_way(1.3, 4.0, method="power")
    pa_mul, _ = engine.devig_two_way(1.3, 4.0, method="multiplicative")
    assert abs(pa_pow - pa_mul) > 1e-4   # Power korrigiert den Bias anders
