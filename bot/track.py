"""Feedback-Loop: Closing-Line erfassen, Ergebnisse werten, CLV/ROI berichten.

Aufruf (per Cron, siehe deploy/crontab.example):
    python -m bot.track close    # scharfe Closing-Quote fuer naheliegende Matches
    python -m bot.track grade    # Ergebnisse holen + P&L berechnen
    python -m bot.track report   # CLV / ROI / P&L ausgeben (+ optional Telegram)
"""
from __future__ import annotations

import argparse
import sys
import time

from . import config
from .logging_setup import get_logger
from .matching.names import normalize_key
from .notify import telegram
from .odds import odds_api
from .storage import db
from .value import engine

log = get_logger(__name__)


def close() -> int:
    """Erfasst die (nahezu) Closing-Quote des scharfen Buchmachers + CLV."""
    now = time.time()
    pending = db.recs_pending_close(now, config.CLOSE_WINDOW_MIN * 60)
    if not pending:
        log.info("close: keine offenen Empfehlungen im Fenster.")
        return 0

    by_id = {m.id: m for m in odds_api.fetch_all_matches()}
    updated = 0
    for rec in pending:
        match = by_id.get(rec["match_id"])
        if match is None:
            continue  # Match evtl. schon gestartet/aus dem Feed -> spaeter erneut
        closing_prob = engine.sharp_consensus(match, rec["selection"])
        if closing_prob is None:
            continue
        closing_odds = _sharp_odds(match, rec["selection"])
        clv = rec["odds_taken"] * closing_prob - 1.0  # >0 = Closing geschlagen
        db.set_closing(rec["id"], closing_odds, closing_prob, clv)
        updated += 1
    log.info("close: %d Empfehlung(en) mit Closing/CLV aktualisiert.", updated)
    return 0


def _sharp_odds(match, selection: str):
    for book in match.books:
        if book.key in config.SHARP_BOOKMAKERS and selection in book.prices:
            return book.prices[selection]
    return None


def grade() -> int:
    """Wertet abgeschlossene Matches aus und berechnet P&L in Units."""
    now = time.time()
    pending = db.recs_pending_grade(now)
    if not pending:
        log.info("grade: keine faelligen Empfehlungen.")
        return 0

    scores = {s["id"]: s for s in odds_api.fetch_all_scores(days_from=3)}
    graded = 0
    for rec in pending:
        ev = scores.get(rec["match_id"])
        if ev is None or not ev["completed"] or not ev["scores"]:
            continue
        winner = max(ev["scores"], key=ev["scores"].get)
        # Tie / unklar -> void
        vals = sorted(ev["scores"].values(), reverse=True)
        if len(vals) >= 2 and vals[0] == vals[1]:
            db.set_result(rec["id"], "void", 0.0)
            graded += 1
            continue
        won = normalize_key(winner) == normalize_key(rec["selection"])
        stake = rec["stake_fraction"] or 0.0
        if won:
            pnl = stake * (rec["odds_taken"] - 1.0)
            db.set_result(rec["id"], "win", pnl)
        else:
            db.set_result(rec["id"], "loss", -stake)
        graded += 1
    log.info("grade: %d Empfehlung(en) gewertet.", graded)
    return 0


def report(send: bool = False) -> int:
    s = db.tracking_stats()
    clv = f"{s['clv_avg']*100:+.2f}%" if s["clv_avg"] is not None else "n/a"
    winrate = f"{s['winrate']*100:.1f}%" if s["winrate"] is not None else "n/a"
    roi = f"{s['roi']*100:+.1f}%" if s["roi"] is not None else "n/a"
    lines = [
        "📈 Tracking-Report",
        f"Empfehlungen gesamt: {s['total']}",
        f"Mittlerer CLV: {clv}  (n={s['clv_n']})  ← Frühindikator für echte Edge",
        f"Gewertet: {s['graded']}  |  Trefferquote: {winrate}",
        f"P&L: {s['pnl_units']:+.3f} Units  |  ROI: {roi}",
    ]
    text = "\n".join(lines)
    print(text)
    if send and s["total"] > 0:
        try:
            telegram.send_message("📈 <b>Tracking-Report</b>\n" + "\n".join(lines[1:]))
        except Exception as exc:
            log.warning("Report-Versand fehlgeschlagen: %s", exc)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Tracking: CLV & Ergebnisse")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("close", help="Closing-Quote + CLV erfassen")
    sub.add_parser("grade", help="Ergebnisse werten + P&L")
    rep = sub.add_parser("report", help="CLV/ROI/P&L ausgeben")
    rep.add_argument("--send", action="store_true", help="Report auch per Telegram")
    args = parser.parse_args()

    db.init_db()
    if args.cmd == "close":
        return close()
    if args.cmd == "grade":
        return grade()
    if args.cmd == "report":
        return report(send=args.send)
    return 1


if __name__ == "__main__":
    sys.exit(main())
