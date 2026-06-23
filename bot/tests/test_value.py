from bot import config
from bot.odds.odds_api import BookOdds, Match
from bot.value import engine


def test_implied_prob():
    assert abs(engine.implied_prob(2.0) - 0.5) < 1e-9
    assert abs(engine.implied_prob(4.0) - 0.25) < 1e-9


def test_devig_two_way_normalizes():
    pa, pb = engine.devig_two_way(2.0, 2.0)
    assert abs(pa - 0.5) < 1e-9 and abs(pb - 0.5) < 1e-9
    pa, pb = engine.devig_two_way(1.5, 2.6)
    assert abs((pa + pb) - 1.0) < 1e-9
    assert pa > pb  # kuerzere Quote = hoehere Wahrscheinlichkeit


def test_kelly_known_value():
    # p=0.6, odds=2.0 -> volles Kelly 0.2, mal Fraktion (Default 0.25) = 0.05
    assert abs(engine.kelly(0.6, 2.0) - 0.2 * config.KELLY_FRACTION) < 1e-9


def test_kelly_no_edge_is_zero():
    assert engine.kelly(0.4, 2.0) == 0.0


def _match():
    return Match(
        id="m1", sport_key="tennis_atp_test", tour="atp",
        commence_time="2026-06-23T10:00:00Z", home="Player A", away="Player B",
        books=[
            BookOdds("pinnacle", "Pinnacle", {"Player A": 1.5, "Player B": 2.6}),
            BookOdds("softbook", "SoftBook", {"Player A": 1.8, "Player B": 2.1}),
            BookOdds("softbook2", "SoftBook2", {"Player A": 1.75, "Player B": 2.05}),
        ],
    )


def test_evaluate_flags_value_on_soft_book():
    bets = engine.evaluate(_match(), 0.65)
    assert len(bets) == 1
    bet = bets[0]
    assert bet.selection == "Player A"
    assert bet.best_book == "SoftBook"     # nicht der scharfe Buchmacher
    assert bet.best_odds == 1.8
    assert bet.n_books == 2                 # MIN_BOOKS erfuellt
    assert bet.ev > config.MIN_EV
    assert bet.stake_fraction > 0
    assert bet.sharp_prob is not None      # Sharp-Anker aus Pinnacle vorhanden


def test_evaluate_rejects_when_no_edge():
    # Modell nahe am Markt -> kein ausreichender +EV gegen die weichen Quoten.
    assert engine.evaluate(_match(), 0.52) == []


def test_min_books_filter_rejects_single_soft_book():
    m = Match(
        id="m2", sport_key="tennis_atp_test", tour="atp",
        commence_time="2026-06-23T10:00:00Z", home="Player A", away="Player B",
        books=[
            BookOdds("pinnacle", "Pinnacle", {"Player A": 1.5, "Player B": 2.6}),
            BookOdds("softbook", "SoftBook", {"Player A": 1.8, "Player B": 2.1}),
        ],
    )
    # Nur 1 weicher Buchmacher -> unter MIN_BOOKS (2) -> kein Bet.
    assert engine.evaluate(m, 0.65) == []


def test_stake_is_capped():
    f = engine.stake_fraction(0.99, 5.0)   # riesiger Edge
    assert f <= config.MAX_STAKE_FRACTION + 1e-9


def test_blend_with_market():
    assert engine.blend_with_market(0.7, None) == 0.7   # ohne Sharp -> Modell
    blended = engine.blend_with_market(0.7, 0.5)
    assert 0.5 <= blended <= 0.7
