"""SQLite-State: Spieler-Elo-Ratings und Dedupe gesendeter Bets.

Bewusst eine einzige lokale Datei (``state.db``), damit der Bot ohne externe
Dienste (kein Supabase) auf dem VPS laeuft.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from .. import config


@dataclass
class Rating:
    player_key: str
    tour: str
    name: str
    elo_overall: float
    elo_hard: float
    elo_clay: float
    elo_grass: float
    matches: int

    def surface_elo(self, surface: str) -> float:
        s = (surface or "").strip().lower()
        if s == "hard":
            return self.elo_hard
        if s == "clay":
            return self.elo_clay
        if s == "grass":
            return self.elo_grass
        return self.elo_overall


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                player_key   TEXT NOT NULL,
                tour         TEXT NOT NULL,
                name         TEXT NOT NULL,
                elo_overall  REAL NOT NULL,
                elo_hard     REAL NOT NULL,
                elo_clay     REAL NOT NULL,
                elo_grass    REAL NOT NULL,
                matches      INTEGER NOT NULL,
                updated_at   REAL NOT NULL,
                PRIMARY KEY (player_key, tour)
            );

            CREATE TABLE IF NOT EXISTS sent_bets (
                bet_key   TEXT PRIMARY KEY,
                match_id  TEXT NOT NULL,
                selection TEXT NOT NULL,
                bookmaker TEXT NOT NULL,
                odds      REAL NOT NULL,
                ev        REAL NOT NULL,
                sent_at   REAL NOT NULL
            );
            """
        )


# ----- Ratings -----

def replace_ratings(ratings: list[Rating]) -> None:
    """Ueberschreibt die Ratings-Tabelle vollstaendig (nach (Re-)Training)."""
    now = time.time()
    with connect() as conn:
        conn.execute("DELETE FROM ratings")
        conn.executemany(
            """INSERT INTO ratings
               (player_key, tour, name, elo_overall, elo_hard, elo_clay,
                elo_grass, matches, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (r.player_key, r.tour, r.name, r.elo_overall, r.elo_hard,
                 r.elo_clay, r.elo_grass, r.matches, now)
                for r in ratings
            ],
        )


def get_rating(player_key: str, tour: str) -> Optional[Rating]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM ratings WHERE player_key = ? AND tour = ?",
            (player_key, tour),
        ).fetchone()
    return _row_to_rating(row) if row else None


def all_ratings(tour: Optional[str] = None) -> list[Rating]:
    with connect() as conn:
        if tour:
            rows = conn.execute(
                "SELECT * FROM ratings WHERE tour = ? ORDER BY elo_overall DESC",
                (tour,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ratings ORDER BY elo_overall DESC"
            ).fetchall()
    return [_row_to_rating(r) for r in rows]


def _row_to_rating(row: sqlite3.Row) -> Rating:
    return Rating(
        player_key=row["player_key"],
        tour=row["tour"],
        name=row["name"],
        elo_overall=row["elo_overall"],
        elo_hard=row["elo_hard"],
        elo_clay=row["elo_clay"],
        elo_grass=row["elo_grass"],
        matches=row["matches"],
    )


# ----- Dedupe gesendeter Bets -----

def already_sent(bet_key: str, current_ev: float, ev_bump: float = 0.03) -> bool:
    """True, wenn dieser Bet bereits gemeldet wurde und sich der EV nicht
    nennenswert verbessert hat (>= ``ev_bump``). So vermeiden wir Spam, melden
    aber nach, wenn der Value deutlich groesser geworden ist."""
    with connect() as conn:
        row = conn.execute(
            "SELECT ev FROM sent_bets WHERE bet_key = ?", (bet_key,)
        ).fetchone()
    if row is None:
        return False
    return current_ev <= row["ev"] + ev_bump


def mark_sent(bet_key: str, match_id: str, selection: str, bookmaker: str,
              odds: float, ev: float) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO sent_bets
               (bet_key, match_id, selection, bookmaker, odds, ev, sent_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(bet_key) DO UPDATE SET
                 odds = excluded.odds, ev = excluded.ev, sent_at = excluded.sent_at""",
            (bet_key, match_id, selection, bookmaker, odds, ev, time.time()),
        )
