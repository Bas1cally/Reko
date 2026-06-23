"""Haupt-Pipeline: Quoten holen -> Modell -> News -> Value -> Telegram.

Aufruf (auf dem VPS per Cron/systemd):
    python -m bot.run                 # echter Lauf, sendet Telegram
    python -m bot.run --dry-run       # nur Konsole, kein Telegram
    python -m bot.run --no-news       # ohne Claude-News-Layer (reine Baseline)
    python -m bot.run --test-telegram # einmalige Test-Nachricht
"""
from __future__ import annotations

import argparse
import sys

from . import config
from .matching.names import NameResolver
from .model import elo
from .news import analyze
from .notify import telegram
from .odds import odds_api
from .storage import db
from .value import engine

# Belag aus dem Turnier-Key der Odds-API raten (sie liefert keinen Belag).
_CLAY = ("french", "roland", "madrid", "monte_carlo", "monte-carlo", "rome",
         "hamburg", "barcelona", "estoril", "clay", "umag", "kitzbuhel", "bucharest")
_GRASS = ("wimbledon", "halle", "queens", "stuttgart", "hertogenbosch",
          "eastbourne", "newport", "mallorca", "grass")


def guess_surface(sport_key: str) -> str:
    key = sport_key.lower()
    if any(t in key for t in _CLAY):
        return "clay"
    if any(t in key for t in _GRASS):
        return "grass"
    return "hard"  # Default; faellt sonst ohnehin auf Overall-Elo zurueck


def _resolvers() -> dict[str, NameResolver]:
    resolvers = {}
    for tour in config.TOURS:
        resolvers[tour] = NameResolver(db.all_ratings(tour))
    return resolvers


def _model_prob_home(match, resolver: NameResolver):
    home_key = resolver.resolve(match.home)
    away_key = resolver.resolve(match.away)
    if home_key is None or away_key is None:
        missing = match.home if home_key is None else match.away
        print(f"  · uebersprungen (Name nicht gematcht: '{missing}') "
              f"[{match.home} vs {match.away}]")
        return None
    home = db.get_rating(home_key, match.tour)
    away = db.get_rating(away_key, match.tour)
    if home is None or away is None:
        return None
    surface = guess_surface(match.sport_key)
    return elo.blended_win_probability(
        home.elo_overall, home.surface_elo(surface),
        away.elo_overall, away.surface_elo(surface),
    )


def run(dry_run: bool = False, use_news: bool = True) -> int:
    db.init_db()
    if not db.all_ratings():
        print("Keine Ratings gefunden. Bitte zuerst:")
        print("  python -m bot.data.fetch_history && python -m bot.model.train")
        return 1

    resolvers = _resolvers()
    matches = odds_api.fetch_all_matches()
    print(f"{len(matches)} Match(es) mit Quoten geladen.")

    found = 0
    for match in matches:
        resolver = resolvers.get(match.tour)
        if resolver is None:
            continue
        p_home = _model_prob_home(match, resolver)
        if p_home is None:
            continue

        news = None
        if use_news:
            news = analyze.analyze_match(match, p_home)
            if news.applied:
                p_home = max(0.01, min(0.99, p_home + news.home_adjustment))

        for bet in engine.evaluate(match, p_home):
            key = engine.bet_key(bet)
            if not dry_run and db.already_sent(key, bet.ev):
                continue
            message = telegram.format_bet(bet, news)
            if dry_run:
                print("\n" + "-" * 60)
                print(message.replace("<b>", "").replace("</b>", "")
                             .replace("<i>", "").replace("</i>", ""))
            else:
                telegram.send_message(message)
                db.mark_sent(key, match.id, bet.selection, bet.best_book,
                             bet.best_odds, bet.ev)
            found += 1

    print(f"\nFertig. {found} Value-Bet(s) {'angezeigt' if dry_run else 'gemeldet'}.")
    return 0


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
        print("Test gesendet." if ok else "Test fehlgeschlagen.")
        return 0 if ok else 1

    return run(dry_run=args.dry_run, use_news=not args.no_news)


if __name__ == "__main__":
    sys.exit(main())
