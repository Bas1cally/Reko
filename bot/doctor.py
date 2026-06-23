"""Self-Check: prueft Konfiguration, Daten und Erreichbarkeit vor dem Betrieb.

Aufruf:  python -m bot.doctor
"""
from __future__ import annotations

import sys
import time

from . import config
from .storage import db


def _ok(b: bool) -> str:
    return "✅" if b else "❌"


def main() -> int:
    print("=== Tennis Value-Bot · Doctor ===\n")
    problems = 0

    # 1. Secrets / Keys
    checks = [
        ("THE_ODDS_API_KEY", bool(config.THE_ODDS_API_KEY), True),
        ("TELEGRAM_BOT_TOKEN", bool(config.TELEGRAM_BOT_TOKEN), True),
        ("TELEGRAM_CHAT_ID", bool(config.TELEGRAM_CHAT_ID), True),
        ("ANTHROPIC_API_KEY (News)", bool(config.ANTHROPIC_API_KEY), False),
        ("NEWS_API_KEY (News)", bool(config.NEWS_API_KEY), False),
    ]
    print("Keys:")
    for name, present, required in checks:
        print(f"  {_ok(present)} {name}{'' if required else '  (optional)'}")
        if required and not present:
            problems += 1

    # 2. Ratings / Daten
    print("\nDaten:")
    db.init_db()
    n_ratings = len(db.all_ratings())
    print(f"  {_ok(n_ratings > 0)} Ratings in DB: {n_ratings}")
    if n_ratings == 0:
        print("     -> python -m bot.data.fetch_history && python -m bot.model.train")
        problems += 1
    else:
        ts = db.ratings_updated_at()
        if ts:
            age_days = (time.time() - ts) / 86400
            fresh = age_days < 14
            print(f"  {_ok(fresh)} Ratings-Alter: {age_days:.1f} Tage"
                  f"{'' if fresh else '  -> refresh_ratings empfohlen'}")

    # 3. Aktive Features / Parameter
    print("\nFeatures & Parameter:")
    print(f"  News-Layer:    {'an' if config.ENABLE_NEWS and config.ANTHROPIC_API_KEY else 'aus'}")
    print(f"  Tracking:      {'an' if config.ENABLE_TRACKING else 'aus'}")
    print(f"  Touren:        {', '.join(config.TOURS)}")
    print(f"  De-Vig:        {config.DEVIG_METHOD}")
    print(f"  Markt-Blend:   {config.MODEL_MARKET_BLEND}")
    print(f"  Kelly:         {config.KELLY_FRACTION}× (Cap {config.MAX_STAKE_FRACTION*100:.0f}%)")
    print(f"  Bankroll:      {config.BANKROLL if config.BANKROLL else '— (keine €-Anzeige)'}")
    print(f"  MIN_EV:        {config.MIN_EV*100:.0f}%  | MIN_BOOKS: {config.MIN_BOOKS}"
          f"  | MIN_PLAYER_MATCHES: {config.MIN_PLAYER_MATCHES}")

    print(f"\n{'✅ Bereit.' if problems == 0 else f'❌ {problems} Problem(e) gefunden.'}")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
