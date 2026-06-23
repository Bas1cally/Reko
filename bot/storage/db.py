"""SQLite-State: Elo-Ratings, Dedupe gesendeter Bets und Tracking (CLV/Ergebnis).

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
    matches_hard: int = 0
    matches_clay: int = 0
    matches_grass: int = 0

    def surface_elo(self, surface: str) -> float:
        s = (surface or "").strip().lower()
        if s == "hard":
            return self.elo_hard
        if s == "clay":
            return self.elo_clay
        if s == "grass":
            return self.elo_grass
        return self.elo_overall

    def surface_matches(self, surface: str) -> int:
        s = (surface or "").strip().lower()
        if s == "hard":
            return self.matches_hard
        if s == "clay":
            return self.matches_clay
        if s == "grass":
            return self.matches_grass
        return self.matches


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
    """Fuegt fehlende Spalten hinzu (einfache Migration fuer bestehende DBs)."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for col, ddl in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


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
                matches_hard  INTEGER NOT NULL DEFAULT 0,
                matches_clay  INTEGER NOT NULL DEFAULT 0,
                matches_grass INTEGER NOT NULL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS recommendations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                bet_key       TEXT UNIQUE NOT NULL,
                match_id      TEXT NOT NULL,
                sport_key     TEXT,
                tour          TEXT,
                selection     TEXT NOT NULL,
                opponent      TEXT,
                commence_time TEXT,
                commence_ts   REAL,
                bookmaker     TEXT,
                odds_taken    REAL,
                model_prob    REAL,
                sharp_prob    REAL,
                final_prob    REAL,
                ev            REAL,
                stake_fraction REAL,
                created_at    REAL,
                closing_odds  REAL,
                closing_prob  REAL,
                clv           REAL,
                result        TEXT,
                pnl           REAL,
                graded_at     REAL
            );
            """
        )
        # Migration fuer aeltere DBs (v1 ohne Surface-Zaehler).
        _ensure_columns(conn, "ratings", {
            "matches_hard": "INTEGER NOT NULL DEFAULT 0",
            "matches_clay": "INTEGER NOT NULL DEFAULT 0",
            "matches_grass": "INTEGER NOT NULL DEFAULT 0",
        })


# ----- Ratings -----

def replace_ratings(ratings: list[Rating]) -> None:
    """Ueberschreibt die Ratings-Tabelle vollstaendig (nach (Re-)Training)."""
    now = time.time()
    with connect() as conn:
        conn.execute("DELETE FROM ratings")
        conn.executemany(
            """INSERT INTO ratings
               (player_key, tour, name, elo_overall, elo_hard, elo_clay,
                elo_grass, matches, matches_hard, matches_clay, matches_grass,
                updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (r.player_key, r.tour, r.name, r.elo_overall, r.elo_hard,
                 r.elo_clay, r.elo_grass, r.matches, r.matches_hard,
                 r.matches_clay, r.matches_grass, now)
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


def ratings_updated_at() -> Optional[float]:
    with connect() as conn:
        row = conn.execute("SELECT MAX(updated_at) AS ts FROM ratings").fetchone()
    return row["ts"] if row and row["ts"] is not None else None


def _row_to_rating(row: sqlite3.Row) -> Rating:
    keys = row.keys()
    return Rating(
        player_key=row["player_key"],
        tour=row["tour"],
        name=row["name"],
        elo_overall=row["elo_overall"],
        elo_hard=row["elo_hard"],
        elo_clay=row["elo_clay"],
        elo_grass=row["elo_grass"],
        matches=row["matches"],
        matches_hard=row["matches_hard"] if "matches_hard" in keys else 0,
        matches_clay=row["matches_clay"] if "matches_clay" in keys else 0,
        matches_grass=row["matches_grass"] if "matches_grass" in keys else 0,
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


# ----- Tracking: Empfehlungen + CLV + Ergebnis -----

def record_recommendation(rec: dict) -> None:
    """Speichert eine Empfehlung (einmalig pro bet_key; erster Preis bleibt)."""
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO recommendations
               (bet_key, match_id, sport_key, tour, selection, opponent,
                commence_time, commence_ts, bookmaker, odds_taken, model_prob,
                sharp_prob, final_prob, ev, stake_fraction, created_at)
               VALUES (:bet_key,:match_id,:sport_key,:tour,:selection,:opponent,
                :commence_time,:commence_ts,:bookmaker,:odds_taken,:model_prob,
                :sharp_prob,:final_prob,:ev,:stake_fraction,:created_at)""",
            {**rec, "created_at": time.time()},
        )


def recs_pending_close(now_ts: float, window_sec: float) -> list[sqlite3.Row]:
    """Empfehlungen, deren Closing-Quote noch fehlt und deren Anpfiff naht/lief."""
    with connect() as conn:
        return conn.execute(
            """SELECT * FROM recommendations
               WHERE closing_odds IS NULL AND commence_ts IS NOT NULL
                 AND commence_ts <= ?""",
            (now_ts + window_sec,),
        ).fetchall()


def set_closing(rec_id: int, closing_odds: float, closing_prob: float,
                clv: float) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE recommendations SET closing_odds=?, closing_prob=?, clv=? WHERE id=?",
            (closing_odds, closing_prob, clv, rec_id),
        )


def recs_pending_grade(now_ts: float, min_age_sec: float = 7200) -> list[sqlite3.Row]:
    """Empfehlungen ohne Ergebnis, deren Match lange genug her ist."""
    with connect() as conn:
        return conn.execute(
            """SELECT * FROM recommendations
               WHERE result IS NULL AND commence_ts IS NOT NULL
                 AND commence_ts <= ?""",
            (now_ts - min_age_sec,),
        ).fetchall()


def set_result(rec_id: int, result: str, pnl: float) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE recommendations SET result=?, pnl=?, graded_at=? WHERE id=?",
            (result, pnl, time.time(), rec_id),
        )


def recent_recommendations(limit: int = 20) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM recommendations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def tracking_stats() -> dict:
    """Aggregierte Kennzahlen fuer den Report (CLV, ROI, P&L, Trefferquote)."""
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM recommendations").fetchone()["c"]
        clv_row = conn.execute(
            "SELECT AVG(clv) a, COUNT(clv) c FROM recommendations WHERE clv IS NOT NULL"
        ).fetchone()
        graded = conn.execute(
            """SELECT COUNT(*) n,
                      SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) wins,
                      SUM(pnl) pnl, SUM(stake_fraction) staked
               FROM recommendations WHERE result IS NOT NULL AND result != 'void'"""
        ).fetchone()
    n = graded["n"] or 0
    staked = graded["staked"] or 0.0
    pnl = graded["pnl"] or 0.0
    return {
        "total": total,
        "clv_avg": clv_row["a"],
        "clv_n": clv_row["c"] or 0,
        "graded": n,
        "wins": graded["wins"] or 0,
        "winrate": (graded["wins"] / n) if n else None,
        "pnl_units": pnl,
        "roi": (pnl / staked) if staked else None,
    }
