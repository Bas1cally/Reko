"""Client fuer The Odds API (https://the-odds-api.com) - Tennis-Maerkte.

Holt aktive Tennis-Turniere und je Match die H2H-Quoten (Matchsieger) aller
verfuegbaren Buchmacher in den konfigurierten Regionen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from .. import config


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
            print(f"  ! Quoten fuer {sport_key} fehlgeschlagen: {exc}")
    return matches
