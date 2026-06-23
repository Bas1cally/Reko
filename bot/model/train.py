"""Baut aus den historischen CSVs die Elo-Ratings auf und speichert sie in SQLite.

Verarbeitet alle Matches einer Tour chronologisch und fuehrt fuer jeden Spieler
ein Overall-Elo sowie je ein Surface-Elo (hard/clay/grass). Carpet & unbekannte
Belaege fliessen nur ins Overall-Elo ein.
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field

from .. import config
from ..matching.names import normalize_key
from ..storage import db
from . import elo
from .score import mov_multiplier

SURFACES = {"hard", "clay", "grass"}


@dataclass
class _PlayerState:
    name: str
    overall: float = config.ELO_START
    hard: float = config.ELO_START
    clay: float = config.ELO_START
    grass: float = config.ELO_START
    n_overall: int = 0
    n: dict = field(default_factory=lambda: {"hard": 0, "clay": 0, "grass": 0})


def _iter_matches(tour: str):
    """Liefert (surface, winner, loser, score) chronologisch sortiert."""
    rows = []
    for path in sorted(config.DATA_DIR.glob(f"{tour}_matches_*.csv")):
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                w, l = row.get("winner_name"), row.get("loser_name")
                date = row.get("tourney_date")
                if not (w and l and date):
                    continue
                try:
                    sort_key = (int(date), int(row.get("match_num") or 0))
                except ValueError:
                    continue
                rows.append((sort_key, (row.get("surface") or "").strip().lower(),
                             w, l, row.get("score") or ""))
    rows.sort(key=lambda r: r[0])
    for _key, surface, w, l, sc in rows:
        yield surface, w, l, sc


def _get(states: dict, name: str) -> _PlayerState:
    key = normalize_key(name)
    st = states.get(key)
    if st is None:
        st = _PlayerState(name=name)
        states[key] = st
    return st


def _update_dimension(winner: _PlayerState, loser: _PlayerState,
                      attr: str, count_key: str | None, mov: float = 1.0) -> None:
    rw = getattr(winner, attr)
    rl = getattr(loser, attr)
    ew = elo.expected_score(rw, rl)
    if count_key is None:
        kw = elo.k_factor(winner.n_overall)
        kl = elo.k_factor(loser.n_overall)
    else:
        kw = elo.k_factor(winner.n[count_key])
        kl = elo.k_factor(loser.n[count_key])
    kw *= mov
    kl *= mov
    setattr(winner, attr, elo.update(rw, 1.0, ew, kw))
    setattr(loser, attr, elo.update(rl, 0.0, 1.0 - ew, kl))


def train_tour(tour: str) -> list[db.Rating]:
    states: dict[str, _PlayerState] = {}
    n_matches = 0
    for surface, w_name, l_name, score in _iter_matches(tour):
        winner = _get(states, w_name)
        loser = _get(states, l_name)
        mov = mov_multiplier(score) if config.ELO_USE_MOV else 1.0

        _update_dimension(winner, loser, "overall", None, mov)
        winner.n_overall += 1
        loser.n_overall += 1

        if surface in SURFACES:
            _update_dimension(winner, loser, surface, surface, mov)
            winner.n[surface] += 1
            loser.n[surface] += 1
        n_matches += 1

    print(f"  {tour}: {n_matches} Matches, {len(states)} Spieler")
    return [
        db.Rating(
            player_key=key,
            tour=tour,
            name=st.name,
            elo_overall=st.overall,
            elo_hard=st.hard,
            elo_clay=st.clay,
            elo_grass=st.grass,
            matches=st.n_overall,
            matches_hard=st.n["hard"],
            matches_clay=st.n["clay"],
            matches_grass=st.n["grass"],
        )
        for key, st in states.items()
    ]


def main() -> int:
    db.init_db()
    all_ratings: list[db.Rating] = []
    for tour in config.TOURS:
        all_ratings.extend(train_tour(tour))
    db.replace_ratings(all_ratings)
    print(f"Gespeichert: {len(all_ratings)} Ratings in {config.DB_PATH}")

    # Sanity: Top 5 je Tour ausgeben.
    for tour in config.TOURS:
        top = db.all_ratings(tour)[:5]
        print(f"\n  Top {tour.upper()} (Overall-Elo):")
        for r in top:
            print(f"    {r.elo_overall:7.1f}  {r.name}  ({r.matches} Matches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
