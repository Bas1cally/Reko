"""Haupt-Pipeline: Quoten holen -> Modell -> Markt-Blend -> News -> Value -> Telegram.

Aufruf (auf dem VPS per Cron/systemd):
    python -m bot.run                 # echter Lauf, sendet Telegram
    python -m bot.run --dry-run       # nur Konsole, kein Telegram
    python -m bot.run --no-news       # ohne Claude-News-Layer (reine Baseline)
    python -m bot.run --test-telegram # einmalige Test-Nachricht
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import config
from .logging_setup import get_logger
from .matching.names import NameResolver
from .model import elo
from .news import analyze
from .notify import telegram
from .odds import odds_api
from .storage import db
from .value import engine

log = get_logger(__name__)

# Belag aus dem Turnier-Key der Odds-API raten (sie liefert keinen Belag).
_CLAY = ("french", "roland", "madrid", "monte_carlo", "monte-carlo", "rome",
         "hamburg", "barcelona", "estoril", "clay", "umag", "kitzbuhel",
         "bucharest", "gstaad", "bastad", "munich", "geneva", "lyon", "rio")
_GRASS = ("wimbledon", "halle", "queens", "stuttgart", "hertogenbosch",
          "eastbourne", "newport", "mallorca", "grass")


def guess_surface(sport_key: str) -> str:
    key = sport_key.lower()
    if any(t in key for t in _CLAY):
        return "clay"
    if any(t in key for t in _GRASS):
        return "grass"
    return "hard"  # Default; faellt sonst ohnehin auf Overall-Elo zurueck


def _to_ts(iso: str) -> float | None:
    if not iso:
        return None
    try:
        return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _resolvers() -> dict[str, NameResolver]:
    return {tour: NameResolver(db.all_ratings(tour)) for tour in config.TOURS}


def _model_for_match(match, resolver: NameResolver):
    """(p_home_raw, home_rating, away_rating, surface) oder None bei Skip."""
    home_key = resolver.resolve(match.home)
    away_key = resolver.resolve(match.away)
    if home_key is None or away_key is None:
        missing = match.home if home_key is None else match.away
        log.info("Skip (Name nicht gematcht: '%s') [%s vs %s]",
                 missing, match.home, match.away)
        return None
    home = db.get_rating(home_key, match.tour)
    away = db.get_rating(away_key, match.tour)
    if home is None or away is None:
        return None

    # Zuverlaessigkeits-Filter: zu wenig Historie -> instabiles Elo.
    if min(home.matches, away.matches) < config.MIN_PLAYER_MATCHES:
        log.info("Skip (zu wenig Matches) [%s vs %s]", match.home, match.away)
        return None

    surface = guess_surface(match.sport_key)
    if surface in ("hard", "clay", "grass") and min(
        home.surface_matches(surface), away.surface_matches(surface)
    ) < config.MIN_SURFACE_MATCHES:
        surface = ""  # zu wenig Surface-Daten -> nur Overall-Elo nutzen

    p_home = elo.blended_win_probability(
        home.elo_overall, home.surface_elo(surface),
        away.elo_overall, away.surface_elo(surface),
    )
    return p_home, home, away, surface


def _record(match, bet) -> None:
    db.record_recommendation({
        "bet_key": engine.bet_key(bet),
        "match_id": match.id,
        "sport_key": match.sport_key,
        "tour": match.tour,
        "selection": bet.selection,
        "opponent": match.away if bet.selection == match.home else match.home,
        "commence_time": match.commence_time,
        "commence_ts": _to_ts(match.commence_time),
        "bookmaker": bet.best_book,
        "odds_taken": bet.best_odds,
        "model_prob": bet.raw_model_prob,
        "sharp_prob": bet.sharp_prob,
        "final_prob": bet.model_prob,
        "ev": bet.ev,
        "stake_fraction": bet.stake_fraction,
    })


def run(dry_run: bool = False, use_news: bool = True) -> int:
    db.init_db()
    if not db.all_ratings():
        log.error("Keine Ratings. Bitte: python -m bot.data.fetch_history && "
                  "python -m bot.model.train")
        return 1

    resolvers = _resolvers()
    matches = odds_api.fetch_all_matches()
    log.info("%d Match(es) mit Quoten geladen.", len(matches))

    matched = found = 0
    for match in matches:
        resolver = resolvers.get(match.tour)
        if resolver is None:
            continue
        model = _model_for_match(match, resolver)
        if model is None:
            continue
        p_raw, _home, _away, _surface = model
        matched += 1

        news = None
        if use_news:
            news = analyze.analyze_match(match, p_raw)
            if news.applied:
                p_raw = max(0.01, min(0.99, p_raw + news.home_adjustment))

        # Markt-bewusste Mischung mit dem scharfen Konsens (Home-Seite).
        p_sharp_home = engine.sharp_consensus(match, match.home)
        p_final = engine.blend_with_market(p_raw, p_sharp_home)

        for bet in engine.evaluate(match, p_final, raw_model_home=p_raw):
            key = engine.bet_key(bet)
            if not dry_run and db.already_sent(key, bet.ev):
                continue
            message = telegram.format_bet(bet, news)
            if dry_run:
                print("\n" + "-" * 60)
                print(_strip_html(message))
            else:
                telegram.send_message(message)
                db.mark_sent(key, match.id, bet.selection, bet.best_book,
                             bet.best_odds, bet.ev)
                if config.ENABLE_TRACKING:
                    _record(match, bet)
            found += 1

    quota = odds_api.remaining_quota()
    log.info("Fertig. %d Value-Bet(s) %s. (API-Rest: %s)",
             found, "angezeigt" if dry_run else "gemeldet", quota)
    if not dry_run and config.NOTIFY_SUMMARY:
        try:
            telegram.send_summary(len(matches), matched, found, quota)
        except Exception as exc:  # Summary-Fehler darf den Lauf nicht killen
            log.warning("Summary fehlgeschlagen: %s", exc)
    return 0


def _strip_html(text: str) -> str:
    for tag in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
        text = text.replace(tag, "")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Tennis Value-Betting Bot")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur Konsole, kein Telegram")
    parser.add_argument("--no-news", action="store_true",
                        help="Ohne Claude-News-Layer (reine Modell-Baseline)")
    parser.add_argument("--test-telegram", action="store_true",
                        help="Einmalige Telegram-Test-Nachricht")
    args = parser.parse_args()

    if args.test_telegram:
        ok = telegram.send_message("✅ Tennis Value-Bot: Telegram funktioniert.")
        log.info("Test gesendet." if ok else "Test fehlgeschlagen.")
        return 0 if ok else 1

    try:
        return run(dry_run=args.dry_run, use_news=not args.no_news)
    except Exception as exc:
        log.exception("Lauf abgebrochen: %s", exc)
        if not args.dry_run and config.NOTIFY_ERRORS:
            try:
                telegram.send_error("run", exc)
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
