from bot import config
from bot.odds.odds_api import BookOdds, Match
from bot.value import engine


def test_kelly_scales_with_fraction():
    # volles Kelly fuer p=0.6, odds=2.0 ist 0.2
    assert abs(engine.kelly(0.6, 2.0) - 0.2 * config.KELLY_FRACTION) < 1e-9


def test_kelly_no_edge_zero():
    assert engine.kelly(0.4, 2.0) == 0.0


def test_stake_fraction_respects_cap():
    assert engine.stake_fraction(0.99, 10.0) <= config.MAX_STAKE_FRACTION + 1e-9


def test_stake_eur_uses_bankroll(monkeypatch):
    monkeypatch.setattr(config, "BANKROLL", 1000.0)
    bet = engine.ValueBet(
        match=Match("m", "tennis_atp_test", "atp", "", "A", "B",
                    [BookOdds("softbook", "S", {"A": 2.0})]),
        selection="A", raw_model_prob=0.6, model_prob=0.6, sharp_prob=None,
        best_odds=2.0, best_book="S", n_books=2, ev=0.2, stake_fraction=0.03,
    )
    assert abs(bet.stake_eur - 30.0) < 1e-9


def test_stake_eur_none_without_bankroll(monkeypatch):
    monkeypatch.setattr(config, "BANKROLL", 0.0)
    bet = engine.ValueBet(
        match=Match("m", "tennis_atp_test", "atp", "", "A", "B", []),
        selection="A", raw_model_prob=0.6, model_prob=0.6, sharp_prob=None,
        best_odds=2.0, best_book="S", n_books=2, ev=0.2, stake_fraction=0.03,
    )
    assert bet.stake_eur is None
