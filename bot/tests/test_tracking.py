import time

import pytest

from bot import config
from bot.storage import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_state.db")
    db.init_db()
    return config.DB_PATH


def _rec(bet_key="m1:A:SoftBook", commence_ts=None, stake=0.04, odds=2.0):
    return {
        "bet_key": bet_key, "match_id": "m1", "sport_key": "tennis_atp_test",
        "tour": "atp", "selection": "Player A", "opponent": "Player B",
        "commence_time": "2026-06-23T10:00:00Z", "commence_ts": commence_ts,
        "bookmaker": "SoftBook", "odds_taken": odds, "model_prob": 0.6,
        "sharp_prob": 0.58, "final_prob": 0.59, "ev": 0.18, "stake_fraction": stake,
    }


def test_record_is_idempotent(temp_db):
    db.record_recommendation(_rec())
    db.record_recommendation(_rec())  # gleicher bet_key -> kein Duplikat
    assert len(db.recent_recommendations()) == 1


def test_close_flow_and_clv(temp_db):
    now = time.time()
    db.record_recommendation(_rec(commence_ts=now + 600))  # startet in 10 Min
    pending = db.recs_pending_close(now, window_sec=3600)
    assert len(pending) == 1
    rec = pending[0]
    closing_prob = 0.55
    clv = rec["odds_taken"] * closing_prob - 1.0   # 2.0*0.55-1 = 0.10
    db.set_closing(rec["id"], closing_odds=1.85, closing_prob=closing_prob, clv=clv)
    stats = db.tracking_stats()
    assert stats["clv_n"] == 1
    assert abs(stats["clv_avg"] - 0.10) < 1e-9


def test_grade_pnl_win_and_loss(temp_db):
    now = time.time()
    old = now - 10000  # Match lange vorbei
    db.record_recommendation(_rec(bet_key="win", commence_ts=old, stake=0.04, odds=2.0))
    db.record_recommendation(_rec(bet_key="loss", commence_ts=old, stake=0.04, odds=3.0))
    pending = db.recs_pending_grade(now)
    assert len(pending) == 2
    for rec in pending:
        if rec["bet_key"] == "win":
            db.set_result(rec["id"], "win", rec["stake_fraction"] * (rec["odds_taken"] - 1))
        else:
            db.set_result(rec["id"], "loss", -rec["stake_fraction"])
    stats = db.tracking_stats()
    assert stats["graded"] == 2
    assert stats["wins"] == 1
    # pnl = +0.04 (win) - 0.04 (loss) = 0.0 ; staked = 0.08 ; roi = 0.0
    assert abs(stats["pnl_units"]) < 1e-9
    assert abs(stats["roi"]) < 1e-9
