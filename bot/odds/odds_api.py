"""Client fuer The Odds API (https://the-odds-api.com) - Tennis-Maerkte.

Holt aktive Tennis-Turniere und je Match die H2H-Quoten (Matchsieger) aller
verfuegbaren Buchmacher in den konfigurierten Regionen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from .. import config
from ..logging_setup import get_logger

log = get_logger(__name__)

# Letztes bekanntes Rest-Kontingent der API (aus Response-Headern).
_last_remaining: int | None = None


def _track_quota(resp: requests.Response) -> None:
    global _last_remaining
    rem = resp.headers.get("x-requests-remaining")
    if rem is None:
        return
    try:
        _last_remaining = int(float(rem))
    except ValueError:
        return
    if _last_remaining <= config.MIN_API_QUOTA_WARN:
        log.warning("The Odds API: nur noch %s Anfragen uebrig!", _last_remaining)


def remaining_quota() -> int | None:
    return _last_remaining


@dataclass
class BookOdds:
    key: str            # z.B. "pinnacle"
    title: str          # z.B. "Pinnacle"
    prices: dict        # {team_name: decimal_odds}


@dataclass
class Match:
    id: str
    sport_key: str
    tour: str           # "atp" oder "wta"
    commence_time: str
    home: str
    away: str
    books: list[BookOdds] = field(default_factory=list)

    @property
    def players(self) -> tuple[str, str]:
        return self.home, self.away


def _tour_from_key(sport_key: str) -> str | None:
    if "atp" in sport_key:
        return "atp"
    if "wta" in sport_key:
        return "wta"
    return None


def _require_key() -> str:
    if not config.THE_ODDS_API_KEY:
        raise RuntimeError("THE_ODDS_API_KEY fehlt - bitte in .env setzen.")
    return config.THE_ODDS_API_KEY


def list_active_tennis_sports(tours: list[str] | None = None) -> list[str]:
    tours = tours or config.TOURS
    resp = requests.get(
        f"{config.ODDS_API_BASE}/sports",
        params={"apiKey": _require_key(), "all": "false"},
        timeout=30,
    )
    resp.raise_for_status()
    _track_quota(resp)
    keys = []
    for sport in resp.json():
        key = sport.get("key", "")
        if not key.startswith("tennis_"):
            continue
        if not sport.get("active", False):
            continue
        if _tour_from_key(key) in tours:
            keys.append(key)
    return keys


def get_odds(sport_key: str) -> list[Match]:
    resp = requests.get(
        f"{config.ODDS_API_BASE}/sports/{sport_key}/odds",
        params={
            "apiKey": _require_key(),
            "regions": config.ODDS_REGIONS,
            "markets": config.ODDS_MARKET,
            "oddsFormat": "decimal",
        },
        timeout=30,
    )
    resp.raise_for_status()
    _track_quota(resp)
    return [_parse_event(ev, sport_key) for ev in resp.json()]


def _parse_event(ev: dict, sport_key: str) -> Match:
    books = []
    for bm in ev.get("bookmakers", []):
        prices: dict[str, float] = {}
        for market in bm.get("markets", []):
            if market.get("key") != config.ODDS_MARKET:
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")
                if name and price:
                    prices[name] = float(price)
        if prices:
            books.append(BookOdds(key=bm.get("key", ""),
                                  title=bm.get("title", ""), prices=prices))
    return Match(
        id=ev.get("id", ""),
        sport_key=sport_key,
        tour=_tour_from_key(sport_key) or "",
        commence_time=ev.get("commence_time", ""),
        home=ev.get("home_team", ""),
        away=ev.get("away_team", ""),
        books=books,
    )


def fetch_all_matches(tours: list[str] | None = None) -> list[Match]:
    matches: list[Match] = []
    for sport_key in list_active_tennis_sports(tours):
        try:
            matches.extend(get_odds(sport_key))
        except requests.RequestException as exc:
            log.warning("Quoten fuer %s fehlgeschlagen: %s", sport_key, exc)
    return matches


def get_scores(sport_key: str, days_from: int = 3) -> list[dict]:
    """Abgeschlossene/aktuelle Ergebnisse fuer ein Turnier (Scores-Endpoint).

    Liefert je Event: {id, completed, commence_time, home, away, scores:{name:int}}.
    """
    resp = requests.get(
        f"{config.ODDS_API_BASE}/sports/{sport_key}/scores",
        params={"apiKey": _require_key(), "daysFrom": days_from},
        timeout=30,
    )
    resp.raise_for_status()
    _track_quota(resp)
    results = []
    for ev in resp.json():
        scores = {}
        for s in ev.get("scores") or []:
            name = s.get("name")
            val = s.get("score")
            if name is None or val is None:
                continue
            try:
                scores[name] = int(val)
            except (ValueError, TypeError):
                continue
        results.append({
            "id": ev.get("id", ""),
            "completed": bool(ev.get("completed")),
            "commence_time": ev.get("commence_time", ""),
            "home": ev.get("home_team", ""),
            "away": ev.get("away_team", ""),
            "scores": scores,
        })
    return results


def fetch_all_scores(tours: list[str] | None = None, days_from: int = 3) -> list[dict]:
    out: list[dict] = []
    for sport_key in list_active_tennis_sports(tours):
        try:
            out.extend(get_scores(sport_key, days_from))
        except requests.RequestException as exc:
            log.warning("Scores fuer %s fehlgeschlagen: %s", sport_key, exc)
    return out
