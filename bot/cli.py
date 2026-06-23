"""Inspektions-CLI fuer Ratings und Empfehlungen.

    python -m bot.cli top [atp|wta]      # Top-Spieler nach Elo
    python -m bot.cli rating "Alcaraz"   # Elo eines Spielers (je Belag)
    python -m bot.cli bets                # letzte Empfehlungen + Status
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from .matching.names import NameResolver, normalize_key
from .storage import db


def cmd_top(tour: str | None, limit: int) -> int:
    for t in ([tour] if tour else ["atp", "wta"]):
        ratings = db.all_ratings(t)[:limit]
        if not ratings:
            continue
        print(f"\nTop {t.upper()} (Overall-Elo):")
        for i, r in enumerate(ratings, 1):
            print(f"  {i:2d}. {r.elo_overall:7.1f}  {r.name}  ({r.matches} Matches)")
    return 0


def cmd_rating(query: str) -> int:
    found = False
    for tour in ["atp", "wta"]:
        ratings = db.all_ratings(tour)
        resolver = NameResolver(ratings)
        key = resolver.resolve(query) or normalize_key(query)
        r = db.get_rating(key, tour)
        if r is None:
            continue
        found = True
        print(f"\n{r.name}  [{tour.upper()}]")
        print(f"  Overall: {r.elo_overall:7.1f}  ({r.matches} Matches)")
        print(f"  Hard:    {r.elo_hard:7.1f}  ({r.matches_hard})")
        print(f"  Clay:    {r.elo_clay:7.1f}  ({r.matches_clay})")
        print(f"  Grass:   {r.elo_grass:7.1f}  ({r.matches_grass})")
    if not found:
        print(f"Kein Spieler gefunden fuer '{query}'.")
        return 1
    return 0


def cmd_bets(limit: int) -> int:
    rows = db.recent_recommendations(limit)
    if not rows:
        print("Noch keine Empfehlungen gespeichert.")
        return 0
    print(f"{'Datum':16}  {'Auswahl':22}  {'Quote':>5}  {'EV':>6}  {'CLV':>7}  Status")
    for r in rows:
        when = dt.datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M")
        clv = f"{r['clv']*100:+.1f}%" if r["clv"] is not None else "—"
        status = r["result"] or ("closing" if r["clv"] is not None else "offen")
        print(f"{when:16}  {r['selection'][:22]:22}  {r['odds_taken']:5.2f}  "
              f"{r['ev']*100:5.1f}%  {clv:>7}  {status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot-Inspektion")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_top = sub.add_parser("top")
    p_top.add_argument("tour", nargs="?", choices=["atp", "wta"])
    p_top.add_argument("--limit", type=int, default=15)
    p_rat = sub.add_parser("rating")
    p_rat.add_argument("name")
    p_bets = sub.add_parser("bets")
    p_bets.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    db.init_db()
    if args.cmd == "top":
        return cmd_top(args.tour, args.limit)
    if args.cmd == "rating":
        return cmd_rating(args.name)
    if args.cmd == "bets":
        return cmd_bets(args.limit)
    return 1


if __name__ == "__main__":
    sys.exit(main())
